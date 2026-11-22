"""Transactional, delivery-neutral G-07 password-reset core."""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .password_feedback import PasswordFeedbackError, UNSET, validate_new_password

from .models import PasswordResetAttempt, PasswordResetLink
from .throttle import _key, _lock


LIFETIME = timedelta(minutes=30)
WINDOW = timedelta(hours=1)
IDENTITY_LIMIT = 3
IP_LIMIT = 20
ACKNOWLEDGEMENT = "If eligible, instructions will be sent."
TOKEN_PURPOSE = b"tory:password-reset:v1\0"
PASSWORD_FINGERPRINT_SALT = "tory.accounts.password_resets.PasswordFingerprint"


class PasswordResetError(Exception):
    """A safe internal rejection; callers must use generic public feedback."""


class PasswordRejected(PasswordFeedbackError, PasswordResetError):
    """Safe field errors after current token and account checks."""


@dataclass(frozen=True)
class ResetCredentials:
    link: PasswordResetLink = field(repr=False)
    token: str = field(repr=False)


@dataclass(frozen=True)
class ResetRequestResult:
    acknowledgement: str = ACKNOWLEDGEMENT
    credentials: ResetCredentials | None = field(default=None, repr=False)


def _digest(purpose, value):
    return hashlib.sha256(purpose + value.encode("utf-8")).hexdigest()


def _password_fingerprint(user):
    """Keyed fingerprint binding a reset link to the password it was issued for.

    The input is Django's stored password hash, never a plaintext password.
    Like Django's PasswordResetTokenGenerator, it is an HMAC keyed with
    SECRET_KEY and a Tory-specific key_salt, so changing the password
    invalidates the link and the stored value is useless without the key.
    """
    return salted_hmac(PASSWORD_FINGERPRINT_SALT, user.password, algorithm="sha256").hexdigest()


def _normalized_email(value):
    if not isinstance(value, str):
        value = ""
    return get_user_model().objects.normalize_email(value)


def _operation_time(at):
    return at if at is not None else timezone.now()


def request_password_reset(email, source_ip, *, at=None):
    """Count every permitted request; expose one identical public acknowledgement.

    The private credentials property is for a later mail adapter only. The
    rolling hour uses (now - 1 hour, now]; the fourth identity or twenty-first
    IP request is denied. Unknown and inactive identities consume quota too.
    """
    normalized = _normalized_email(email)
    identity_key = _key("reset-identity", normalized)
    ip_key = _key("reset-ip", source_ip if isinstance(source_ip, str) else "")
    with transaction.atomic():
        for key in sorted((identity_key, ip_key)):
            _lock(key)
        user = get_user_model().objects.select_for_update().filter(email__iexact=normalized).first()
        now = _operation_time(at)
        cutoff = now - WINDOW
        if (PasswordResetAttempt.objects.filter(identity_key=identity_key, requested_at__gt=cutoff).count() >= IDENTITY_LIMIT or
                PasswordResetAttempt.objects.filter(ip_key=ip_key, requested_at__gt=cutoff).count() >= IP_LIMIT):
            return ResetRequestResult()
        PasswordResetAttempt.objects.create(identity_key=identity_key, ip_key=ip_key, requested_at=now)
        if user is None or not user.is_active or not user.has_usable_password():
            return ResetRequestResult()
        PasswordResetLink.objects.filter(user=user, status=PasswordResetLink.Status.PENDING).update(
            status=PasswordResetLink.Status.SUPERSEDED
        )
        token = secrets.token_urlsafe(32)
        link = PasswordResetLink.objects.create(
            user=user, token_digest=_digest(TOKEN_PURPOSE, token),
            password_digest=_password_fingerprint(user),
            issued_at=now, expires_at=now + LIFETIME,
        )
        return ResetRequestResult(credentials=ResetCredentials(link, token))


def redeem_password_reset(token, password, *, at=None, confirmation=UNSET):
    """Change password and consume every link in one transaction."""
    if not isinstance(token, str) or not token or len(token) > 256:
        raise PasswordResetError("This reset link cannot be used.")
    digest = _digest(TOKEN_PURPOSE, token)
    seed = PasswordResetLink.objects.filter(token_digest=digest).select_related("user").first()
    if seed is None:
        raise PasswordResetError("This reset link cannot be used.")
    identity_key = _key("reset-identity", _normalized_email(seed.user.email))
    with transaction.atomic():
        _lock(identity_key)
        user = get_user_model().objects.select_for_update().get(pk=seed.user_id)
        link = PasswordResetLink.objects.select_for_update().get(pk=seed.pk)
        now = _operation_time(at)
        if (not user.is_active or not user.has_usable_password() or
                link.status != PasswordResetLink.Status.PENDING or
                link.token_digest != digest or link.expires_at <= now or
                not constant_time_compare(link.password_digest, _password_fingerprint(user))):
            raise PasswordResetError("This reset link cannot be used.")
        validate_new_password(password, user, confirmation, PasswordRejected)
        user.set_password(password)
        user.save(update_fields=["password"])
        consumed_at = _operation_time(at)
        if link.expires_at <= consumed_at:
            raise PasswordResetError("This reset link cannot be used.")
        PasswordResetLink.objects.filter(user=user, status=PasswordResetLink.Status.PENDING).exclude(pk=link.pk).update(
            status=PasswordResetLink.Status.SUPERSEDED
        )
        link.status = PasswordResetLink.Status.REDEEMED
        link.redeemed_at = consumed_at
        link.save(update_fields=["status", "redeemed_at"])
        return user
