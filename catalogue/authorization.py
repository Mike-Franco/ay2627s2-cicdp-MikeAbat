from inventory_access.authorization import authorized_inventories, get_authorized_inventory

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
