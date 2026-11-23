from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from django.core.files.storage import default_storage

from accounts.sessions import protected_view
from config.media import store_image
from catalogue.models import InventoryProduct
from catalogue.table_lists import INVENTORY_SORT_CHOICES, INVENTORY_SORTS, TableControls, paginate, prepare_inventory_cards
from django.utils import timezone

from .authorization import (
    authorized_inventories,
    get_authorized_inventory,
    manageable_inventories,
    manager_memberships,
)
from .forms import InventoryForm, InventoryStatusForm
from .inventory_changes import (
    AccessRejected, confirms_name, create_inventory, set_staff_access, staff_access, update_inventory,
)
from .models import BusinessMembership, Inventory


@protected_view
def inventory_list(request):
    managed = manageable_inventories(request.user)
    controls = TableControls.from_request(request, INVENTORY_SORTS, default="name")
    active = authorized_inventories(request.user).select_related("business").annotate(
        can_manage=Exists(managed.filter(pk=OuterRef("pk"))),
    )
    inactive = managed.filter(is_active=False).select_related("business")
    if controls.query:
        active = active.filter(name__icontains=controls.query)
        inactive = inactive.filter(name__icontains=controls.query)
    inventories = list(active) + list(inactive)
    links = list(InventoryProduct.objects.filter(
        inventory_id__in=[inventory.pk for inventory in inventories if inventory.is_active],
    ).select_related("product"))
    page = paginate(request, prepare_inventory_cards(inventories, links, at=timezone.now(), sort=controls.sort))
    return render(request, "inventory_access/inventory_list.html", {
        "inventories": page.object_list, "page": page,
        "toolbar": controls.toolbar(request, page, search_label="Search inventories", sort_choices=INVENTORY_SORT_CHOICES),
        "manager_memberships": manager_memberships(request.user).select_related("business").order_by(
            "business__name", "business_id",
        ),
    })


@protected_view
def inventory_detail(request, inventory_id):
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    return render(request, "inventory_access/inventory_detail.html", {"inventory": inventory})


@protected_view
@require_http_methods(["GET", "POST"])
def inventory_create(request, business_id):
    try:
        manager = manager_memberships(request.user).select_related("business").get(business_id=business_id)
    except BusinessMembership.DoesNotExist as error:
        raise Http404 from error
    form = InventoryForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        picture = _store_picture(form)
        try:
            create_inventory(user=request.user, business_id=business_id, name=form.cleaned_data["name"],
                             icon=form.cleaned_data["icon"], colour=form.cleaned_data["colour"], picture=picture or "")
        except ValidationError as error:
            _discard_picture(picture)
            form.add_error("name", error)
        else:
            messages.success(request, "Inventory added.")
            return redirect("inventory-list")
    return render(request, "inventory_access/inventory_form.html", {"form": form, "business": manager.business},
                  status=400 if request.method == "POST" else 200)


def _store_picture(form):
    content = form.cleaned_data.get("picture_upload")
    return store_image(content, "inventories") if content is not None else None


def _discard_picture(name):
    if name:
        default_storage.delete(name)


@protected_view
@require_http_methods(["GET", "POST"])
def inventory_rename(request, inventory_id):
    inventory = get_object_or_404(
        manageable_inventories(request.user).filter(is_active=True).select_related("business"), pk=inventory_id,
    )
    form = InventoryForm(request.POST or None, request.FILES or None, initial={
        "name": inventory.name, "icon": inventory.icon, "colour": inventory.colour,
    })
    access_error = None
    if request.method == "POST" and form.is_valid():
        picture = _store_picture(form)
        try:
            with transaction.atomic():
                update_inventory(
                    user=request.user, inventory=inventory, name=form.cleaned_data["name"],
                    icon=form.cleaned_data["icon"] or None, colour=form.cleaned_data["colour"] or None,
                    picture=picture if picture else ("" if form.cleaned_data["remove_picture"] else None),
                )
                # TORY-65: the access checklist is saved with the rest of the page. The marker
                # field keeps a name-only submission from removing everyone's access.
                if request.POST.get("access_form") == "1":
                    try:
                        staff_ids = {int(value) for value in request.POST.getlist("staff")}
                    except ValueError as error:
                        raise AccessRejected("Choose Staff from this business only.") from error
                    changes = set_staff_access(user=request.user, inventory=inventory, membership_ids=staff_ids)
        except AccessRejected as error:
            _discard_picture(picture)
            access_error = error.messages[0]
        except ValidationError as error:
            _discard_picture(picture)
            form.add_error("name", error)
        else:
            changed = len(changes) if request.POST.get("access_form") == "1" else 0
            messages.success(request, "Inventory saved." + (
                f" Access changed for {changed} {'person' if changed == 1 else 'people'}." if changed else ""))
            return redirect("inventory-list")
    people = staff_access(inventory)
    if request.method == "POST" and request.POST.get("access_form") == "1":
        chosen = set(request.POST.getlist("staff"))
        for person in people:
            if not person["manager"]:
                person["has_access"] = str(person["membership"].pk) in chosen
    staff_with_access = [person for person in people if person["has_access"] and not person["manager"]]
    return render(request, "inventory_access/inventory_form.html", {
        "form": form, "business": inventory.business, "inventory": inventory, "people": people,
        "access_count": sum(person["has_access"] for person in people), "access_error": access_error,
        "staff_losing_access": len(staff_with_access),
        "product_count": InventoryProduct.objects.filter(inventory=inventory).count(),
        "breadcrumbs": [("Dashboard", reverse("home")), ("All inventories", reverse("inventory-list")),
                        (inventory, reverse("inventory-products", args=[inventory.pk])), ("Edit", None)],
    }, status=400 if request.method == "POST" else 200)


def _deactivation_counts(inventory):
    return {
        "product_count": InventoryProduct.objects.filter(inventory=inventory).count(),
        "staff_losing_access": sum(1 for person in staff_access(inventory)
                                   if person["has_access"] and not person["manager"]),
    }


@protected_view
@require_http_methods(["GET", "POST"])
def inventory_status(request, inventory_id):
    inventory = get_object_or_404(manageable_inventories(request.user).select_related("business"), pk=inventory_id)
    if request.method == "GET":
        # Deactivation is a confirm step reached from the edit page; reactivation
        # stays a one-click action on the list.
        if not inventory.is_active:
            return redirect("inventory-list")
        return render(request, "inventory_access/confirm_inventory_deactivation.html", {
            "inventory": inventory, **_deactivation_counts(inventory),
        })
    if request.POST.get("is_active") not in {"true", "false"}:
        raise Http404
    form = InventoryStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose whether to activate or deactivate the inventory.")
    elif not form.cleaned_data["is_active"] and not confirms_name(inventory, request.POST.get("confirm_name")):
        # TORY-65: deactivating needs the inventory's exact name typed in (case-sensitive, trimmed).
        return render(request, "inventory_access/confirm_inventory_deactivation.html", {
            "inventory": inventory, "confirm_error": f"Type {inventory.name} exactly to confirm.",
            "typed": request.POST.get("confirm_name", ""),
            **_deactivation_counts(inventory),
        }, status=400)
    else:
        active = form.cleaned_data["is_active"]
        update_inventory(user=request.user, inventory=inventory, is_active=active)
        messages.success(request, "Inventory reactivated." if active else "Inventory deactivated.")
    return redirect("inventory-list")
