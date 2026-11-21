"""Bulk lookups for list and card templates, so pages stay free of per-row queries."""

from collections import Counter, defaultdict

from django import template
from django.utils import timezone

from catalogue.authorization import visible_product_links
from inventory_access.models import InventoryAssignment

register = template.Library()


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None


@register.simple_tag(takes_context=True)
def staff_inventory_names(context, staff_accounts, business_id):
    """{user id: [inventory names]} for the listed accounts, in one query.

    Only inventories the viewing Manager is also assigned to are named, so the
    list never reveals inventories outside the viewer's authority.
    """
    viewer = context["request"].user
    viewer_inventories = InventoryAssignment.objects.filter(
        is_active=True, membership__user=viewer, membership__is_active=True,
        membership__business_id=business_id,
    ).values("inventory_id")
    names = defaultdict(list)
    for user_id, name in InventoryAssignment.objects.filter(
        is_active=True, membership__business_id=business_id,
        membership__user_id__in=[account.pk for account in staff_accounts],
        inventory_id__in=viewer_inventories,
    ).order_by("inventory__name", "inventory_id").values_list("membership__user_id", "inventory__name"):
        names[user_id].append(name)
    return names


@register.simple_tag(takes_context=True)
def inventory_card_stats(context, inventories):
    """{inventory id: {"products": n, "low_stock": n}} for the viewer's visible links."""
    from accounts.dashboard import reorder_alerts

    ids = {inventory.pk for inventory in inventories}
    links = list(visible_product_links(context["request"].user).filter(inventory_id__in=ids))
    _, low_stock, _ = reorder_alerts(links, at=timezone.now())
    products = Counter(link.inventory_id for link in links)
    low = Counter(link.inventory_id for link, _ in low_stock)
    return {inventory_id: {"products": products[inventory_id], "low_stock": low[inventory_id]} for inventory_id in ids}
