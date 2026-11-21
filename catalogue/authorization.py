from django.db import connection

from inventory_access.authorization import authorized_inventories, get_authorized_inventory
from inventory_access.models import BusinessMembership, InventoryAssignment

from .models import InventoryProduct


def visible_product_links(user):
    """Limit catalogue rows to products linked to inventories the user may view."""
    allowed_ids = authorized_inventories(user).values("pk")
    return InventoryProduct.objects.filter(inventory_id__in=allowed_ids).select_related(
        "product", "inventory"
    ).order_by("product__sku", "inventory__name", "pk")


def visible_inventory_product_links(user, inventory_id):
    """Resolve the inventory through TORY-12 before querying its product links."""
    inventory = get_authorized_inventory(user, inventory_id)
    return inventory, InventoryProduct.objects.filter(inventory=inventory).select_related("product").order_by("product__sku", "pk")


def managed_inventories(user):
    manager_assignments = InventoryAssignment.objects.filter(
        membership__user=user, membership__role=BusinessMembership.Role.MANAGER,
        membership__is_active=True, is_active=True,
    ).values("inventory_id")
    return authorized_inventories(user).filter(pk__in=manager_assignments)


def lock_manager_assignment_ids(user_id, business_id):
    """Hold Manager authority stable for the duration of a shared product write."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT is_active FROM accounts_user WHERE id=%s FOR SHARE", [user_id])
        user_state = cursor.fetchone()
        cursor.execute(
            "SELECT id, role, is_active FROM inventory_access_businessmembership "
            "WHERE user_id=%s AND business_id=%s FOR SHARE", [user_id, business_id],
        )
        membership = cursor.fetchone()
        if (not user_state or not user_state[0] or not membership
                or membership[1:] != (BusinessMembership.Role.MANAGER, True)):
            return set()
        cursor.execute(
            "SELECT inventory_id, is_active FROM inventory_access_inventoryassignment "
            "WHERE membership_id=%s ORDER BY inventory_id FOR SHARE", [membership[0]],
        )
        return {inventory_id for inventory_id, active in cursor.fetchall() if active}


def can_manage_product_lifecycle(user, product):
    """Require an active Manager assignment to every linked inventory."""
    if not user.is_authenticated or not user.is_active:
        return False
    membership = BusinessMembership.objects.filter(
        user=user, business_id=product.business_id,
        role=BusinessMembership.Role.MANAGER, is_active=True,
    ).first()
    if membership is None:
        return False
    linked_ids = set(InventoryProduct.objects.filter(
        product=product,
    ).values_list("inventory_id", flat=True))
    assigned_ids = set(InventoryAssignment.objects.filter(
        membership=membership, is_active=True,
    ).values_list("inventory_id", flat=True))
    return bool(linked_ids) and linked_ids <= assigned_ids
