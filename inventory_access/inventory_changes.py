from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .authorization import manager_memberships
from .models import Inventory, InventoryAssignment, InventoryChangeAuditEvent

DUPLICATE_NAME = "An inventory with this name already exists in this business."


def _lock_manager(user, business_id):
    # Match stock writers: user, membership, assignment, then inventory.
    get_object_or_404(get_user_model().objects.select_for_update(no_key=True), pk=user.pk, is_active=True)
    return get_object_or_404(manager_memberships(user).select_for_update(no_key=True), business_id=business_id)


def _snapshot(inventory):
    return {"name": inventory.name, "is_active": inventory.is_active}


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
def create_inventory(*, user, business_id, name):
    manager = _lock_manager(user, business_id)
    inventory = Inventory(business_id=business_id, name=name.strip())
    _save_inventory(inventory)
    InventoryAssignment.objects.create(membership=manager, inventory=inventory)
    _record_change(user, inventory, InventoryChangeAuditEvent.Action.CREATE, None)


@transaction.atomic
def update_inventory(*, user, inventory, name=None, is_active=None):
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
    if name is not None:
        inventory.name = name.strip()
        action = actions.RENAME
    else:
        inventory.is_active = is_active
        action = actions.REACTIVATE if is_active else actions.DEACTIVATE
    if _snapshot(inventory) != before:
        _save_inventory(inventory)
        _record_change(user, inventory, action, before)
