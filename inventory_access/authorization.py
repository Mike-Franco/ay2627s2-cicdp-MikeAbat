from django.core.exceptions import PermissionDenied
from django.db.models import F

from .models import BusinessMembership, Inventory, InventoryAssignment


def authorized_inventories(user):
    """Return active inventories explicitly assigned within active user memberships."""
    if not user.is_authenticated or not user.is_active:
        return Inventory.objects.none()
    return Inventory.objects.filter(
        is_active=True,
        assignments__is_active=True,
        assignments__membership__user=user,
        assignments__membership__is_active=True,
        assignments__membership__business_id=F("business_id"),
    ).distinct()


def get_authorized_inventory(user, inventory_id):
    """Scope lookup before returning the object, so foreign IDs disclose no contents."""
    return authorized_inventories(user).get(pk=inventory_id)


def assign_staff_inventory(actor, staff_membership, inventory):
    """Assign Staff only where the Manager already has current same-business access."""
    actor_membership = BusinessMembership.objects.filter(
        user=actor,
        business=staff_membership.business,
        role=BusinessMembership.Role.MANAGER,
        is_active=True,
    ).first()
    if (
        not actor.is_authenticated
        or not actor.is_active
        or
        actor_membership is None
        or staff_membership.role != BusinessMembership.Role.STAFF
        or not staff_membership.is_active
        or inventory.business_id != staff_membership.business_id
        or not InventoryAssignment.objects.filter(
            membership=actor_membership, inventory=inventory, is_active=True
        ).exists()
    ):
        raise PermissionDenied

    assignment = InventoryAssignment(membership=staff_membership, inventory=inventory)
    assignment.full_clean()
    assignment.save()
    return assignment
