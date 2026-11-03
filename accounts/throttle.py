"""PostgreSQL-coordinated sliding login-failure limits."""

import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from .models import LoginFailure


WINDOW_SECONDS = 15 * 60
IDENTITY_LIMIT = 5
IP_LIMIT = 20


def _key(kind, value):
    # Purpose-separated HMAC keys avoid storing submitted email or source IP.
    material = f"{kind}:{value}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), material, hashlib.sha256).hexdigest()


def _lock(key):
    # A transaction-scoped PostgreSQL lock works across workers and is released
    # even if authentication raises; a process-local counter would not.
    lock_id = int.from_bytes(bytes.fromhex(key[:16]), "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])


def check_and_authenticate(email, password, ip_address, authenticate):
    """Enforce G-07's independent rolling identity and IP failure limits.

    Locking both keys in stable order makes the count-and-record step atomic
    across workers and avoids opposite-order lock waits. The limit is inclusive:
    the fifth identity or twentieth IP failure is recorded; later attempts are
    denied until the 15-minute window passes. Success does not erase failures.
    """
    identity_key = _key("identity", email.strip().casefold())
    ip_key = _key("ip", ip_address)
    with transaction.atomic():
        for key in sorted((identity_key, ip_key)):
            _lock(key)
        now = timezone.now()
        cutoff = now - timedelta(seconds=WINDOW_SECONDS)
        identity_count = LoginFailure.objects.filter(
            identity_key=identity_key, occurred_at__gt=cutoff
        ).count()
        ip_count = LoginFailure.objects.filter(
            ip_key=ip_key, occurred_at__gt=cutoff
        ).count()
        if identity_count >= IDENTITY_LIMIT or ip_count >= IP_LIMIT:
            return None, True

        user = authenticate(email, password)
        if user is None:
            LoginFailure.objects.create(
                identity_key=identity_key, ip_key=ip_key, occurred_at=now
            )
        return user, False
