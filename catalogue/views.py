from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Case, CharField, F, Q, Sum, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.sessions import protected_view
from catalogue.models import InventoryProduct, Product, ProductLifecycleAuditEvent
from inventory_access.authorization import get_authorized_inventory
from inventory_access.models import BusinessMembership, Inventory
from receiving.demand import (
    _totals,
    forecasts_for_links,
    mark_demand_day_incomplete,
    reviewable_days,
    verify_demand_day,
    verify_demand_days_for_inventory,
)
from receiving.forms import DemandCoverageActionForm
from receiving.models import (
    DemandAuditEvent,
    DisposalAuditEvent,
    ExpiryQuarantineEvent,
    ObservationActivation,
    ReceiptAuditEvent,
    ReceivingBatch,
    StockAdjustmentAuditEvent,
)
from receiving.services import SINGAPORE, ReceiptRejected, quarantine_quantity

from .authorization import (can_manage_product_lifecycle, manageable_lifecycle_product_ids, managed_inventories,
                            visible_inventory_product_links, visible_product_links)
from .csv_exports import csv_download, history_rows, stock_rows
from .forms import BulkDemandVerifyForm, SellingPriceForm, InventoryProductFilterForm, ProductCreateForm, ProductForm, ProductSearchForm, ReorderSettingsForm
from .templatetags.tory_format import sgdate
from .lifecycle import ProductLifecycleRejected, set_product_active
from .product_changes import save_product_change, save_selling_price
from .reorder import can_edit_shared_settings, recommendation, recommendation_from_evidence, save_shared_settings


@protected_view
def inventory_insights(request, inventory_id):
    try:
        inventory, links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    now = timezone.now()
    today = now.astimezone(SINGAPORE).date()
    first_day = today - timedelta(days=29)
    demand = _totals(
        {"business_id": inventory.business_id, "inventory_id": inventory.pk},
        first_day, today + timedelta(days=1),
    )
    forecast_data = forecasts_for_links([link.pk for link in links if link.product.is_active], at=now)
    labels = [first_day + timedelta(days=offset) for offset in range(30)]
    active_link_ids = [link.pk for link in links if link.product.is_active]
    active_forecasts = [forecast_data.get(link_id) for link_id in active_link_ids]
    average = None
    if active_forecasts and all(item and item.available for item in active_forecasts):
        total_average = sum((item.average for item in active_forecasts), start=0)
        average = f"{Decimal(total_average.numerator) / Decimal(total_average.denominator):.2f}"
    demand_data = [
        {"day": day.isoformat(), "issued": demand.get(day, 0), "verified_average": average}
        for day in labels
    ] if links else []
    batch_totals = ReceivingBatch.objects.filter(
        inventory_product__in=links, remaining_quantity_units__gt=0,
    ).order_by().values("inventory_product_id").annotate(
        quarantined=Sum(Case(
            When(expiry_date__lte=today, then=F("remaining_quantity_units")),
            When(expiry_date__gt=today, then=F("quarantined_quantity_units")),
            default=F("quarantined_quantity_units"),
        ), default=0),
    )
    quarantine_by_link = dict(batch_totals.values_list("inventory_product_id", "quarantined"))
    reorder_data = []
    # Selling-price value of available (issuable) stock; unpriced products are listed, not guessed.
    stock_value, priced, unpriced = Decimal(0), 0, []
    for link in links:
        quarantine = quarantine_by_link.get(link.pk, 0)
        forecast = forecast_data.get(link.pk)
        result = None
        if link.product.is_active and forecast and forecast.available:
            result = recommendation_from_evidence(link.product, link.physical_quantity_units, forecast, quarantine)
        reorder_data.append({
            "sku": link.product.sku, "name": link.product.name,
            "available": link.physical_quantity_units - quarantine,
            "reorder_point": str(result.reorder_point) if result and result.reorder_point is not None else None,
            "alert": bool(result and result.alert),
        })
        available = link.physical_quantity_units - quarantine
        if link.selling_price is None:
            unpriced.append(link.product)
        else:
            stock_value += available * link.selling_price
            priced += 1
    # Four rolling 7-day windows starting tomorrow, so stock expiring in the
    # next few days is never dropped by a calendar-week boundary.
    window_start = today + timedelta(days=1)
    week_starts = [window_start + timedelta(days=7 * offset) for offset in range(4)]
    expiry_totals = defaultdict(int)
    expiring = ReceivingBatch.objects.filter(
        inventory_product__in=links, expiry_date__gte=window_start,
        expiry_date__lt=window_start + timedelta(days=28),
        remaining_quantity_units__gt=F("quarantined_quantity_units"),
    ).values("expiry_date", "remaining_quantity_units", "quarantined_quantity_units")
    for batch in expiring:
        index = (batch["expiry_date"] - window_start).days // 7
        expiry_totals[index] += batch["remaining_quantity_units"] - batch["quarantined_quantity_units"]
    expiry_data = [{
        "week": f"{sgdate(start)} – {sgdate(start + timedelta(days=6))}",
        "units": expiry_totals[index],
    } for index, start in enumerate(week_starts)]
    return render(request, "catalogue/inventory_insights.html", {
        "inventory": inventory, "demand_data": demand_data,
        "demand_data_json": demand_data, "reorder_data_json": reorder_data, "expiry_data_json": expiry_data,
        "reorder_data": reorder_data, "expiry_data": expiry_data, "has_products": bool(links),
        "stock_value": stock_value, "priced_count": priced, "unpriced_products": unpriced,
    })


@protected_view
def product_catalogue(request):
    search_form = ProductSearchForm(request.GET)
    valid_search = search_form.is_valid()
    links = _search_product_links(visible_product_links(request.user), search_form.cleaned_data["q"]) if valid_search else []
    page = Paginator(links, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "catalogue/product_catalogue.html",
        {"product_links": page.object_list, "page": page, "search_form": search_form,
         "create_inventories": managed_inventories(request.user).select_related("business")
         .order_by("business_id", "name", "pk").distinct("business_id")},
        status=200 if valid_search else 400,
    )


def _search_product_links(links, query):
    if query:
        return links.filter(Q(product__name__icontains=query) | Q(product__sku__icontains=query))
    return links


@protected_view
@require_http_methods(["GET", "POST"])
def product_create(request, inventory_id):
    inventory = get_object_or_404(managed_inventories(request.user), pk=inventory_id)
    choices = managed_inventories(request.user).filter(business_id=inventory.business_id)
    form = ProductCreateForm(
        request.POST if request.method == "POST" else None, inventories=choices,
        instance=Product(business_id=inventory.business_id), initial={"inventories": [inventory.pk]},
    )
    if request.method == "POST" and form.is_valid():
        inventory_ids = [shelf.pk for shelf in form.cleaned_data["inventories"]]
        try:
            product = save_product_change(user=request.user, inventory=inventory,
                                          values=form.cleaned_data, inventory_ids=inventory_ids)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("product-stock", inventory_id=min(inventory_ids), product_id=product.pk)
    return render(request, "catalogue/product_form.html", {"inventory": inventory, "form": form},
                  status=400 if request.method == "POST" else 200)


@protected_view
@require_http_methods(["GET", "POST"])
def product_edit(request, inventory_id, product_id):
    inventory = get_object_or_404(managed_inventories(request.user), pk=inventory_id)
    link = get_object_or_404(
        InventoryProduct.objects.select_related("product"), inventory=inventory,
        product_id=product_id, product__business_id=inventory.business_id,
    )
    product = link.product
    if not can_manage_product_lifecycle(request.user, product):
        raise Http404
    form = ProductForm(request.POST if request.method == "POST" else None, instance=product)
    if request.method == "POST" and form.is_valid():
        try:
            save_product_change(user=request.user, inventory=inventory,
                                product_id=product.pk, values=form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("product-stock", inventory_id=inventory.pk, product_id=product.pk)
    return render(request, "catalogue/product_form.html", {
        "inventory": inventory, "product": product, "form": form,
    }, status=400 if request.method == "POST" else 200)


@protected_view
def inventory_products(request, inventory_id):
    try:
        inventory, links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    total_product_count = links.count()
    filter_form = InventoryProductFilterForm(request.GET)
    product_links = []
    page = None
    valid_filters = filter_form.is_valid()
    can_adjust_stock = _is_inventory_manager(request.user, inventory)
    if valid_filters:
        links = _search_product_links(links, filter_form.cleaned_data["q"])
        selected_status = filter_form.cleaned_data["reorder"]
        now = timezone.now()
        links = links.annotate(display_quarantine_units=Sum(Case(
            When(receiving_batches__expiry_date__lte=now.astimezone(SINGAPORE).date(),
                 then=F("receiving_batches__remaining_quantity_units")),
            default=F("receiving_batches__quarantined_quantity_units"),
        ), default=0))
        if selected_status:
            links = [link for link in _prepare_stock_list(links, at=now) if _reorder_status(link) == selected_status]
        page = Paginator(links, 25).get_page(request.GET.get("page"))
        product_links = page.object_list if selected_status else _prepare_stock_list(page.object_list, at=now)
        if can_adjust_stock:
            manageable = manageable_lifecycle_product_ids(
                request.user, inventory.business_id, [link.product_id for link in product_links],
            )
            for link in product_links:
                link.can_manage_lifecycle = link.product_id in manageable
    return render(
        request,
        "catalogue/inventory_products.html",
        {"inventory": inventory, "product_links": product_links, "page": page,
         "filter_form": filter_form, "total_product_count": total_product_count,
         "has_filters": bool(request.GET.get("q") or request.GET.get("reorder")),
         "can_adjust_stock": can_adjust_stock},
        status=200 if valid_filters else 400,
    )


def _prepare_stock_list(links, *, at):
    links = list(links)
    forecasts = forecasts_for_links([link.pk for link in links if link.product.is_active], at=at)
    for link in links:
        link.display_physical_units = link.physical_quantity_units
        link.display_available_units = link.physical_quantity_units - link.display_quarantine_units
        link.reorder = None
        if link.product.is_active:
            link.reorder = recommendation_from_evidence(
                link.product, link.physical_quantity_units, forecasts[link.pk], link.display_quarantine_units,
            )
    return links


def _reorder_status(link):
    """Classify only the recommendation state already displayed on the page."""
    if link.reorder is None or link.reorder.reorder_point is None:
        return "unavailable"
    return "attention" if link.reorder.alert else "above"


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
def selling_price(request, inventory_id, product_id):
    """Manager-only edit of one inventory's selling price for a product."""
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    if not _is_inventory_manager(request.user, inventory):
        raise Http404
    link = get_object_or_404(InventoryProduct.objects.select_related("product"), inventory=inventory,
                             product_id=product_id, product__business_id=inventory.business_id)
    form = SellingPriceForm(request.POST or None, initial={"selling_price": link.selling_price})
    if request.method == "POST" and form.is_valid():
        save_selling_price(user=request.user, inventory=inventory, product_id=product_id,
                           price=form.cleaned_data["selling_price"])
        return redirect("product-stock", inventory_id=inventory.pk, product_id=product_id)
    return render(request, "catalogue/selling_price.html", {
        "inventory": inventory, "product": link.product, "link": link, "form": form,
    }, status=400 if request.method == "POST" else 200)


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


def _history_scope(user, inventory_id, product_id):
    try:
        inventory = get_authorized_inventory(user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    link = get_object_or_404(
        InventoryProduct.objects.select_related("product"),
        inventory=inventory, product_id=product_id,
        product__business_id=inventory.business_id,
    )
    scope = {"business_id": inventory.business_id,
             "inventory_id": inventory.pk, "product_id": link.product_id}
    return inventory, link, scope


@protected_view
@require_GET
def export_inventory_stock(request, inventory_id):
    try:
        inventory, links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    return csv_download(
        f"inventory-{inventory.pk}-stock.csv",
        ("SKU", "Product", "Base unit", "Physical", "Quarantined", "Available"),
        stock_rows(links, today=timezone.localdate()),
    )


@protected_view
@require_GET
def export_stock_history(request, inventory_id, product_id):
    inventory, link, scope = _history_scope(request.user, inventory_id, product_id)
    return csv_download(
        f"inventory-{inventory.pk}-product-{link.product_id}-history.csv",
        ("Recorded at (Singapore)", "Action", "Actor", "Physical before", "Physical after", "Reason", "Note"),
        history_rows(scope),
    )


@protected_view
def stock_history(request, inventory_id, product_id):
    """Show committed audit evidence within one assigned inventory/product."""
    inventory, link, scope = _history_scope(request.user, inventory_id, product_id)
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
def bulk_verify_demand(request, inventory_id):
    """Manager action: verify complete Singapore dates for every product at once."""
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    if not _is_inventory_manager(request.user, inventory):
        raise Http404
    now = timezone.now()
    today = now.astimezone(SINGAPORE).date()
    initial = {"scope": BulkDemandVerifyForm.SCOPE_WEEK} if request.GET.get("scope") == "week" else None
    form = BulkDemandVerifyForm(request.POST or None, initial=initial, today=today)
    result = None
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["scope"] == BulkDemandVerifyForm.SCOPE_WEEK:
            days = reviewable_days(now)
        else:
            days = (form.cleaned_data["day"],)
        try:
            result = verify_demand_days_for_inventory(
                user_id=request.user.pk, inventory_id=inventory.pk, days=days, at=now,
            )
        except ReceiptRejected as error:
            form.add_error(None if error.field == "__all__" else "day", str(error))
    return render(request, "catalogue/bulk_verify_demand.html", {
        "inventory": inventory, "form": form, "result": result,
        "window": reviewable_days(now),
    }, status=400 if request.method == "POST" and result is None else 200)


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
