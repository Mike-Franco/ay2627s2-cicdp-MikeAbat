from collections import defaultdict

from django.db.models import Case, CharField, Exists, F, OuterRef, Value, When
from django.db.models.functions import Coalesce, Lower, NullIf
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.access_errors import account_not_found
from accounts.deactivation_views import _scoped_staff
from accounts.invitation_views import _scope, manager_invitations
from accounts.models import StaffInvitation, StaffInvitationInventory
from accounts.sessions import protected_view
from catalogue.table_lists import TableControls, paginate, search_rows

from .models import InventoryAssignment


STAFF_SORTS = {
    # Display name first (TORY-55), then the legacy first name.
    "name": Lower(Coalesce(NullIf("display_name", Value("")), "first_name")), "email": Lower("email"),
    "status": "is_active", "last_login": F("last_login"),
}
STAFF_STATUSES = (("", "All statuses"), ("active", "Active"), ("inactive", "Inactive"))
INVITATION_SORTS = {
    "email": Lower("target_email"), "status": "display_status", "sent": "issued_at", "expires": "expires_at",
}
INVITATION_STATUSES = (("", "All statuses"), *StaffInvitation.Status.choices)


def team_breadcrumbs(business_id, current):
    """Dashboard / Team / <page> (TORY-68). Team opens the Staff list."""
    return [("Dashboard", reverse("home")), ("Team", reverse("manager-staff", args=[business_id])), (current, None)]


def _staff_inventories(request, business_id, accounts):
    allowed = InventoryAssignment.objects.filter(
        is_active=True, membership__user=request.user, membership__is_active=True,
        membership__business_id=business_id, inventory__is_active=True,
    ).values("inventory_id")
    assignments = InventoryAssignment.objects.filter(
        is_active=True, membership__business_id=business_id,
        membership__user_id__in=[account.pk for account in accounts], inventory_id__in=allowed,
    ).select_related("inventory", "membership").order_by("inventory__name", "inventory_id")
    inventories = defaultdict(list)
    for assignment in assignments:
        inventories[assignment.membership.user_id].append(assignment.inventory)
    for account in accounts:
        account.assigned_inventories = inventories[account.pk]


@protected_view
@require_GET
@account_not_found
def staff_list(request, business_id):
    staff = _scoped_staff(request, business_id)
    controls = TableControls.from_request(request, STAFF_SORTS, default="email")
    staff = search_rows(staff, controls.query, "email", "first_name", "last_name", "display_name", "job_title")
    status = request.GET.get("status")
    if status in ("active", "inactive"):
        staff = staff.filter(is_active=status == "active")
    ordering = [controls.order(STAFF_SORTS)]
    if controls.sort.removeprefix("-") == "name":
        last = Lower("last_name")
        ordering.append(last.desc() if controls.sort.startswith("-") else last.asc())
    page = paginate(request, staff.order_by(*ordering, "pk"))
    accounts = list(page.object_list)
    _staff_inventories(request, business_id, accounts)
    return render(request, "accounts/staff.html", {
        "business_id": business_id, "staff_accounts": accounts, "page": page,
        "breadcrumbs": team_breadcrumbs(business_id, "Staff"),
        "toolbar": controls.toolbar(request, page, search_label="Search name, email or job title",
                                    filters=(("status", "Status", STAFF_STATUSES),)),
    })


@protected_view
@require_http_methods(["GET", "POST"])
@account_not_found
def invitation_list(request, business_id):
    if request.method == "POST":
        return manager_invitations(request, business_id)
    inventories = _scope(request, business_id)
    links = StaffInvitationInventory.objects.filter(invitation_id=OuterRef("pk"))
    invitations = StaffInvitation.objects.filter(
        Exists(links), ~Exists(links.exclude(inventory_id__in=inventories.values("pk"))), business_id=business_id,
    ).annotate(display_status=Case(
        When(status=StaffInvitation.Status.PENDING, expires_at__lte=timezone.now(),
             then=Value(StaffInvitation.Status.EXPIRED)),
        default=F("status"), output_field=CharField(),
    ))
    controls = TableControls.from_request(request, INVITATION_SORTS, default="-sent")
    invitations = search_rows(invitations, controls.query, "target_email")
    status = request.GET.get("status")
    if status in StaffInvitation.Status.values:
        invitations = invitations.filter(display_status=status)
    secondary = "-pk" if controls.sort == "-sent" else "pk"
    page = paginate(request, invitations.order_by(controls.order(INVITATION_SORTS), secondary))
    return render(request, "accounts/invitations.html", {
        "business_id": business_id, "inventories": inventories, "invitations": page.object_list, "page": page,
        "breadcrumbs": team_breadcrumbs(business_id, "Invitations"), "now": timezone.now(),
        "toolbar": controls.toolbar(request, page, search_label="Search email",
                                    filters=(("status", "Status", INVITATION_STATUSES),)),
    })
