"""Signed-in account page: change password."""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .forms import AccountPasswordChangeForm
from .password_feedback import REQUIREMENTS
from .sessions import protected_view


def end_other_sessions(user, keep_session_key):
    """Delete the user's other unexpired database sessions; return how many ended.

    Django would already reject them on their next request, because each
    session stores a hash of the old password; deleting them makes the
    sign-out immediate and keeps the session table tidy.
    """
    ended = 0
    sessions = Session.objects.filter(expire_date__gt=timezone.now()).exclude(session_key=keep_session_key)
    for session in sessions.iterator():
        if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
            session.delete()
            ended += 1
    return ended


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@protected_view
@require_http_methods(["GET", "POST"])
def account(request):
    form = AccountPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        ended = end_other_sessions(user, request.session.session_key)
        messages.success(request, "Password changed." + (
            f" Signed out {ended} other session{'s' if ended != 1 else ''}." if ended else ""))
        return redirect("account")
    return render(request, "accounts/account.html", {
        "form": form, "password_requirements": REQUIREMENTS,
    }, status=400 if request.method == "POST" else 200)
