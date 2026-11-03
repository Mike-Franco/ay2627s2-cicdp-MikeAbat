"""Server-checked idle and absolute session deadlines for protected views."""

from functools import wraps

from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone


IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60
CREATED_KEY = "tory_session_created_at"
ACTIVE_KEY = "tory_session_last_activity_at"


def start_session(request):
    """Pin the absolute G-07 clock at login; later activity cannot move it."""
    now = timezone.now().timestamp()
    request.session[CREATED_KEY] = now
    request.session[ACTIVE_KEY] = now
    request.session.set_expiry(ABSOLUTE_SECONDS)


def protected_view(view):
    """Check both G-07 clocks on every decorated protected request.

    Django's cookie expiry alone cannot express a refreshed idle deadline and
    fixed absolute deadline together. Missing timestamps or clock rollback fail
    closed; only a successful protected response refreshes idle activity.
    Future protected views must apply this decorator or equivalent enforcement.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_active:
            # ModelBackend returns AnonymousUser for deactivated accounts but
            # leaves their DB session intact; flush it so reactivation cannot
            # make this old session usable again.
            if request.session.get("_auth_user_id"):
                logout(request)
            return redirect("login")

        now = timezone.now().timestamp()
        created = request.session.get(CREATED_KEY)
        active = request.session.get(ACTIVE_KEY)
        if (
            not isinstance(created, (int, float))
            or not isinstance(active, (int, float))
            or now < created
            or now < active
            or now - created >= ABSOLUTE_SECONDS
            or now - active >= IDLE_SECONDS
        ):
            logout(request)
            return redirect("login")

        response = view(request, *args, **kwargs)
        if response.status_code < 400:
            request.session[ACTIVE_KEY] = now
        return response

    return wrapper
