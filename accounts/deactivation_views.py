"""Manager-facing Staff list and explicit confirmation flow."""

from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from inventory_access.models import BusinessMembership

from .deactivation import StaffDeactivationRejected, deactivate_staff, visible_staff
from .sessions import protected_view
from .access_errors import account_not_found


def _scoped_staff(request, business_id, target_id=None):
    if not BusinessMembership.objects.filter(
        user_id=request.user.pk, business_id=business_id,
        role=BusinessMembership.Role.MANAGER, is_active=True,
    ).exists():
        raise Http404
    staff = visible_staff(request.user.pk, business_id)
    if target_id is None:
        return staff
    target = next((user for user in staff if user.pk == target_id), None)
    if target is None:
        raise Http404
    return target


@protected_view
@require_GET
@account_not_found
def manager_staff(request, business_id):
    return render(request, "accounts/staff.html", {
        "business_id": business_id, "staff_accounts": _scoped_staff(request, business_id),
    })


@protected_view
@require_GET
@account_not_found
def confirm_staff_deactivation(request, business_id, target_id):
    target = _scoped_staff(request, business_id, target_id)
    return render(request, "accounts/confirm_staff_deactivation.html", {
        "business_id": business_id, "target": target,
    })


@protected_view
@require_POST
@account_not_found
def deactivate_staff_view(request, business_id, target_id):
    _scoped_staff(request, business_id, target_id)
    try:
        deactivate_staff(request.user.pk, business_id, target_id)
    except StaffDeactivationRejected as error:
        raise Http404 from error
    return redirect("manager-staff", business_id=business_id)
