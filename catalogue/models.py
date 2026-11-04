from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim
from django.core.validators import MinValueValidator

from inventory_access.models import Business, Inventory


class Product(models.Model):
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="products")
    sku = models.CharField(max_length=64)
    name = models.TextField()
    safety_stock_units = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                F("business"), Lower(Trim("sku")), name="unique_business_sku_ci_trimmed"
            ),
            models.CheckConstraint(
                condition=Q(lead_time_days__isnull=True) | Q(lead_time_days__gte=1),
                name="product_lead_time_positive_or_unset",
            ),
        ]
    lead_time_days = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )

    def clean(self):
        super().clean()
        self.sku = self.sku.strip()
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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["inventory", "product"], name="unique_inventory_product_link")
        ]

    def clean(self):
        super().clean()
        if self.inventory_id and self.product_id:
            if self.inventory.business_id != self.product.business_id:
                raise ValidationError({"product": "Inventory and product must belong to the same business."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
