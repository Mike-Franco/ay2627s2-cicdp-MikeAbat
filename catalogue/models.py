from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim
from django.core.validators import MaxValueValidator, MinValueValidator

from inventory_access.models import Business, Inventory


class Product(models.Model):
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="products")
    sku = models.CharField(max_length=64)
    name = models.TextField()
    # NULL means the legacy product has not had its receiving setup completed.
    base_unit_label = models.CharField(max_length=40, null=True, blank=True)
    expiry_tracking_required = models.BooleanField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    safety_stock_units = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(2_147_483_647)],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                F("business"), Lower(Trim("sku")), name="unique_business_sku_ci_trimmed"
            ),
            models.CheckConstraint(
                condition=Q(lead_time_days__isnull=True) | Q(lead_time_days__gte=1),
                name="product_lead_time_positive_or_unset",
            ),
            models.CheckConstraint(
                condition=Q(lead_time_days__isnull=True) | Q(lead_time_days__lte=365),
                name="product_lead_time_max_365_or_unset",
            ),
            models.CheckConstraint(
                condition=Q(safety_stock_units__isnull=True) | Q(safety_stock_units__lte=2_147_483_647),
                name="product_safety_stock_cap_or_unset",
            ),
            models.CheckConstraint(
                condition=Q(base_unit_label__isnull=True) | Q(base_unit_label__regex=r"\S"),
                name="product_unit_label_nonblank_or_unset",
            ),
        ]
    lead_time_days = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(365)]
    )

    def clean(self):
        super().clean()
        self.sku = self.sku.strip()
        if self.base_unit_label is not None:
            self.base_unit_label = self.base_unit_label.strip()
        if not self.sku:
            raise ValidationError({"sku": "SKU is required."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class InventoryProduct(models.Model):
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="product_links")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="inventory_links")
    # Provisional storage only: currency, scale and precision are not approved.
    selling_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    physical_quantity_units = models.PositiveBigIntegerField(default=0)
    last_receipt_sequence = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["inventory", "product"], name="unique_inventory_product_link"),
            models.CheckConstraint(
                condition=Q(physical_quantity_units__lte=2147483647),
                name="inventory_product_physical_quantity_cap",
            ),
        ]

    def clean(self):
        super().clean()
        if self.inventory_id and self.product_id:
            if self.inventory.business_id != self.product.business_id:
                raise ValidationError({"product": "Inventory and product must belong to the same business."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProductLifecycleAuditEvent(models.Model):
    """Immutable evidence of an actual Product status transition."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="lifecycle_audit_events")
    action = models.CharField(max_length=16)
    classification = models.CharField(max_length=16, default="non_demand")
    previous_is_active = models.BooleanField()
    new_is_active = models.BooleanField()
    occurred_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(action="deactivate", previous_is_active=True, new_is_active=False)
                           | Q(action="reactivate", previous_is_active=False, new_is_active=True)),
                name="product_lifecycle_audit_transition",
            ),
            models.CheckConstraint(
                condition=Q(classification="non_demand"),
                name="product_lifecycle_audit_non_demand",
            ),
        ]
