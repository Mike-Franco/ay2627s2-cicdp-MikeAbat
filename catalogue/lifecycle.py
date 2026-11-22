"""Business-wide product lifecycle changes under the stock writers' Product lock."""

from django.db import transaction
from django.utils import timezone

from inventory_access.models import Inventory

from .authorization import lock_manager_assignment_ids
from .models import InventoryProduct, Product, ProductLifecycleAuditEvent


class ProductLifecycleRejected(Exception):
    pass


def set_product_active(*, user_id, inventory_id, product_id, active):
    """Change status only for a Manager assigned to every linked inventory."""
    if type(active) is not bool:
        raise ValueError("active must be a boolean")
    unavailable = "This inventory or product is unavailable."
    with transaction.atomic():
        try:
            hint = Inventory.objects.only("business_id").get(pk=inventory_id, is_active=True)
        except Inventory.DoesNotExist as error:
            raise ProductLifecycleRejected(unavailable) from error
        # Match stock writers' authorization -> Product lock order. A concurrent
        # account, membership, or assignment revocation cannot slip past this check.
        assigned_ids = lock_manager_assignment_ids(user_id, hint.business_id)
        if inventory_id not in assigned_ids:
            raise ProductLifecycleRejected(unavailable)
        try:
            product = Product.objects.select_for_update().get(
                pk=product_id, business_id=hint.business_id,
            )
        except Product.DoesNotExist as error:
            raise ProductLifecycleRejected(unavailable) from error
        linked_ids = set(InventoryProduct.objects.filter(
            product=product,
        ).values_list("inventory_id", flat=True))
        if inventory_id not in linked_ids or not linked_ids <= assigned_ids:
            raise ProductLifecycleRejected(unavailable)
        # Every physical balance counts, including inactive inventories and
        # quarantined batches. Stock writers hold this Product lock to commit.
        if not active and InventoryProduct.objects.filter(
            product=product, physical_quantity_units__gt=0,
        ).exists():
            raise ProductLifecycleRejected(
                "Physical stock must be zero in every inventory before deactivation."
            )
        if product.is_active != active:
            previous = product.is_active
            product.is_active = active
            product.save(update_fields=["is_active"])
            ProductLifecycleAuditEvent.objects.create(
                actor_id=user_id, business_id=product.business_id,
                inventory_id=inventory_id, product=product,
                action="reactivate" if active else "deactivate",
                previous_is_active=previous, new_is_active=active,
                occurred_at=timezone.now(),
            )
        return product
