"""Opt-in mail adapter; never log or return a redeemable URL."""

from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse


class InvitationDeliveryError(Exception):
    pass


def public_origin():
    origin = settings.STAFF_INVITATION_PUBLIC_ORIGIN.strip()
    parsed = urlsplit(origin)
    localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path or
            parsed.query or parsed.fragment or parsed.scheme not in {"http", "https"} or
            (parsed.scheme == "http" and not (settings.DJANGO_ENV == "development" and localhost))):
        raise InvitationDeliveryError("Invitation delivery is unavailable.")
    return origin.rstrip("/")


def ensure_delivery_ready():
    origin = public_origin()
    backend = settings.EMAIL_BACKEND
    if backend not in {
        "django.core.mail.backends.smtp.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
    }:
        raise InvitationDeliveryError("Invitation delivery is unavailable.")
    try:
        validate_email(settings.DEFAULT_FROM_EMAIL)
    except ValidationError:
        raise InvitationDeliveryError("Invitation delivery is unavailable.")
    if backend.endswith("smtp.EmailBackend") and (not settings.EMAIL_HOST or not settings.EMAIL_PORT):
        raise InvitationDeliveryError("Invitation delivery is unavailable.")
    return origin


def send_invitation(credentials, origin):
    url = origin + reverse("staff-invitation-setup") + "#" + credentials.token
    try:
        sent = EmailMessage(
            "Set up your Tory Staff account",
            "Use this private link within 24 hours to set your password:\n" + url,
            settings.DEFAULT_FROM_EMAIL,
            [credentials.invitation.target_email],
        ).send(fail_silently=False)
        if sent != 1:
            raise InvitationDeliveryError("Invitation delivery failed.")
    except Exception as error:
        raise InvitationDeliveryError("Invitation delivery failed.") from error
