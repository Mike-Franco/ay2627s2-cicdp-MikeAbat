import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, Inventory


MAX_RECEIPT_UNITS = 2_147_483_647


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
                condition=Q(remaining_quantity_units__lte=F("quantity_units")),
                name="receiving_batch_remaining_lte_received",
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

