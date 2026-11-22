"""Restricted whole-account Staff deactivation."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef

from inventory_access.models import BusinessMembership, Inventory, InventoryAssignment


class StaffDeactivationRejected(Exception):
    """The requested account is outside the Manager's current authority."""


def _eligible(actor, target, business_id, *, lock=False):
    """Check every membership and assignment, including inactive historical rows.

    The write path holds User FOR UPDATE locks first. They block new membership
    FK inserts and reset transitions. Membership FOR UPDATE blocks new assignment
    FK inserts. Inventory and assignment locks then stabilize the current scope.
    """
    if (actor is None or target is None or not actor.is_active or
            actor.pk == target.pk or target.is_staff or target.is_superuser):
        return False
    memberships = BusinessMembership.objects.filter(user_id__in=(actor.pk, target.pk)).order_by("pk")
    if lock:
        memberships = memberships.select_for_update()
    memberships = list(memberships)
    managers = [m for m in memberships if m.user_id == actor.pk and
                m.business_id == business_id and m.role == BusinessMembership.Role.MANAGER and m.is_active]
    target_memberships = [m for m in memberships if m.user_id == target.pk]
    if (len(managers) != 1 or len(target_memberships) != 1 or
            target_memberships[0].business_id != business_id or
            target_memberships[0].role != BusinessMembership.Role.STAFF or
            not target_memberships[0].is_active):
        return False
    manager, staff = managers[0], target_memberships[0]
    assignments = InventoryAssignment.objects.filter(
        membership_id__in=(manager.pk, staff.pk)).order_by("pk")
    # Lock all referenced inventories before assignment rows, as invitation
    # issuance does. Inactive inventories are retained in the eligibility test.
    inventory_ids = list(assignments.values_list("inventory_id", flat=True))
    inventories = Inventory.objects.filter(pk__in=inventory_ids).order_by("pk")
    if lock:
        inventories = inventories.select_for_update()
    active_ids = {i.pk for i in inventories if i.business_id == business_id and i.is_active}
    if lock:
        assignments = assignments.select_for_update()
    assignments = list(assignments)
    authorized_ids = {a.inventory_id for a in assignments if
                      a.membership_id == manager.pk and a.is_active and a.inventory_id in active_ids}
    return all(a.inventory_id in authorized_ids for a in assignments if a.membership_id == staff.pk)


def visible_staff(actor_id, business_id):
    """Only return account details for currently eligible targets."""
    manager = BusinessMembership.objects.filter(
        user_id=actor_id, user__is_active=True, business_id=business_id,
        role=BusinessMembership.Role.MANAGER, is_active=True,
    )
    allowed = InventoryAssignment.objects.filter(
        membership__in=manager, is_active=True,
        inventory__is_active=True, inventory__business_id=business_id,
    ).values("inventory_id")
    other_memberships = BusinessMembership.objects.filter(
        user_id=OuterRef("pk"),
    ).exclude(business_id=business_id)
    outside_assignments = InventoryAssignment.objects.filter(
        membership__user_id=OuterRef("pk"), membership__business_id=business_id,
    ).exclude(inventory_id__in=allowed)
    return get_user_model().objects.filter(
        Exists(manager), ~Exists(other_memberships), ~Exists(outside_assignments),
        is_staff=False, is_superuser=False,
        business_memberships__business_id=business_id,
        business_memberships__role=BusinessMembership.Role.STAFF,
        business_memberships__is_active=True,
    ).exclude(pk=actor_id).order_by("email", "pk")


def deactivate_staff(actor_id, business_id, target_id):
    """Recheck authority under PostgreSQL locks; repeat requests are safe."""
    User = get_user_model()
    with transaction.atomic():
        actor = User.objects.select_for_update().filter(pk=actor_id).first()
        target = User.objects.select_for_update().filter(pk=target_id).first()
        if not _eligible(actor, target, business_id, lock=True):
            raise StaffDeactivationRejected("Staff account is unavailable.")
        if target.is_active:
            target.is_active = False
            target.save(update_fields=["is_active"])
        return target
