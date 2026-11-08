import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, Inventory


MAX_RECEIPT_UNITS = 2_147_483_647


class StockImport(models.Model):
    """A successful, inventory-scoped CSV file; failed files leave no row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    raw_bytes = models.BinaryField()
    sha256 = models.CharField(max_length=64, db_index=True)
    committed_at = models.DateTimeField()


class ReceivingBatch(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        CSV = "csv", "CSV"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="receiving_batches")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="receiving_batches")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="receiving_batches")
    inventory_product = models.ForeignKey(InventoryProduct, on_delete=models.PROTECT, related_name="receiving_batches")
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL)
    request_token = models.UUIDField()
    input_fingerprint = models.CharField(max_length=64)
    quantity_units = models.PositiveIntegerField()
    remaining_quantity_units = models.PositiveIntegerField()
    quarantined_quantity_units = models.PositiveIntegerField(default=0)
    unit_label_snapshot = models.CharField(max_length=40)
    expiry_date = models.DateField(null=True, blank=True)
    receipt_sequence = models.PositiveBigIntegerField()
    received_at = models.DateTimeField()
    import_record = models.ForeignKey(StockImport, null=True, blank=True, on_delete=models.PROTECT)
    import_row_number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "source", "request_token"], name="unique_actor_receipt_request_token"
            ),
            models.UniqueConstraint(
                fields=["inventory_product", "receipt_sequence"], name="unique_receipt_sequence_per_inventory_product"
            ),
            models.CheckConstraint(
                condition=Q(quantity_units__gte=1) & Q(quantity_units__lte=MAX_RECEIPT_UNITS),
                name="receiving_batch_quantity_range",
            ),
            models.CheckConstraint(
                condition=Q(remaining_quantity_units__lte=MAX_RECEIPT_UNITS),
                name="receiving_batch_remaining_cap",
            ),
            models.CheckConstraint(
                condition=Q(quarantined_quantity_units__lte=F("remaining_quantity_units")),
                name="receiving_batch_quarantine_lte_remaining",
            ),
            models.CheckConstraint(
                condition=Q(input_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="receiving_batch_fingerprint_sha256",
            ),
            models.CheckConstraint(
                condition=~Q(unit_label_snapshot=""),
                name="receiving_batch_unit_label_nonblank",
            ),
        ]


class ReceiptAuditEvent(models.Model):
    """Immutable, non-demand evidence committed with exactly one receipt batch."""

    id = models.BigAutoField(primary_key=True)
    batch = models.OneToOneField(ReceivingBatch, on_delete=models.PROTECT, related_name="audit_event")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="receipt_audit_events")
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="receipt_audit_events")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="receipt_audit_events")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="receipt_audit_events")
    source = models.CharField(max_length=12, default=ReceivingBatch.Source.MANUAL)
    action = models.CharField(max_length=16, default="receipt")
    classification = models.CharField(max_length=16, default="non_demand")
    quantity_before_units = models.PositiveBigIntegerField()
    quantity_change_units = models.PositiveIntegerField()
    quantity_after_units = models.PositiveBigIntegerField()
    occurred_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(action="receipt"), name="receipt_audit_action_is_receipt"),
            models.CheckConstraint(condition=Q(classification="non_demand"), name="receipt_audit_is_non_demand"),
            models.CheckConstraint(
                condition=Q(quantity_after_units=F("quantity_before_units") + F("quantity_change_units")),
                name="receipt_audit_quantity_reconciles",
            ),
            models.CheckConstraint(
                condition=Q(quantity_before_units__lte=MAX_RECEIPT_UNITS)
                & Q(quantity_change_units__lte=MAX_RECEIPT_UNITS)
                & Q(quantity_after_units__lte=MAX_RECEIPT_UNITS),
                name="receipt_audit_quantity_cap",
            ),
        ]


class ExpiryQuarantineEvent(models.Model):
    """One system transition per immutable batch expiry boundary."""

    id = models.BigAutoField(primary_key=True)
    batch = models.OneToOneField(ReceivingBatch, on_delete=models.PROTECT, related_name="expiry_event")
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    actor_identity = models.CharField(max_length=32, default="system:expiry_quarantine")
    action = models.CharField(max_length=32, default="expiry_quarantine")
    classification = models.CharField(max_length=16, default="non_demand")
    effective_at = models.DateTimeField()
    recorded_at = models.DateTimeField()
    physical_quantity_units = models.PositiveIntegerField()
    disposed_before_recording_units = models.PositiveIntegerField(default=0)
    available_before_units = models.PositiveIntegerField()
    available_after_units = models.PositiveIntegerField(default=0)
    quarantine_before_units = models.PositiveIntegerField()
    quarantine_after_units = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(actor_identity="system:expiry_quarantine"), name="expiry_event_system_actor"),
            models.CheckConstraint(condition=Q(action="expiry_quarantine"), name="expiry_event_action"),
            models.CheckConstraint(condition=Q(classification="non_demand"), name="expiry_event_non_demand"),
            models.CheckConstraint(condition=Q(recorded_at__gte=F("effective_at")), name="expiry_event_recorded_after_effective"),
            models.CheckConstraint(condition=Q(available_after_units=0), name="expiry_event_zero_available"),
            models.CheckConstraint(condition=Q(quarantine_after_units=F("physical_quantity_units")), name="expiry_event_quarantine_reconciles"),
            models.CheckConstraint(condition=Q(available_before_units=F("physical_quantity_units") + F("disposed_before_recording_units") - F("quarantine_before_units")), name="expiry_event_boundary_reconciles"),
        ]


class StockDisposal(models.Model):
    """One Manager physical disposal from an expired quarantined batch."""

    class ReasonCode(models.TextChoices):
        EXPIRED = "Expired", "Expired"
        DAMAGED = "Damaged", "Damaged"
        OTHER = "Other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    inventory_product = models.ForeignKey(InventoryProduct, on_delete=models.PROTECT)
    batch = models.ForeignKey(ReceivingBatch, on_delete=models.PROTECT, related_name="disposals")
    quantity_units = models.PositiveIntegerField()
    batch_before_units = models.PositiveIntegerField()
    batch_after_units = models.PositiveIntegerField()
    stored_quarantine_before_units = models.PositiveIntegerField()
    stored_quarantine_after_units = models.PositiveIntegerField()
    physical_before_units = models.PositiveBigIntegerField()
    physical_after_units = models.PositiveBigIntegerField()
    reason_code = models.CharField(max_length=16, choices=ReasonCode.choices)
    reason_note = models.TextField(blank=True)
    occurred_at = models.DateTimeField()
    batch_applied = models.BooleanField(default=False)
    balance_applied = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity_units__gte=1) & Q(quantity_units__lte=MAX_RECEIPT_UNITS), name="disposal_quantity_range"),
            models.CheckConstraint(condition=Q(batch_after_units=F("batch_before_units") - F("quantity_units")), name="disposal_batch_reconciles"),
            models.CheckConstraint(condition=Q(physical_after_units=F("physical_before_units") - F("quantity_units")), name="disposal_balance_reconciles"),
            models.CheckConstraint(condition=Q(stored_quarantine_after_units__lte=F("batch_after_units")), name="disposal_stored_quarantine_bound"),
            models.CheckConstraint(condition=Q(reason_code__in=("Expired", "Damaged", "Other")), name="disposal_reason_code_valid"),
            models.CheckConstraint(condition=~Q(reason_code="Other") | ~Q(reason_note__regex=r"^\s*$"), name="disposal_other_note_required"),
        ]


class DisposalAuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    disposal = models.OneToOneField(StockDisposal, on_delete=models.PROTECT, related_name="audit_event")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(ReceivingBatch, on_delete=models.PROTECT)
    action = models.CharField(max_length=16, default="disposal")
    classification = models.CharField(max_length=16, default="non_demand")
    quantity_units = models.PositiveIntegerField()
    batch_before_units = models.PositiveIntegerField()
    batch_after_units = models.PositiveIntegerField()
    physical_before_units = models.PositiveBigIntegerField()
    physical_after_units = models.PositiveBigIntegerField()
    reason_code = models.CharField(max_length=16)
    reason_note = models.TextField(blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(action="disposal"), name="disposal_audit_action"),
            models.CheckConstraint(condition=Q(classification="non_demand"), name="disposal_audit_non_demand"),
            models.CheckConstraint(condition=Q(batch_after_units=F("batch_before_units") - F("quantity_units")), name="disposal_audit_batch_reconciles"),
            models.CheckConstraint(condition=Q(physical_after_units=F("physical_before_units") - F("quantity_units")), name="disposal_audit_balance_reconciles"),
        ]


class StockOut(models.Model):
    """One attributable manual issue; allocation rows identify consumed batches."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_outs")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="stock_outs")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_outs")
    inventory_product = models.ForeignKey(InventoryProduct, on_delete=models.PROTECT, related_name="stock_outs")
    quantity_units = models.PositiveIntegerField()
    quantity_before_units = models.PositiveBigIntegerField()
    quantity_after_units = models.PositiveBigIntegerField()
    occurred_at = models.DateTimeField()
    balance_applied = models.BooleanField(default=False)
    import_record = models.ForeignKey(StockImport, null=True, blank=True, on_delete=models.PROTECT)
    import_row_number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity_units__gte=1) & Q(quantity_units__lte=MAX_RECEIPT_UNITS), name="stock_out_quantity_range"),
            models.CheckConstraint(condition=Q(quantity_after_units=F("quantity_before_units") - F("quantity_units")), name="stock_out_quantity_reconciles"),
        ]


class StockOutAllocation(models.Model):
    stock_out = models.ForeignKey(StockOut, on_delete=models.PROTECT, related_name="allocations")
    batch = models.ForeignKey(ReceivingBatch, on_delete=models.PROTECT, related_name="stock_out_allocations")
    quantity_units = models.PositiveIntegerField()
    applied = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["stock_out", "batch"], name="unique_stock_out_batch_allocation"),
            models.CheckConstraint(condition=Q(quantity_units__gte=1), name="stock_out_allocation_positive"),
        ]


class DemandAuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    stock_out = models.OneToOneField(StockOut, on_delete=models.PROTECT, related_name="audit_event")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="demand_audit_events")
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="demand_audit_events")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="demand_audit_events")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="demand_audit_events")
    quantity_before_units = models.PositiveBigIntegerField()
    quantity_change_units = models.PositiveIntegerField()
    quantity_after_units = models.PositiveBigIntegerField()
    occurred_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity_after_units=F("quantity_before_units") - F("quantity_change_units")), name="demand_audit_quantity_reconciles"),
            models.CheckConstraint(condition=Q(quantity_before_units__lte=MAX_RECEIPT_UNITS) & Q(quantity_after_units__lte=MAX_RECEIPT_UNITS) & Q(quantity_change_units__lte=MAX_RECEIPT_UNITS), name="demand_audit_quantity_cap"),
        ]


class StockAdjustment(models.Model):
    """Manager's absolute batch count, kept separate from demand events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_adjustments")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="stock_adjustments")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_adjustments")
    inventory_product = models.ForeignKey(InventoryProduct, on_delete=models.PROTECT, related_name="stock_adjustments")
    quantity_before_units = models.PositiveBigIntegerField()
    quantity_after_units = models.PositiveBigIntegerField()
    quantity_change_units = models.BigIntegerField()
    reason = models.TextField()
    occurred_at = models.DateTimeField()
    balance_applied = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity_before_units__lte=MAX_RECEIPT_UNITS) & Q(quantity_after_units__lte=MAX_RECEIPT_UNITS), name="stock_adjustment_quantity_cap"),
            models.CheckConstraint(condition=Q(quantity_after_units=F("quantity_before_units") + F("quantity_change_units")), name="stock_adjustment_quantity_reconciles"),
            models.CheckConstraint(condition=~Q(reason=""), name="stock_adjustment_reason_nonblank"),
        ]


class StockAdjustmentAllocation(models.Model):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.PROTECT, related_name="allocations")
    batch = models.ForeignKey(ReceivingBatch, on_delete=models.PROTECT, related_name="adjustment_allocations")
    quantity_before_units = models.PositiveIntegerField()
    counted_quantity_units = models.PositiveIntegerField()
    quantity_change_units = models.IntegerField()
    manager_confirmed_identity = models.BooleanField(default=False)
    applied = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["adjustment", "batch"], name="unique_adjustment_batch_allocation"),
            models.CheckConstraint(condition=Q(quantity_before_units__lte=MAX_RECEIPT_UNITS) & Q(counted_quantity_units__lte=MAX_RECEIPT_UNITS), name="stock_adjustment_allocation_cap"),
            models.CheckConstraint(condition=Q(counted_quantity_units=F("quantity_before_units") + F("quantity_change_units")), name="stock_adjustment_allocation_reconciles"),
            models.CheckConstraint(condition=Q(manager_confirmed_identity=True), name="stock_adjustment_identity_confirmed"),
        ]


class StockAdjustmentAuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    adjustment = models.OneToOneField(StockAdjustment, on_delete=models.PROTECT, related_name="audit_event")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_adjustment_audit_events")
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="stock_adjustment_audit_events")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="stock_adjustment_audit_events")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_adjustment_audit_events")
    quantity_before_units = models.PositiveBigIntegerField()
    quantity_after_units = models.PositiveBigIntegerField()
    quantity_change_units = models.BigIntegerField()
    reason = models.TextField()
    action = models.CharField(max_length=20, default="adjustment")
    classification = models.CharField(max_length=16, default="non_demand")
    occurred_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity_before_units__lte=MAX_RECEIPT_UNITS) & Q(quantity_after_units__lte=MAX_RECEIPT_UNITS), name="stock_adjustment_audit_cap"),
            models.CheckConstraint(condition=Q(quantity_after_units=F("quantity_before_units") + F("quantity_change_units")), name="stock_adjustment_audit_reconciles"),
            models.CheckConstraint(condition=Q(action="adjustment"), name="stock_adjustment_audit_action"),
            models.CheckConstraint(condition=Q(classification="non_demand"), name="stock_adjustment_audit_non_demand"),
            models.CheckConstraint(condition=~Q(reason=""), name="stock_adjustment_audit_reason_nonblank"),
        ]

