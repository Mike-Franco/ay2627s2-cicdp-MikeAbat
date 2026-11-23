from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim

from config.palette import DEFAULT_TONE, TONE_CHOICES, TONE_KEYS

from .icons import DEFAULT_ICON, ICON_KEYS, ICONS


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
    # TORY-54: how the inventory is recognised at a glance. Only preset keys
    # are stored; the picture is written only by config.media.
    icon = models.CharField(max_length=24, choices=ICONS, default=DEFAULT_ICON)
    colour = models.CharField(max_length=12, choices=TONE_CHOICES, default=DEFAULT_TONE)
    picture = models.FileField(upload_to="inventories/", max_length=120, blank=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                "business", Lower(Trim("name")), name="unique_inventory_business_name_ci",
            ),
            models.CheckConstraint(condition=models.Q(icon__in=sorted(ICON_KEYS)), name="inventory_icon_preset"),
            models.CheckConstraint(condition=models.Q(colour__in=sorted(TONE_KEYS)), name="inventory_colour_preset"),
        ]

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        super().save(*args, **kwargs)

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


class InventoryChangeAuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        RENAME = "rename", "Rename"
        DEACTIVATE = "deactivate", "Deactivate"
        REACTIVATE = "reactivate", "Reactivate"
        RESTYLE = "restyle", "Change icon, colour or picture"

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="change_audit_events")
    action = models.CharField(max_length=10, choices=Action.choices)
    before = models.JSONField(null=True)
    after = models.JSONField()
    occurred_at = models.DateTimeField()

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=(
                    models.Q(action="create", before__isnull=True)
                    | models.Q(action__in=("rename", "deactivate", "reactivate", "restyle"), before__isnull=False)
                ),
                name="inventory_change_action_before",
            ),
        ]
