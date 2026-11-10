"""Business-wide product lifecycle changes under the stock writers' Product lock."""

from django.db import connection, transaction

from inventory_access.models import BusinessMembership, Inventory

from .models import InventoryProduct, Product


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
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_active FROM accounts_user WHERE id=%s FOR SHARE", [user_id])
            user_state = cursor.fetchone()
            cursor.execute(
                "SELECT id, role, is_active FROM inventory_access_businessmembership "
                "WHERE user_id=%s AND business_id=%s FOR SHARE",
                [user_id, hint.business_id],
            )
            membership = cursor.fetchone()
            if (not user_state or not user_state[0] or not membership
                    or membership[1:] != (BusinessMembership.Role.MANAGER, True)):
                raise ProductLifecycleRejected(unavailable)
            cursor.execute(
                "SELECT inventory_id, is_active FROM inventory_access_inventoryassignment "
                "WHERE membership_id=%s ORDER BY inventory_id FOR SHARE", [membership[0]],
            )
            assigned_ids = {row[0] for row in cursor.fetchall() if row[1]}
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
            product.is_active = active
            product.save(update_fields=["is_active"])
        return product
