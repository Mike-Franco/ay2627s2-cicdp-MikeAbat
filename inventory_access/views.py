from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.sessions import protected_view
from catalogue.models import InventoryProduct
from catalogue.table_lists import INVENTORY_SORT_CHOICES, INVENTORY_SORTS, TableControls, paginate, prepare_inventory_cards
from django.utils import timezone

from .authorization import (
    authorized_inventories,
    get_authorized_inventory,
    manageable_inventories,
    manager_memberships,
)
from .forms import InventoryNameForm, InventoryStatusForm
from .inventory_changes import create_inventory, update_inventory
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
    form = InventoryNameForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            create_inventory(user=request.user, business_id=business_id, name=form.cleaned_data["name"])
        except ValidationError as error:
            form.add_error("name", error)
        else:
            messages.success(request, "Inventory added.")
            return redirect("inventory-list")
    return render(request, "inventory_access/inventory_form.html", {"form": form, "business": manager.business},
                  status=400 if request.method == "POST" else 200)


@protected_view
@require_http_methods(["GET", "POST"])
def inventory_rename(request, inventory_id):
    inventory = get_object_or_404(
        manageable_inventories(request.user).filter(is_active=True).select_related("business"), pk=inventory_id,
    )
    form = InventoryNameForm(request.POST if request.method == "POST" else None, initial={"name": inventory.name})
    if request.method == "POST" and form.is_valid():
        try:
            update_inventory(user=request.user, inventory=inventory, name=form.cleaned_data["name"])
        except ValidationError as error:
            form.add_error("name", error)
        else:
            messages.success(request, "Inventory name saved.")
            return redirect("inventory-list")
    return render(request, "inventory_access/inventory_form.html", {
        "form": form, "business": inventory.business, "inventory": inventory,
    }, status=400 if request.method == "POST" else 200)


@protected_view
@require_POST
def inventory_status(request, inventory_id):
    inventory = get_object_or_404(manageable_inventories(request.user), pk=inventory_id)
    if request.POST.get("is_active") not in {"true", "false"}:
        raise Http404
    form = InventoryStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose whether to activate or deactivate the inventory.")
    else:
        active = form.cleaned_data["is_active"]
        update_inventory(user=request.user, inventory=inventory, is_active=active)
        messages.success(request, "Inventory reactivated." if active else "Inventory deactivated.")
    return redirect("inventory-list")
