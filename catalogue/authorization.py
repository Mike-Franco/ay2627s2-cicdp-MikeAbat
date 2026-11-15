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
