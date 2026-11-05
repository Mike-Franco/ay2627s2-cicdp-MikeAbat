import hashlib
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from catalogue.models import InventoryProduct, Product
from inventory_access.models import BusinessMembership, Inventory, InventoryAssignment

from .models import MAX_RECEIPT_UNITS, ReceiptAuditEvent, ReceivingBatch


class ReceiptRejected(Exception):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def _fingerprint(inventory_id, product_id, quantity_units, expiry_date):
    payload = {
        "inventory_id": int(inventory_id),
        "product_id": int(product_id),
        "quantity_units": int(quantity_units),
        "expiry_date": expiry_date.isoformat() if expiry_date else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _lock_authorized_scope(user_id, inventory_id, product_id):
    """Lock in membership/assignment then Product→Inventory→link order.

    The product-first parent order matches the revised InventoryProduct trigger;
    assignment locks make receipt-first versus revocation-first observable.
    """
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
                or membership_state[1] not in (BusinessMembership.Role.MANAGER, BusinessMembership.Role.STAFF)
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

