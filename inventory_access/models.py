from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Business(models.Model):
    name = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BusinessMembership(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff"

    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="business_memberships")
    role = models.CharField(max_length=12, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["business", "user"], name="unique_business_membership")]

    def __str__(self):
        return f"{self.user} — {self.business} ({self.role})"


class Inventory(models.Model):
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="inventories")
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return f"{self.name} — {self.business}"


class InventoryAssignment(models.Model):
    membership = models.ForeignKey(BusinessMembership, on_delete=models.PROTECT, related_name="inventory_assignments")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="assignments")
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "inventory"], name="unique_membership_inventory_assignment")]

    def clean(self):
        super().clean()
        if self.membership_id and self.inventory_id:
            if self.membership.business_id != self.inventory.business_id:
                raise ValidationError({"inventory": "Membership and inventory must belong to the same business."})

    def save(self, *args, **kwargs):
        # This invariant spans two foreign-key rows, so a portable DB CHECK
        # cannot express it; validate ordinary ORM saves as well as forms.
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.membership} → {self.inventory}"
