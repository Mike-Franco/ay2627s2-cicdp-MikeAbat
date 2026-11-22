"""Signed-in account page: own profile (TORY-55) and password change."""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.sessions.models import Session
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from config.media import delete_image_after_commit, store_image
from inventory_access.models import BusinessMembership, InventoryAssignment

from .forms import AccountPasswordChangeForm, ProfileForm
from .models import User
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
    return _render_account(request, password_form=form, status=400 if request.method == "POST" else 200)


@protected_view
@require_http_methods(["POST"])
def account_profile(request):
    """Save the signed-in user's own profile. There is no way to name another user."""
    # A fresh row, so an invalid submission never leaks into request.user
    # (the sidebar would otherwise show the rejected values).
    user = User.objects.get(pk=request.user.pk)
    form = ProfileForm(request.POST, request.FILES, instance=user)
    if not form.is_valid():
        return _render_account(request, profile_form=form, status=400)
    with transaction.atomic():
        user = form.save(commit=False)
        old_photo = user.photo.name
        new_photo = form.cleaned_data["photo_upload"]
        if new_photo is not None:
            user.photo.name = store_image(new_photo, "avatars")
            delete_image_after_commit(old_photo)
        elif form.cleaned_data["remove_photo"]:
            user.photo.name = ""
            delete_image_after_commit(old_photo)
        user.save(update_fields=["display_name", "job_title", "phone", "avatar_colour", "photo"])
    messages.success(request, "Profile saved.")
    return redirect("account")


def _render_account(request, *, password_form=None, profile_form=None, status=200):
    user = request.user
    memberships = list(BusinessMembership.objects.filter(user=user, is_active=True).select_related("business")
                       .order_by("business__name", "pk"))
    assigned = (InventoryAssignment.objects.filter(membership__in=memberships, is_active=True,
                                                   inventory__is_active=True)
                .select_related("inventory").order_by("inventory__name", "pk"))
    return render(request, "accounts/account.html", {
        "form": password_form or AccountPasswordChangeForm(user),
        "profile_form": profile_form or ProfileForm(instance=user),
        "password_requirements": REQUIREMENTS,
        "memberships": memberships,
        "assigned_inventories": [assignment.inventory for assignment in assigned],
    }, status=status)
