"""Reset-specific mail adapter; never return or log a link."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.urls import reverse

from .invitation_email import InvitationDeliveryError, public_origin


class ResetDeliveryError(Exception):
    pass


def delivery_origin():
    try:
        origin = public_origin()
        validate_email(settings.DEFAULT_FROM_EMAIL)
    except (InvitationDeliveryError, ValidationError) as error:
        raise ResetDeliveryError("Reset delivery is unavailable.") from error
    if settings.EMAIL_BACKEND not in {
        "django.core.mail.backends.smtp.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
    }:
        raise ResetDeliveryError("Reset delivery is unavailable.")
    if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and (
        not settings.EMAIL_HOST or not settings.EMAIL_PORT
    ):
        raise ResetDeliveryError("Reset delivery is unavailable.")
    return origin


def send_reset(credentials, origin):
    url = origin + reverse("password-reset-setup") + "#" + credentials.token
    try:
        connection = get_connection(timeout=settings.PASSWORD_RESET_SMTP_TIMEOUT)
        sent = EmailMessage(
            "Reset your Tory password",
            "Use this private link within 30 minutes to set a new password:\n" + url,
            settings.DEFAULT_FROM_EMAIL,
            [credentials.link.user.email],
            connection=connection,
        ).send(fail_silently=False)
        if sent != 1:
            raise ResetDeliveryError("Reset delivery failed.")
    except Exception as error:
        raise ResetDeliveryError("Reset delivery failed.") from error
