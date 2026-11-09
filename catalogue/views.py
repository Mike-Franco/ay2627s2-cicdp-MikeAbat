from collections import defaultdict

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import CharField, F, Value
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from accounts.sessions import protected_view
from catalogue.models import InventoryProduct
from inventory_access.authorization import get_authorized_inventory
from inventory_access.models import BusinessMembership, Inventory
from django.utils import timezone
from receiving.models import (DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent,
                              ObservationActivation, ReceiptAuditEvent, StockAdjustmentAuditEvent)
from receiving.services import quarantine_quantity
from receiving.demand import mark_demand_day_incomplete, seven_day_forecast, verify_demand_day
from receiving.forms import DemandCoverageActionForm
from receiving.services import ReceiptRejected

from .authorization import visible_inventory_product_links, visible_product_links


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
        link.display_quarantine_units = sum(
            quarantine_quantity(batch, at=now) for batch in link.receiving_batches.all()
        )
        link.display_available_units = link.physical_quantity_units - link.display_quarantine_units
    return render(
        request,
        "catalogue/inventory_products.html",
        {"inventory": inventory, "product_links": product_links,
         "can_adjust_stock": BusinessMembership.objects.filter(
             user=request.user, business=inventory.business,
             role=BusinessMembership.Role.MANAGER, is_active=True,
             inventory_assignments__inventory=inventory,
             inventory_assignments__is_active=True,
         ).exists()},
    )


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
        forecast = seven_day_forecast(user_id=request.user.pk, inventory_id=inventory_id,
                                      product_id=product_id)
    except ReceiptRejected as error:
        raise Http404 from error
    return render(request, "catalogue/demand_forecast.html", {
        "inventory": inventory, "product": link.product, "forecast": forecast,
        "form": form, "is_manager": is_manager,
        "observation_active": observation_active,
    }, status=400 if request.method == "POST" else 200)
