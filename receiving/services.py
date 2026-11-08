import hashlib
import json
import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, connection, transaction
from django.db.models import F, Q
from django.db.models.functions import Now
from django.utils import timezone

from catalogue.models import InventoryProduct, Product
from inventory_access.models import BusinessMembership, Inventory, InventoryAssignment

from .models import (MAX_RECEIPT_UNITS, DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent, ReceiptAuditEvent,
                     ReceivingBatch, StockOut, StockOutAllocation,
                     StockAdjustment, StockAdjustmentAllocation,
                     StockAdjustmentAuditEvent, StockDisposal)


EXPIRY_CONSTRAINT_NAME = "receiving_expiry_after_singapore_today"
SINGAPORE = ZoneInfo("Asia/Singapore")


class ReceiptRejected(Exception):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def expiry_boundary(expiry_date):
    return datetime.combine(expiry_date, time.min, tzinfo=SINGAPORE)


def quarantine_quantity(batch, *, at=None):
    """The displayed quarantine is date-derived even before evidence is written."""
    local_date = (at or timezone.now()).astimezone(SINGAPORE).date()
    if batch.expiry_date is not None and batch.expiry_date <= local_date:
        return batch.remaining_quantity_units
    return batch.quarantined_quantity_units


def process_expiry_quarantine():
    """Reconcile due batches; one transaction and one immutable event per batch."""
    due_ids = list(ReceivingBatch.objects.filter(
        expiry_date__lte=timezone.localdate(), expiry_event__isnull=True,
    ).order_by("expiry_date", "id").values_list("id", flat=True))
    created = 0
    for batch_id in due_ids:
        # Match the Product -> Inventory -> InventoryProduct -> Batch order used
        # by receipt, issue and count operations, then recheck after locking.
        hint = ReceivingBatch.objects.only("product_id", "inventory_id", "inventory_product_id").get(pk=batch_id)
        with transaction.atomic():
            Product.objects.select_for_update().get(pk=hint.product_id)
            Inventory.objects.select_for_update().get(pk=hint.inventory_id)
            InventoryProduct.objects.select_for_update().get(pk=hint.inventory_product_id)
            batch = ReceivingBatch.objects.select_for_update().get(pk=batch_id)
            if batch.expiry_date is None or batch.expiry_date > timezone.localdate():
                continue
            if ExpiryQuarantineEvent.objects.filter(batch=batch).exists():
                continue
            before_quarantine = batch.quarantined_quantity_units
            remaining = batch.remaining_quantity_units
            disposed_before = sum(batch.disposals.values_list("quantity_units", flat=True))
            ExpiryQuarantineEvent.objects.create(
                batch=batch, business_id=batch.product.business_id,
                inventory_id=batch.inventory_id, product_id=batch.product_id,
                effective_at=expiry_boundary(batch.expiry_date), recorded_at=Now(),
                physical_quantity_units=remaining,
                disposed_before_recording_units=disposed_before,
                available_before_units=remaining + disposed_before - before_quarantine,
                quarantine_before_units=before_quarantine,
                quarantine_after_units=remaining,
            )
            if before_quarantine != remaining:
                batch.quarantined_quantity_units = remaining
                batch.save(update_fields=["quarantined_quantity_units"])
            created += 1
    return created


def dispose_quarantined(*, user_id, inventory_id, product_id, batch_id,
                        quantity_units, reason_code, reason_note=""):
    """Remove quarantined physical units with one Manager-attributed audit."""
    if type(quantity_units) is not int or not 1 <= quantity_units <= MAX_RECEIPT_UNITS:
        raise ReceiptRejected("quantity_units", "Enter a positive whole quantity in base units.")
    if reason_code not in StockDisposal.ReasonCode.values:
        raise ReceiptRejected("reason_code", "Choose Expired, Damaged, or Other.")
    if not isinstance(reason_note, str):
        raise ReceiptRejected("reason_note", "Enter a valid note.")
    reason_note = reason_note.strip()
    if len(reason_note) > 2000:
        raise ReceiptRejected("reason_note", "Enter a note of no more than 2,000 characters.")
    if reason_code == StockDisposal.ReasonCode.OTHER and not reason_note:
        raise ReceiptRejected("reason_note", "Enter a note for Other.")
    try:
        batch_id = uuid.UUID(str(batch_id))
    except (TypeError, ValueError, AttributeError) as error:
        raise ReceiptRejected("batch_id", "Select an expired quarantined batch.") from error

    with transaction.atomic():
        user, _, _, product, inventory, link = _lock_authorized_scope(
            user_id, inventory_id, product_id,
            allowed_roles=(BusinessMembership.Role.MANAGER,),
        )
        try:
            batch = ReceivingBatch.objects.select_for_update().get(
                pk=batch_id, inventory_product=link,
            )
        except ReceivingBatch.DoesNotExist as error:
            raise ReceiptRejected("batch_id", "Select an expired quarantined batch.") from error
        if batch.expiry_date is None or batch.expiry_date > timezone.localdate():
            raise ReceiptRejected("batch_id", "Only quarantined units may be disposed.")
        if quantity_units > quarantine_quantity(batch):
            raise ReceiptRejected("quantity_units", "Disposal exceeds the quarantined units remaining.")
        if batch.quarantined_quantity_units not in (0, batch.remaining_quantity_units):
            raise ReceiptRejected("batch_id", "The batch quarantine state requires review.")
        physical_before = link.physical_quantity_units
        if quantity_units > physical_before:
            raise ReceiptRejected("quantity_units", "Disposal exceeds physical stock.")
        batch_before = batch.remaining_quantity_units
        stored_before = batch.quarantined_quantity_units
        stored_after = stored_before - quantity_units if stored_before else 0
        disposal = StockDisposal.objects.create(
            actor=user, inventory=inventory, product=product, inventory_product=link,
            batch=batch, quantity_units=quantity_units,
            batch_before_units=batch_before, batch_after_units=batch_before-quantity_units,
            stored_quarantine_before_units=stored_before,
            stored_quarantine_after_units=stored_after,
            physical_before_units=physical_before,
            physical_after_units=physical_before-quantity_units,
            reason_code=reason_code, reason_note=reason_note, occurred_at=timezone.now(),
        )
        batch.remaining_quantity_units -= quantity_units
        batch.quarantined_quantity_units = stored_after
        batch.save(update_fields=["remaining_quantity_units", "quarantined_quantity_units"])
        link.physical_quantity_units -= quantity_units
        link.save(update_fields=["physical_quantity_units"])
        DisposalAuditEvent.objects.create(
            disposal=disposal, actor=user, business_id=product.business_id,
            inventory=inventory, product=product, batch=batch,
            quantity_units=quantity_units,
            batch_before_units=batch_before, batch_after_units=batch.remaining_quantity_units,
            physical_before_units=physical_before,
            physical_after_units=link.physical_quantity_units,
            reason_code=reason_code, reason_note=reason_note, occurred_at=disposal.occurred_at,
        )
        return disposal


def _fingerprint(inventory_id, product_id, quantity_units, expiry_date):
    payload = {
        "inventory_id": int(inventory_id),
        "product_id": int(product_id),
        "quantity_units": int(quantity_units),
        "expiry_date": expiry_date.isoformat() if expiry_date else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _lock_authorized_scope(user_id, inventory_id, product_id, *, allowed_roles=None):
    """Lock in membership/assignment then Product→Inventory→link order.

    The product-first parent order matches the revised InventoryProduct trigger;
    assignment locks make receipt-first versus revocation-first observable.
    """
    allowed_roles = allowed_roles or (BusinessMembership.Role.MANAGER, BusinessMembership.Role.STAFF)
    try:
        inventory_hint = Inventory.objects.only("business_id").get(pk=inventory_id)
        # Shared row locks block account/membership/assignment revocation while
        # allowing distinct receipt requests by the same actor to proceed.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT is_active FROM accounts_user WHERE id = %s FOR SHARE", [user_id]
            )
            user_state = cursor.fetchone()
            if not user_state or not user_state[0]:
                raise ReceiptRejected("__all__", "This inventory or product is unavailable.")
            cursor.execute(
                "SELECT id, role, is_active FROM inventory_access_businessmembership "
                "WHERE user_id = %s AND business_id = %s FOR SHARE",
                [user_id, inventory_hint.business_id],
            )
            membership_state = cursor.fetchone()
            if (
                not membership_state
                or not membership_state[2]
                or membership_state[1] not in allowed_roles
            ):
                raise ReceiptRejected("__all__", "This inventory or product is unavailable.")
            cursor.execute(
                "SELECT is_active FROM inventory_access_inventoryassignment "
                "WHERE membership_id = %s AND inventory_id = %s FOR SHARE",
                [membership_state[0], inventory_id],
            )
            assignment_state = cursor.fetchone()
            if not assignment_state or not assignment_state[0]:
                raise ReceiptRejected("__all__", "This inventory or product is unavailable.")
        user = get_user_model().objects.get(pk=user_id, is_active=True)
        membership = BusinessMembership.objects.get(pk=membership_state[0])
        assignment = InventoryAssignment.objects.get(
            membership_id=membership.pk, inventory_id=inventory_id, is_active=True
        )
        product = Product.objects.select_for_update().get(pk=product_id)
        inventory = Inventory.objects.select_for_update().get(
            pk=inventory_id, business_id=product.business_id
        )
        link = InventoryProduct.objects.select_for_update().get(
            inventory=inventory, product=product
        )
    except ObjectDoesNotExist as error:
        raise ReceiptRejected("__all__", "This inventory or product is unavailable.") from error

    if not user.is_active or not membership.is_active or not assignment.is_active:
        raise ReceiptRejected("__all__", "This inventory or product is unavailable.")
    if not inventory.is_active or not product.is_active:
        raise ReceiptRejected("__all__", "This inventory or product is unavailable.")
    return user, membership, assignment, product, inventory, link


def _check_replay(batch, fingerprint):
    if batch.input_fingerprint != fingerprint:
        raise ReceiptRejected("request_token", "This form token was already used with different receipt details.")
    return batch, True


def _is_token_unique_error(error):
    cause = getattr(error, "__cause__", None)
    return getattr(getattr(cause, "diag", None), "constraint_name", None) == "unique_actor_receipt_request_token"


def _has_constraint(error, name):
    cause = getattr(error, "__cause__", None)
    return getattr(getattr(cause, "diag", None), "constraint_name", None) == name


def receive_manual(*, user_id, inventory_id, product_id, request_token, quantity_units, expiry_date):
    """Commit a manual receipt, audit, balance and sequence as one operation."""
    if type(quantity_units) is not int:
        raise ReceiptRejected("quantity_units", "Enter a whole quantity in base units.")
    fingerprint = _fingerprint(inventory_id, product_id, quantity_units, expiry_date)
    try:
        with transaction.atomic():
            user, _, _, product, inventory, link = _lock_authorized_scope(
                user_id, inventory_id, product_id
            )
            existing = ReceivingBatch.objects.filter(
                actor=user, source=ReceivingBatch.Source.MANUAL, request_token=request_token
            ).first()
            if existing:
                return _check_replay(existing, fingerprint)

            if product.base_unit_label is None or product.expiry_tracking_required is None:
                raise ReceiptRejected("__all__", "Receiving setup must be completed before this product can be received.")
            if expiry_date and expiry_date <= timezone.localdate():
                raise ReceiptRejected("expiry_date", "Expiry must be later than today's Singapore date.")
            if product.expiry_tracking_required and expiry_date is None:
                raise ReceiptRejected("expiry_date", "Expiry date is required for this product.")
            if quantity_units < 1 or quantity_units > MAX_RECEIPT_UNITS:
                raise ReceiptRejected("quantity_units", "Enter a whole quantity within the approved limit.")
            before = link.physical_quantity_units
            if before + quantity_units > MAX_RECEIPT_UNITS:
                raise ReceiptRejected("quantity_units", "This receipt would exceed the physical stock limit.")

            batch = ReceivingBatch.objects.create(
                actor=user,
                inventory=inventory,
                product=product,
                inventory_product=link,
                source=ReceivingBatch.Source.MANUAL,
                request_token=request_token,
                input_fingerprint=fingerprint,
                quantity_units=quantity_units,
                remaining_quantity_units=quantity_units,
                unit_label_snapshot=product.base_unit_label,
                expiry_date=expiry_date,
                receipt_sequence=link.last_receipt_sequence + 1,
                received_at=timezone.now(),
            )
            _create_receipt_audit(batch, before)
            return batch, False
    except IntegrityError as error:
        # The exception escapes transaction.atomic first, so every tentative
        # row/counter is rolled back before it becomes a form-level rejection.
        if _has_constraint(error, EXPIRY_CONSTRAINT_NAME):
            raise ReceiptRejected(
                "expiry_date", "Expiry must be later than today's Singapore date."
            ) from error
        if not _is_token_unique_error(error):
            raise

    # A concurrent request with this actor/operation/token committed first.
    # Start a new transaction and re-lock current authorization before replay.
    with transaction.atomic():
        user, _, _, _, _, _ = _lock_authorized_scope(user_id, inventory_id, product_id)
        try:
            existing = ReceivingBatch.objects.get(
                actor=user, source=ReceivingBatch.Source.MANUAL, request_token=request_token
            )
        except ReceivingBatch.DoesNotExist:
            raise ReceiptRejected("request_token", "The request could not be completed; submit a new form.")
        return _check_replay(existing, fingerprint)


def _create_receipt_audit(batch, quantity_before):
    """Separate write point so transaction rollback on evidence failure is testable."""
    ReceiptAuditEvent.objects.create(
        batch=batch,
        actor=batch.actor,
        business_id=batch.product.business_id,
        inventory=batch.inventory,
        product=batch.product,
        source=batch.source,
        action="receipt",
        classification="non_demand",
        quantity_before_units=quantity_before,
        quantity_change_units=batch.quantity_units,
        quantity_after_units=quantity_before + batch.quantity_units,
        occurred_at=batch.received_at,
    )


def issue_stock(*, user_id, inventory_id, product_id, quantity_units):
    """Issue eligible stock using approved dated FEFO then undated FIFO."""
    if type(quantity_units) is not int or not 1 <= quantity_units <= MAX_RECEIPT_UNITS:
        raise ReceiptRejected("quantity_units", "Enter a positive whole quantity in base units.")
    with transaction.atomic():
        user, _, _, product, inventory, link = _lock_authorized_scope(user_id, inventory_id, product_id)
        candidates = list(ReceivingBatch.objects.select_for_update().filter(
            inventory_product=link,
            remaining_quantity_units__gt=F("quarantined_quantity_units"),
        ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gt=timezone.localdate()))
          .order_by("expiry_date", "receipt_sequence", "id"))
        physical_before = link.physical_quantity_units
        eligible_total = sum(b.remaining_quantity_units - b.quarantined_quantity_units for b in candidates)
        if eligible_total < quantity_units:
            raise ReceiptRejected("quantity_units", "There is not enough eligible, non-quarantined stock.")
        now = timezone.now()
        stock_out = StockOut.objects.create(
            actor=user, inventory=inventory, product=product, inventory_product=link,
            quantity_units=quantity_units, quantity_before_units=physical_before,
            quantity_after_units=physical_before - quantity_units, occurred_at=now,
        )
        left = quantity_units
        for batch in candidates:
            if left == 0:
                break
            allocated = min(left, batch.remaining_quantity_units - batch.quarantined_quantity_units)
            StockOutAllocation.objects.create(stock_out=stock_out, batch=batch, quantity_units=allocated)
            batch.remaining_quantity_units -= allocated
            batch.save(update_fields=["remaining_quantity_units"])
            left -= allocated
        link.physical_quantity_units = physical_before - quantity_units
        link.save(update_fields=["physical_quantity_units"])
        _create_demand_audit(stock_out)
        return stock_out


def _create_demand_audit(stock_out):
    DemandAuditEvent.objects.create(
        stock_out=stock_out, actor=stock_out.actor,
        business_id=stock_out.product.business_id, inventory=stock_out.inventory,
        product=stock_out.product, quantity_before_units=stock_out.quantity_before_units,
        quantity_change_units=stock_out.quantity_units, quantity_after_units=stock_out.quantity_after_units,
        occurred_at=stock_out.occurred_at,
    )


def adjust_stock(*, user_id, inventory_id, product_id, batch_counts, reason):
    """Apply Manager-confirmed absolute counts to existing eligible batches."""
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 2000:
        raise ReceiptRejected("reason", "Enter a reason of no more than 2,000 characters.")
    if not isinstance(batch_counts, (list, tuple)) or not batch_counts:
        raise ReceiptRejected("batch_counts", "Select and confirm at least one batch count.")
    normalized = {}
    for row in batch_counts:
        try:
            batch_id, count = row["batch_id"], row["counted_quantity_units"]
            confirmed = row["manager_confirmed_identity"]
        except (TypeError, KeyError):
            raise ReceiptRejected("batch_counts", "Enter a valid count for each confirmed batch.")
        if confirmed is not True:
            raise ReceiptRejected("batch_counts", "Confirm the identity and physical count of each selected batch.")
        if type(count) is not int or not 0 <= count <= MAX_RECEIPT_UNITS:
            raise ReceiptRejected("batch_counts", "Counts must be whole units within the approved limit.")
        try:
            batch_id = uuid.UUID(str(batch_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise ReceiptRejected("batch_counts", "Select a valid existing batch.") from error
        if batch_id in normalized:
            raise ReceiptRejected("batch_counts", "A batch can be counted only once per adjustment.")
        normalized[batch_id] = count

    with transaction.atomic():
        user, _, _, product, inventory, link = _lock_authorized_scope(
            user_id, inventory_id, product_id, allowed_roles=(BusinessMembership.Role.MANAGER,)
        )
        # Same Product → Inventory → InventoryProduct parent order as receive/issue;
        # stable batch-PK ordering keeps any multi-batch adjustment deterministic.
        batches = list(ReceivingBatch.objects.select_for_update().filter(
            inventory_product=link, pk__in=normalized.keys()
        ).order_by("pk"))
        if len(batches) != len(normalized):
            raise ReceiptRejected("batch_counts", "One or more batches are no longer available for this product.")
        today = timezone.localdate()
        for batch in batches:
            if batch.quarantined_quantity_units or (batch.expiry_date and batch.expiry_date <= today):
                raise ReceiptRejected("batch_counts", "Expired or quarantined batches cannot be adjusted here.")
        before = link.physical_quantity_units
        change = sum(normalized[batch.pk] - batch.remaining_quantity_units for batch in batches)
        after = before + change
        if after < 0 or after > MAX_RECEIPT_UNITS:
            raise ReceiptRejected("batch_counts", "The resulting physical balance is outside the approved limit.")
        now = timezone.now()
        adjustment = StockAdjustment.objects.create(
            actor=user, inventory=inventory, product=product, inventory_product=link,
            quantity_before_units=before, quantity_after_units=after,
            quantity_change_units=change, reason=reason, occurred_at=now,
        )
        for batch in batches:
            count = normalized[batch.pk]
            delta = count - batch.remaining_quantity_units
            StockAdjustmentAllocation.objects.create(
                adjustment=adjustment, batch=batch,
                quantity_before_units=batch.remaining_quantity_units,
                counted_quantity_units=count, quantity_change_units=delta,
                manager_confirmed_identity=True,
            )
            batch.remaining_quantity_units = count
            batch.save(update_fields=["remaining_quantity_units"])
        link.physical_quantity_units = after
        link.save(update_fields=["physical_quantity_units"])
        StockAdjustmentAuditEvent.objects.create(
            adjustment=adjustment, actor=user, business_id=product.business_id,
            inventory=inventory, product=product,
            quantity_before_units=before, quantity_after_units=after,
            quantity_change_units=change, reason=reason, occurred_at=now,
        )
        return adjustment

