"""Scoped Manager controls and public Staff password setup."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from catalogue.pagination import paginate
from inventory_access.models import BusinessMembership, Inventory
from .invitation_email import InvitationDeliveryError, ensure_delivery_ready, send_invitation
from .invitations import (StaffInvitationError, prepare_staff_invitation,
                          replace_staff_invitation, revoke_staff_invitation,
                          redeem_staff_invitation)
from .models import StaffInvitation, StaffInvitationInventory
from .sessions import protected_view
from .password_feedback import PasswordFeedbackError, REQUIREMENTS
from .access_errors import account_not_found


def _scope(request, business_id):
    membership = BusinessMembership.objects.filter(
        user=request.user, business_id=business_id,
        role=BusinessMembership.Role.MANAGER, is_active=True,
    ).first()
    if membership is None:
        raise Http404
    inventories = Inventory.objects.filter(
        business_id=business_id, is_active=True,
        assignments__membership=membership, assignments__is_active=True,
    ).distinct()
    if not inventories.exists():
        raise Http404
    return inventories


def _visible_invitation(request, business_id, invitation_id, inventories):
    allowed = inventories.values_list("pk", flat=True)
    invitation = StaffInvitation.objects.filter(
        pk=invitation_id, business_id=business_id,
        inventory_links__inventory_id__in=allowed,
    ).distinct().first()
    if invitation is None:
        raise Http404
    linked = set(invitation.inventories.values_list("pk", flat=True))
    if not linked or not linked.issubset(set(allowed)):
        raise Http404
    return invitation


def _deliver_after_commit(request, credentials, origin):
    def deliver():
        try:
            send_invitation(credentials, origin)
        except InvitationDeliveryError:
            # The pending record remains eligible for an authorised replacement.
            messages.error(request, "Delivery failed. An authorised Manager can replace the invitation.")
    transaction.on_commit(deliver)


@protected_view
@require_http_methods(["GET", "POST"])
@account_not_found
def manager_invitations(request, business_id):
    inventories = _scope(request, business_id)
    error = None
    if request.method == "POST":
        try:
            origin = ensure_delivery_ready()
            credentials = prepare_staff_invitation(
                request.user, business_id=business_id,
                target_email=request.POST.get("email", ""),
                inventory_ids=request.POST.getlist("inventories"),
            )
            _deliver_after_commit(request, credentials, origin)
            messages.success(request, "Invitation prepared. Delivery may take time; replace it if delivery fails.")
            return redirect("staff-invitations", business_id=business_id)
        except (StaffInvitationError, InvitationDeliveryError):
            error = "Invitation could not be issued. Check the selection and delivery configuration."
    links = StaffInvitationInventory.objects.filter(invitation_id=OuterRef("pk"))
    allowed = inventories.values("pk")
    invitations = StaffInvitation.objects.filter(
        Exists(links), ~Exists(links.exclude(inventory_id__in=allowed)), business_id=business_id,
    ).prefetch_related("inventories").order_by("-issued_at", "-pk")
    page = paginate(request, invitations)
    return render(request, "accounts/invitations.html", {
        "inventories": inventories, "invitations": page.object_list, "page": page,
        "business_id": business_id, "error": error,
    })


@protected_view
@require_POST
@account_not_found
def change_invitation(request, business_id, invitation_id, action):
    inventories = _scope(request, business_id)
    _visible_invitation(request, business_id, invitation_id, inventories)
    try:
        if action == "replace":
            origin = ensure_delivery_ready()
            selected = request.POST.getlist("inventories")
            credentials = replace_staff_invitation(
                request.user, invitation_id,
                inventory_ids=selected if selected else None,
            )
            _deliver_after_commit(request, credentials, origin)
            messages.success(request, "Replacement prepared. Delivery may take time.")
        elif action == "revoke":
            revoke_staff_invitation(request.user, invitation_id)
            messages.success(request, "Invitation revoked.")
        else:
            raise Http404
    except (StaffInvitationError, InvitationDeliveryError):
        messages.error(request, "Invitation could not be changed.")
    return redirect("staff-invitations", business_id=business_id)


@never_cache
@sensitive_post_parameters("token", "password", "password_confirm")
@require_http_methods(["GET", "POST"])
def staff_invitation_setup(request):
    if request.method == "POST":
        try:
            redeem_staff_invitation(request.POST.get("token", ""), request.POST.get("password", ""),
                                    confirmation=request.POST.get("password_confirm", ""))
            result = {"ok": True, "sign_in_url": reverse("login")}
        except PasswordFeedbackError as error:
            result = {"ok": False, "error": "Check the password fields below.", "errors": error.errors}
        except StaffInvitationError:
            result = {"ok": False, "error": "This link cannot be used. Request a new invitation."}
        response = JsonResponse(result)
    else:
        response = render(request, "accounts/invitation_setup.html", {
            "public_auth_page": True, "password_requirements": REQUIREMENTS})
    response["Referrer-Policy"] = "no-referrer"
    response["Cache-Control"] = "no-store"
    return response
