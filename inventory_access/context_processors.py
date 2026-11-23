"""Navigation data comes from the same assignment scope as inventory views."""

from .authorization import authorized_inventories
from .models import BusinessMembership
from .selection import current_inventory, url_inventory_id


def workspace(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return {}

    inventories = list(authorized_inventories(request.user).select_related("business"))
    inventory_id = url_inventory_id(request)
    # The inventory in the URL (breadcrumbs, product links) and the remembered
    # selection that the switcher, the inventory group and Manage pages follow.
    selected = next((item for item in inventories if item.pk == inventory_id), None)
    current = current_inventory(request, inventories)
    role_inventory = current or (inventories[0] if inventories else None)
    role = None
    if role_inventory:
        role = BusinessMembership.objects.filter(
            user=request.user, business_id=role_inventory.business_id, is_active=True,
            inventory_assignments__inventory=role_inventory,
            inventory_assignments__is_active=True,
        ).values_list("role", flat=True).first()
    return {
        "workspace_inventories": inventories,
        "workspace_inventory": selected,
        "workspace_current": current,
        "workspace_default_inventory": role_inventory,
        "workspace_role": BusinessMembership.Role.MANAGER.label if role == BusinessMembership.Role.MANAGER else (
            BusinessMembership.Role.STAFF.label if role == BusinessMembership.Role.STAFF else None
        ),
        "workspace_is_manager": role == BusinessMembership.Role.MANAGER,
    }
