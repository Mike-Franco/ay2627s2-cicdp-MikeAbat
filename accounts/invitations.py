"""Transactional core for scoped, single-use Staff invitations.

This module prepares credentials for a future mail integration. It never sends,
prints, or logs raw invitation tokens.
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from inventory_access.models import (
    BusinessMembership,
    Inventory,
    InventoryAssignment,
)

from .models import StaffInvitation, StaffInvitationInventory


INVITATION_LIFETIME = timedelta(hours=24)
INVITATIONS_PER_MANAGER_PER_DAY = 5
SINGAPORE = ZoneInfo("Asia/Singapore")
TOKEN_PURPOSE = b"tory:staff-invitation:v1\0"
IDENTITY_LOCK_PURPOSE = b"tory:staff-invitation-identity:v1\0"


class StaffInvitationError(Exception):
    """A safe service-level rejection; callers should use generic public copy."""


@dataclass(frozen=True)
class StaffInvitationCredentials:
    invitation: StaffInvitation
    token: str = field(repr=False)


def _clean_email(value):
    User = get_user_model()
    try:
        email = User._meta.get_field("email").clean(value, None)
    except (ValidationError, TypeError) as error:
        raise StaffInvitationError("A valid target email is required.") from error
    return User.objects.normalize_email(email)


def _inventory_ids(values):
    try:
        raw_values = list(values)
        if any(isinstance(value, bool) for value in raw_values):
            raise ValueError
        ids = tuple(sorted({int(value) for value in raw_values}))
    except (TypeError, ValueError) as error:
        raise StaffInvitationError("At least one valid inventory is required.") from error
    if not ids or ids[0] < 1:
        raise StaffInvitationError("At least one valid inventory is required.")
    return ids


def _identity_lock(email):
    """Serialize all invitation transitions for a normalized identity in PostgreSQL."""
    lock_bytes = hashlib.sha256(IDENTITY_LOCK_PURPOSE + email.encode("utf-8")).digest()[:8]
    lock_id = int.from_bytes(lock_bytes, "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])


def _locked_manager_scope(manager_id, business_id, inventory_ids, membership_id=None):
    """Lock and recheck the Manager, membership, selected inventories and assignments."""
    User = get_user_model()
    manager = User.objects.select_for_update().filter(pk=manager_id).first()
    if manager is None or not manager.is_active:
        raise StaffInvitationError("Manager is not authorised to invite Staff.")

    memberships = BusinessMembership.objects.select_for_update().filter(
        user_id=manager.pk,
        business_id=business_id,
        role=BusinessMembership.Role.MANAGER,
        is_active=True,
    )
    if membership_id is not None:
        memberships = memberships.filter(pk=membership_id)
    membership = memberships.first()
    if membership is None:
        raise StaffInvitationError("Manager is not authorised to invite Staff.")

    inventories = list(
        Inventory.objects.select_for_update()
        .filter(pk__in=inventory_ids, business_id=business_id, is_active=True)
        .order_by("pk")
    )
    if len(inventories) != len(inventory_ids):
        raise StaffInvitationError("Manager is not authorised for every selected inventory.")

    assignments = list(
        InventoryAssignment.objects.select_for_update()
        .filter(
            membership=membership,
            inventory_id__in=inventory_ids,
            is_active=True,
        )
        .order_by("inventory_id")
    )
    if len(assignments) != len(inventory_ids):
        raise StaffInvitationError("Manager is not authorised for every selected inventory.")
    return manager, membership, inventories


def _account_exists(email):
    User = get_user_model()
    return User.objects.filter(email__iexact=email).exists()


def _pending_for_email(email):
    return list(
        StaffInvitation.objects.select_for_update()
        .filter(target_email__iexact=email, status=StaffInvitation.Status.PENDING)
        .order_by("pk")
    )


def _expire_stale(pending, now):
    current = []
    for invitation in pending:
        if invitation.expires_at <= now:
            invitation.status = StaffInvitation.Status.EXPIRED
            invitation.save(update_fields=["status"])
        else:
            current.append(invitation)
    return current


def _enforce_manager_daily_limit(manager_id, now):
    local_day = timezone.localtime(now, SINGAPORE).date()
    start = timezone.make_aware(datetime.combine(local_day, time.min), SINGAPORE)
    end = start + timedelta(days=1)
    count = StaffInvitation.objects.filter(
        invited_by_id=manager_id,
        issued_at__gte=start,
        issued_at__lt=end,
    ).count()
    if count >= INVITATIONS_PER_MANAGER_PER_DAY:
        raise StaffInvitationError("The Manager invitation limit has been reached for today.")


def _new_invitation(manager, membership, email, inventory_ids, now):
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(TOKEN_PURPOSE + token.encode("utf-8")).hexdigest()
    invitation = StaffInvitation.objects.create(
        target_email=email,
        business_id=membership.business_id,
        manager_membership=membership,
        invited_by=manager,
        token_digest=digest,
        status=StaffInvitation.Status.PENDING,
        issued_at=now,
        expires_at=now + INVITATION_LIFETIME,
    )
    StaffInvitationInventory.objects.bulk_create(
        [
            StaffInvitationInventory(invitation=invitation, inventory_id=inventory_id)
            for inventory_id in inventory_ids
        ]
    )
    return StaffInvitationCredentials(invitation=invitation, token=token)


def _translate_integrity_error(error):
    raise StaffInvitationError("The invitation could not be completed.") from error


def prepare_staff_invitation(manager, *, business_id, target_email, inventory_ids, at=None):
    """Issue the first pending invitation for one target identity and business."""
    email = _clean_email(target_email)
    selected_ids = _inventory_ids(inventory_ids)
    now = at or timezone.now()
    try:
        with transaction.atomic():
            _identity_lock(email)
            manager, membership, _ = _locked_manager_scope(
                getattr(manager, "pk", None), business_id, selected_ids
            )
            if _account_exists(email):
                raise StaffInvitationError("An account already exists for this email.")

            pending = _pending_for_email(email)
            if pending and pending[0].business_id != membership.business_id:
                raise StaffInvitationError("The invitation could not be issued.")
            pending = _expire_stale(pending, now)
            if pending:
                if pending[0].business_id != membership.business_id:
                    raise StaffInvitationError("The invitation could not be issued.")
                raise StaffInvitationError("A pending invitation already exists; replace it to resend.")

            _enforce_manager_daily_limit(manager.pk, now)
            return _new_invitation(manager, membership, email, selected_ids, now)
    except IntegrityError as error:
        _translate_integrity_error(error)


def _invitation_seed(invitation_id):
    try:
        return StaffInvitation.objects.only(
            "pk", "target_email", "business_id", "invited_by_id", "manager_membership_id"
        ).get(pk=invitation_id)
    except StaffInvitation.DoesNotExist as error:
        raise StaffInvitationError("The invitation could not be changed.") from error


def _locked_invitation(invitation_id):
    try:
        return StaffInvitation.objects.select_for_update().get(pk=invitation_id)
    except StaffInvitation.DoesNotExist as error:
        raise StaffInvitationError("The invitation could not be changed.") from error


def replace_staff_invitation(manager, invitation_id, *, inventory_ids=None, at=None):
    """Supersede the current invitation and issue its replacement atomically."""
    seed = _invitation_seed(invitation_id)
    email = seed.target_email
    now = at or timezone.now()
    try:
        with transaction.atomic():
            _identity_lock(email)
            invitation = _locked_invitation(seed.pk)
            if invitation.status != StaffInvitation.Status.PENDING:
                raise StaffInvitationError("The invitation could not be changed.")

            old_ids = _inventory_ids(
                StaffInvitationInventory.objects.select_for_update()
                .filter(invitation=invitation)
                .order_by("inventory_id")
                .values_list("inventory_id", flat=True)
            )
            selected_ids = old_ids if inventory_ids is None else _inventory_ids(inventory_ids)
            scope_ids = tuple(sorted(set(old_ids) | set(selected_ids)))
            actor, membership, _ = _locked_manager_scope(
                getattr(manager, "pk", None), invitation.business_id, scope_ids
            )
            if _account_exists(email):
                raise StaffInvitationError("An account already exists for this email.")

            pending = _pending_for_email(email)
            if len(pending) != 1 or pending[0].pk != invitation.pk:
                raise StaffInvitationError("The invitation could not be changed.")

            _enforce_manager_daily_limit(actor.pk, now)
            invitation.status = (
                StaffInvitation.Status.EXPIRED
                if invitation.expires_at <= now
                else StaffInvitation.Status.SUPERSEDED
            )
            invitation.save(update_fields=["status"])
            return _new_invitation(actor, membership, email, selected_ids, now)
    except IntegrityError as error:
        _translate_integrity_error(error)


def revoke_staff_invitation(manager, invitation_id, *, at=None):
    """Revoke the current invitation if the Manager still controls its scope."""
    seed = _invitation_seed(invitation_id)
    now = at or timezone.now()
    with transaction.atomic():
        _identity_lock(seed.target_email)
        invitation = _locked_invitation(seed.pk)
        if invitation.status != StaffInvitation.Status.PENDING:
            raise StaffInvitationError("The invitation could not be changed.")

        inventory_ids = _inventory_ids(
            StaffInvitationInventory.objects.select_for_update()
            .filter(invitation=invitation)
            .order_by("inventory_id")
            .values_list("inventory_id", flat=True)
        )
        _locked_manager_scope(
            getattr(manager, "pk", None), invitation.business_id, inventory_ids
        )
        pending = _pending_for_email(invitation.target_email)
        if len(pending) != 1 or pending[0].pk != invitation.pk:
            raise StaffInvitationError("The invitation could not be changed.")
        invitation.status = (
            StaffInvitation.Status.EXPIRED
            if invitation.expires_at <= now
            else StaffInvitation.Status.REVOKED
        )
        invitation.save(update_fields=["status"])
        return invitation


def _token_digest(token):
    if not isinstance(token, str) or not token or len(token) > 256:
        raise StaffInvitationError("The invitation is invalid or no longer usable.")
    return hashlib.sha256(TOKEN_PURPOSE + token.encode("utf-8")).hexdigest()


def redeem_staff_invitation(token, password, *, at=None):
    """Consume a current invitation and create its ordinary Staff account atomically."""
    digest = _token_digest(token)
    seed = StaffInvitation.objects.filter(token_digest=digest).only(
        "pk", "target_email", "business_id", "invited_by_id", "manager_membership_id"
    ).first()
    if seed is None:
        raise StaffInvitationError("The invitation is invalid or no longer usable.")

    now = at or timezone.now()
    User = get_user_model()
    try:
        with transaction.atomic():
            _identity_lock(seed.target_email)
            invitation = _locked_invitation(seed.pk)
            if (
                invitation.status != StaffInvitation.Status.PENDING
                or invitation.expires_at <= now
                or invitation.token_digest != digest
            ):
                raise StaffInvitationError("The invitation is invalid or no longer usable.")

            pending = _pending_for_email(invitation.target_email)
            if len(pending) != 1 or pending[0].pk != invitation.pk:
                raise StaffInvitationError("The invitation is invalid or no longer usable.")

            inventory_ids = _inventory_ids(
                StaffInvitationInventory.objects.select_for_update()
                .filter(invitation=invitation)
                .order_by("inventory_id")
                .values_list("inventory_id", flat=True)
            )
            _, membership, inventories = _locked_manager_scope(
                invitation.invited_by_id,
                invitation.business_id,
                inventory_ids,
                membership_id=invitation.manager_membership_id,
            )
            if _account_exists(invitation.target_email):
                raise StaffInvitationError("The invitation is invalid or no longer usable.")

            user = User(
                email=invitation.target_email,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            if not isinstance(password, str) or not password:
                raise StaffInvitationError("A nonblank password is required.")
            try:
                validate_password(password, user)
            except ValidationError as error:
                raise StaffInvitationError("Password does not meet configured requirements.") from error
            user.set_password(password)
            user.save()

            staff_membership = BusinessMembership.objects.create(
                business=membership.business,
                user=user,
                role=BusinessMembership.Role.STAFF,
                is_active=True,
            )
            InventoryAssignment.objects.bulk_create(
                [
                    InventoryAssignment(membership=staff_membership, inventory=inventory)
                    for inventory in inventories
                ]
            )
            invitation.status = StaffInvitation.Status.REDEEMED
            invitation.redeemed_at = now
            invitation.save(update_fields=["status", "redeemed_at"])
            return user
    except IntegrityError as error:
        _translate_integrity_error(error)
