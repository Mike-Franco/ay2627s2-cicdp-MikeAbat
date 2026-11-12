from collections import defaultdict

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import CharField, F, Value
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from accounts.sessions import protected_view
from catalogue.models import InventoryProduct, ProductLifecycleAuditEvent
from inventory_access.authorization import get_authorized_inventory
from inventory_access.models import BusinessMembership, Inventory
from django.utils import timezone
from receiving.models import (DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent,
                              ObservationActivation, ReceiptAuditEvent, StockAdjustmentAuditEvent)
from receiving.services import quarantine_quantity
from receiving.demand import mark_demand_day_incomplete, verify_demand_day
from receiving.forms import DemandCoverageActionForm
from receiving.services import ReceiptRejected

from .authorization import (can_manage_product_lifecycle, visible_inventory_product_links,
                            visible_product_links)
from .forms import ReorderSettingsForm
from .lifecycle import ProductLifecycleRejected, set_product_active
from .reorder import can_edit_shared_settings, recommendation, save_shared_settings


@protected_view
def product_catalogue(request):
    return render(
        request,
        "catalogue/product_catalogue.html",
        {"product_links": visible_product_links(request.user)},
    )


@protected_view
def inventory_products(request, inventory_id):
    try:
        inventory, links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    product_links = list(links.prefetch_related("receiving_batches"))
    now = timezone.now()
    for link in product_links:
        _prepare_stock_link(link, request.user, inventory, now)
    return render(
        request,
        "catalogue/inventory_products.html",
        {"inventory": inventory, "product_links": product_links,
         "can_adjust_stock": _is_inventory_manager(request.user, inventory)},
    )


def _is_inventory_manager(user, inventory):
    return BusinessMembership.objects.filter(
        user=user, business=inventory.business,
        role=BusinessMembership.Role.MANAGER, is_active=True,
        inventory_assignments__inventory=inventory,
        inventory_assignments__is_active=True,
    ).exists()


def _prepare_stock_link(link, user, inventory, now):
    """Display the same expiry-aware balances and reorder state on both pages."""
    link.display_quarantine_units = sum(
        quarantine_quantity(batch, at=now) for batch in link.receiving_batches.all()
    )
    link.display_available_units = link.physical_quantity_units - link.display_quarantine_units
    link.display_physical_units = link.physical_quantity_units
    link.reorder = None
    link.reorder_error = None
    if link.product.is_active:
        try:
            link.reorder = recommendation(
                user_id=user.pk, inventory_id=inventory.pk,
                product_id=link.product_id, at=now,
            )
        except ReceiptRejected as error:
            link.reorder_error = str(error)
        else:
            link.display_quarantine_units = link.reorder.quarantined_units
            link.display_available_units = link.reorder.available_units
            link.display_physical_units = (
                link.reorder.available_units + link.reorder.quarantined_units
            )
    link.can_manage_lifecycle = can_manage_product_lifecycle(user, link.product)


@protected_view
def product_stock(request, inventory_id, product_id):
    try:
        inventory, links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    link = get_object_or_404(links.prefetch_related("receiving_batches"), product_id=product_id)
    now = timezone.now()
    _prepare_stock_link(link, request.user, inventory, now)
    batches = []
    for batch in sorted(link.receiving_batches.all(), key=lambda item: item.receipt_sequence):
        if batch.remaining_quantity_units:
            batches.append({"batch": batch, "quarantined": quarantine_quantity(batch, at=now)})
    return render(request, "catalogue/product_stock.html", {
        "inventory": inventory, "product": link.product, "link": link,
        "batches": batches, "can_adjust_stock": _is_inventory_manager(request.user, inventory),
    })


@protected_view
@require_http_methods(["GET", "POST"])
def product_lifecycle(request, inventory_id, product_id):
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    link = get_object_or_404(
        InventoryProduct.objects.select_related("product"), inventory=inventory,
        product_id=product_id, product__business_id=inventory.business_id,
    )
    if not can_manage_product_lifecycle(request.user, link.product):
        raise Http404
    error_message = None
    if request.method == "POST":
        desired = request.POST.get("action")
        if desired not in ("deactivate", "reactivate"):
            error_message = "Choose a valid product action."
        else:
            try:
                set_product_active(
                    user_id=request.user.pk, inventory_id=inventory_id,
                    product_id=product_id, active=desired == "reactivate",
                )
            except ProductLifecycleRejected as error:
                if str(error) == "This inventory or product is unavailable.":
                    raise Http404 from error
                error_message = str(error)
            else:
                return redirect("inventory-products", inventory_id=inventory_id)
    return render(request, "catalogue/product_lifecycle.html", {
        "inventory": inventory, "product": link.product, "error_message": error_message,
    }, status=400 if error_message else 200)


@protected_view
def stock_history(request, inventory_id, product_id):
    """Show committed audit evidence within one assigned inventory/product."""
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    link = get_object_or_404(
        InventoryProduct.objects.select_related("product"),
        inventory=inventory, product_id=product_id,
        product__business_id=inventory.business_id,
    )
    scope = {"business_id": inventory.business_id,
             "inventory_id": inventory.pk, "product_id": link.product_id}
    audit_sources = {
        "receipt": ReceiptAuditEvent.objects.filter(**scope).select_related("actor", "batch"),
        "issue": DemandAuditEvent.objects.filter(**scope).select_related("actor", "stock_out").prefetch_related(
            "stock_out__allocations__batch"
        ),
        "adjustment": StockAdjustmentAuditEvent.objects.filter(**scope).select_related("actor").prefetch_related(
            "adjustment__allocations__batch"
        ),
        "quarantine": ExpiryQuarantineEvent.objects.filter(**scope).select_related("batch"),
        "disposal": DisposalAuditEvent.objects.filter(**scope).select_related("actor", "batch"),
        "lifecycle": ProductLifecycleAuditEvent.objects.filter(**scope).select_related("actor"),
    }

    def event_keys(kind, timestamp):
        return audit_sources[kind].order_by().annotate(
            event_time=F(timestamp), event_kind=Value(kind, output_field=CharField()),
            event_id=F("id"),
        ).values("event_time", "event_kind", "event_id")

    keys = event_keys("receipt", "occurred_at").union(
        event_keys("issue", "occurred_at"),
        event_keys("adjustment", "occurred_at"),
        event_keys("quarantine", "recorded_at"),
        event_keys("disposal", "occurred_at"),
        event_keys("lifecycle", "occurred_at"),
        all=True,
    ).order_by("-event_time", "-event_kind", "-event_id")
    page = Paginator(keys, 50).get_page(request.GET.get("page"))
    page_keys = list(page.object_list)
    ids_by_kind = defaultdict(list)
    for key in page_keys:
        ids_by_kind[key["event_kind"]].append(key["event_id"])
    audits = {kind: audit_sources[kind].filter(pk__in=ids).in_bulk()
              for kind, ids in ids_by_kind.items()}
    events = [{"kind": key["event_kind"], "audit": audits[key["event_kind"]][key["event_id"]]}
              for key in page_keys]
    return render(request, "catalogue/stock_history.html", {
        "inventory": inventory, "product": link.product, "events": events, "page": page,
    })


@protected_view
@require_http_methods(["GET", "POST"])
def demand_forecast(request, inventory_id, product_id):
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    link = get_object_or_404(
        InventoryProduct.objects.select_related("product"),
        inventory=inventory, product_id=product_id,
        product__business_id=inventory.business_id,
    )
    is_manager = BusinessMembership.objects.filter(
        user=request.user, business=inventory.business,
        role=BusinessMembership.Role.MANAGER, is_active=True,
        inventory_assignments__inventory=inventory,
        inventory_assignments__is_active=True,
    ).exists()
    observation_active = ObservationActivation.objects.filter(
        environment=settings.DJANGO_ENV, state="active",
    ).exists()
    form = DemandCoverageActionForm(request.POST or None)
    if request.method == "POST":
        if not is_manager:
            raise Http404
        if form.is_valid():
            try:
                if form.cleaned_data["action"] == "verify":
                    verify_demand_day(user_id=request.user.pk, inventory_id=inventory_id,
                                      product_id=product_id, day=form.cleaned_data["day"])
                else:
                    mark_demand_day_incomplete(
                        user_id=request.user.pk, inventory_id=inventory_id,
                        product_id=product_id, day=form.cleaned_data["day"],
                        reason=form.cleaned_data["reason"],
                    )
            except ReceiptRejected as error:
                form.add_error(error.field, str(error))
            else:
                return redirect("demand-forecast", inventory_id=inventory_id, product_id=product_id)
    try:
        reorder = recommendation(user_id=request.user.pk, inventory_id=inventory_id,
                                 product_id=product_id)
    except ReceiptRejected as error:
        raise Http404 from error
    return render(request, "catalogue/demand_forecast.html", {
        "inventory": inventory, "product": link.product, "forecast": reorder.forecast,
        "reorder": reorder,
        "form": form, "is_manager": is_manager,
        "observation_active": observation_active,
        "can_edit_reorder": can_edit_shared_settings(request.user, link.product),
    }, status=400 if request.method == "POST" else 200)


@protected_view
@require_http_methods(["GET", "POST"])
def reorder_settings(request, inventory_id, product_id):
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    link = get_object_or_404(
        InventoryProduct.objects.select_related("product"),
        inventory=inventory, product_id=product_id,
        product__business_id=inventory.business_id,
    )
    if not can_edit_shared_settings(request.user, link.product):
        raise Http404
    form = ReorderSettingsForm(request.POST or None, instance=link.product)
    if request.method == "POST" and form.is_valid():
        try:
            save_shared_settings(
                user_id=request.user.pk, inventory_id=inventory_id, product_id=product_id,
                lead_time_days=form.cleaned_data["lead_time_days"],
                safety_stock_units=form.cleaned_data["safety_stock_units"],
            )
        except ReceiptRejected as error:
            form.add_error(error.field if error.field != "__all__" else None, str(error))
        else:
            return redirect("demand-forecast", inventory_id=inventory_id, product_id=product_id)
    return render(request, "catalogue/reorder_settings.html", {
        "inventory": inventory, "product": link.product, "form": form,
    }, status=400 if request.method == "POST" else 200)
