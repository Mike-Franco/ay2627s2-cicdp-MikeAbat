from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from config.media import delete_image_after_commit

from .authorization import manager_memberships
from .models import Inventory, InventoryAssignment, InventoryChangeAuditEvent

DUPLICATE_NAME = "An inventory with this name already exists in this business."


def _lock_manager(user, business_id):
    # Match stock writers: user, membership, assignment, then inventory.
    get_object_or_404(get_user_model().objects.select_for_update(no_key=True), pk=user.pk, is_active=True)
    return get_object_or_404(manager_memberships(user).select_for_update(no_key=True), business_id=business_id)


APPEARANCE = ("icon", "colour", "picture")


def _snapshot(inventory):
    return {"name": inventory.name, "is_active": inventory.is_active,
            "icon": inventory.icon, "colour": inventory.colour, "picture": inventory.picture.name or ""}


def _save_inventory(inventory):
    try:
        with transaction.atomic():
            inventory.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) != "unique_inventory_business_name_ci":
            raise
        raise ValidationError(DUPLICATE_NAME, code="duplicate") from error


def _record_change(user, inventory, action, before):
    InventoryChangeAuditEvent.objects.create(
        actor=user, business_id=inventory.business_id, inventory=inventory, action=action,
        before=before, after=_snapshot(inventory), occurred_at=timezone.now(),
    )


@transaction.atomic
def create_inventory(*, user, business_id, name, icon=None, colour=None, picture=""):
    """picture is a storage name already written by config.media, or ""."""
    manager = _lock_manager(user, business_id)
    inventory = Inventory(business_id=business_id, name=name.strip(), picture=picture)
    if icon:
        inventory.icon = icon
    if colour:
        inventory.colour = colour
    _save_inventory(inventory)
    InventoryAssignment.objects.create(membership=manager, inventory=inventory)
    _record_change(user, inventory, InventoryChangeAuditEvent.Action.CREATE, None)


@transaction.atomic
def update_inventory(*, user, inventory, name=None, is_active=None, icon=None, colour=None, picture=None):
    """Change one inventory. picture: a new storage name, "" to remove, or None to keep."""
    manager = _lock_manager(user, inventory.business_id)
    get_object_or_404(
        InventoryAssignment.objects.select_for_update(no_key=True),
        membership=manager, inventory_id=inventory.pk, is_active=True,
    )
    inventory = get_object_or_404(
        Inventory.objects.select_for_update(), pk=inventory.pk, business_id=manager.business_id,
    )
    before = _snapshot(inventory)
    actions = InventoryChangeAuditEvent.Action
    old_picture = inventory.picture.name
    if name is not None or icon is not None or colour is not None or picture is not None:
        if name is not None:
            inventory.name = name.strip()
        if icon is not None:
            inventory.icon = icon
        if colour is not None:
            inventory.colour = colour
        if picture is not None:
            inventory.picture = picture
        action = actions.RENAME if inventory.name != before["name"] else actions.RESTYLE
    else:
        inventory.is_active = is_active
        action = actions.REACTIVATE if is_active else actions.DEACTIVATE
    if _snapshot(inventory) != before:
        inventory.full_clean(exclude=["business", "name"], validate_unique=False, validate_constraints=False)
        _save_inventory(inventory)
        _record_change(user, inventory, action, before)
        if inventory.picture.name != old_picture:
            delete_image_after_commit(old_picture)


class AccessRejected(ValidationError):
    pass


def staff_access(inventory):
    """Every active membership of the inventory's business, with whether it can use this inventory."""
    from .models import BusinessMembership

    memberships = (BusinessMembership.objects.filter(business_id=inventory.business_id, is_active=True,
                                                     user__is_active=True)
                   .select_related("user").order_by("role", "user__email"))
    assignments = InventoryAssignment.objects.filter(membership__in=memberships, is_active=True,
                                                     inventory__is_active=True).select_related("inventory")
    here, elsewhere = set(), {}
    for assignment in assignments:
        if assignment.inventory_id == inventory.pk:
            here.add(assignment.membership_id)
        else:
            elsewhere.setdefault(assignment.membership_id, []).append(assignment.inventory.name)
    return [{"membership": membership, "manager": membership.role == BusinessMembership.Role.MANAGER,
             "has_access": membership.role == BusinessMembership.Role.MANAGER or membership.pk in here,
             "elsewhere": sorted(elsewhere.get(membership.pk, []))} for membership in memberships]


@transaction.atomic
def set_staff_access(*, user, inventory, membership_ids):
    """Make exactly these Staff memberships able to use the inventory (TORY-65).

    Assignment rows are switched on or off, never deleted. Each change writes an
    audit event for the Activity log. Ids that are not active Staff in this
    business are rejected, so nothing changes. Returns [(membership, granted)].
    """
    from .models import BusinessMembership, InventoryAccessAuditEvent

    manager = _lock_manager(user, inventory.business_id)
    get_object_or_404(InventoryAssignment.objects.select_for_update(no_key=True),
                      membership=manager, inventory_id=inventory.pk, is_active=True)
    inventory = get_object_or_404(Inventory.objects.select_for_update(), pk=inventory.pk,
                                  business_id=manager.business_id, is_active=True)
    staff = {membership.pk: membership for membership in BusinessMembership.objects.select_for_update(
        no_key=True).filter(business_id=inventory.business_id, role=BusinessMembership.Role.STAFF, is_active=True)
        .select_related("user")}
    wanted = set(membership_ids)
    if not wanted <= set(staff):
        raise AccessRejected("Choose Staff from this business only.", code="foreign_membership")
    assignments = {assignment.membership_id: assignment for assignment in InventoryAssignment.objects
                   .select_for_update(no_key=True).filter(inventory=inventory, membership_id__in=staff)}
    now = timezone.now()
    changes = []
    for pk, membership in staff.items():
        assignment = assignments.get(pk)
        active = bool(assignment and assignment.is_active)
        if (pk in wanted) == active:
            continue
        if assignment is None:
            InventoryAssignment.objects.create(membership=membership, inventory=inventory)
        else:
            assignment.is_active = pk in wanted
            assignment.save(update_fields=["is_active"])
        InventoryAccessAuditEvent.objects.create(actor=user, business_id=inventory.business_id, inventory=inventory,
                                                 membership=membership, granted=pk in wanted, occurred_at=now)
        changes.append((membership, pk in wanted))
    return changes


def confirms_name(inventory, typed):
    """Deactivation confirm: the typed name must match exactly (case-sensitive), ignoring outer spaces."""
    return isinstance(typed, str) and typed.strip() == inventory.name.strip()
