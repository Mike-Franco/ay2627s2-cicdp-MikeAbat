from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Case, F, Q, Sum, When
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.sessions import protected_view
from catalogue.models import Category, InventoryProduct, Product
from inventory_access.authorization import authorized_inventories, get_authorized_inventory, manager_memberships
from inventory_access.models import BusinessMembership, Inventory
from inventory_access.selection import current_inventory, scope_chip, scope_filter
from receiving.demand import (
    forecasts_for_links,
    mark_demand_day_incomplete,
    reviewable_days,
    verify_demand_day,
    verify_demand_days_for_inventory,
)
from receiving.forms import DemandCoverageActionForm
from receiving.models import ObservationActivation
from receiving.services import SINGAPORE, ReceiptRejected, quarantine_quantity

from .authorization import (can_manage_product_lifecycle, manageable_lifecycle_product_ids, managed_inventories,
                            visible_inventory_product_links, visible_product_links)
from .csv_exports import csv_download, history_rows, stock_rows
from .table_lists import CATALOGUE_SORTS, CATALOGUE_STATUSES, TableControls, catalogue_rows, paginate
from .forms import BulkDemandVerifyForm, SellingPriceForm, InventoryProductFilterForm, ProductCreateForm, ProductForm, ReorderSettingsForm
from .insights import inventory_insights as inventory_insights
from .metrics import STATUS_LABELS, singapore_day, stock_positions
from .product_page import (
    OVERVIEW_HISTORY_ROWS, fefo_batches, history_keys, history_row, history_sources, hydrate_history, outlook, summary,
)
from .lifecycle import ProductLifecycleRejected, set_product_active
from .product_changes import save_product_change, save_selling_price
from .reorder import (ORDER_COVER_DAYS, can_edit_shared_settings, recommendation, recommendation_from_evidence,
                      save_shared_settings)
from .templatetags.tory_format import whole_units


@protected_view
def product_catalogue(request):
    inventories = list(authorized_inventories(request.user))
    categories = list(Category.objects.filter(business_id__in={inventory.business_id for inventory in inventories}))
    categories_by_id = {str(category.pk): category.pk for category in categories}
    inventories_by_id = {str(inventory.pk): inventory.pk for inventory in inventories}
    controls = TableControls.from_request(request, CATALOGUE_SORTS, default="sku")
    links = _search_product_links(visible_product_links(request.user), controls.query)
    category = request.GET.get("category", "")
    # TORY-63: default to the inventory selected in the sidebar; ?scope=all widens to
    # every inventory this user may see (visible_product_links never goes further).
    current = current_inventory(request, inventories)
    inventory, defaulted = scope_filter(request, current)
    inventory = inventory or ""
    status = request.GET.get("status", "")
    valid = len(request.GET.get("q", "")) <= 200 and (not category or category in categories_by_id or category == "uncategorised") and (
        not inventory or inventory in inventories_by_id
    )
    if category:
        links = links.filter(product__category_id=categories_by_id.get(category))
    if inventory in inventories_by_id:
        links = links.filter(inventory_id=inventories_by_id[inventory])
    if status in {"active", "inactive"}:
        links = links.filter(product__is_active=status == "active")
    rows = catalogue_rows(links, at=timezone.now(), status=status, sort=controls.sort) if valid else []
    page = paginate(request, rows)
    toolbar = controls.toolbar(request, page, search_label="Search product name or SKU", filters=(
        ("category", "Category", [("", "All categories"), ("uncategorised", "Uncategorised"),
                                 *((str(item.pk), item.name) for item in categories)]),
        ("status", "Status", CATALOGUE_STATUSES),
        ("inventory", "Inventory", [("", "All inventories"),
                                     *((str(item.pk), item.name) for item in inventories)]),
    ))
    if defaulted:
        for item in toolbar["filters"]:
            if item["key"] == "inventory":
                item["value"] = inventory  # keep the scope when the toolbar is submitted
    all_count = visible_product_links(request.user).values("product_id").distinct().count() if current else 0
    return render(request, "catalogue/product_catalogue.html", {
        "scope": scope_chip(request, current, shown_id=inventory or None, all_count=all_count, noun="products"),
        "product_links": page.object_list, "page": page, "toolbar": toolbar, "valid_filters": valid,
        "breadcrumbs": [("Dashboard", reverse("home")), ("Catalogue", None)],
        "category_managers": manager_memberships(request.user).select_related("business"),
        "create_inventories": managed_inventories(request.user).select_related("business")
        .order_by("business_id", "name", "pk").distinct("business_id"),
    }, status=200 if valid else 400)


def _search_product_links(links, query):
    links = links.select_related("product__category")
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
    all_links = links
    filter_form = InventoryProductFilterForm(
        request.GET, categories=Category.objects.filter(business_id=inventory.business_id),
    )
    product_links = []
    page = None
    valid_filters = filter_form.is_valid()
    can_adjust_stock = _is_inventory_manager(request.user, inventory)
    if valid_filters:
        links = _search_product_links(links, filter_form.cleaned_data["q"])
        if filter_form.cleaned_data["category"]:
            links = links.filter(product__category=filter_form.cleaned_data["category"])
        selected_status = filter_form.cleaned_data["reorder"]
        now = timezone.now()
        links = links.annotate(display_quarantine_units=Sum(Case(
            When(receiving_batches__expiry_date__lte=now.astimezone(SINGAPORE).date(),
                 then=F("receiving_batches__remaining_quantity_units")),
            default=F("receiving_batches__quarantined_quantity_units"),
        ), default=0))
        sort = filter_form.cleaned_data["sort"]
        descending, sort_key = sort.startswith("-"), sort.lstrip("-")
        # Every ordering ends with SKU and id so pages never overlap or skip rows.
        if sort_key == "name":
            name = Lower("product__name")
            links = links.order_by(name.desc() if descending else name.asc(), "product__sku", "pk")
        elif sort_key == "available":
            links = links.annotate(
                sort_available=F("physical_quantity_units") - F("display_quarantine_units"),
            ).order_by(("-" if descending else "") + "sort_available", "product__sku", "pk")
        computed = bool(selected_status) or sort_key == "status"
        if computed:
            links = _prepare_stock_list(links, at=now)
            if selected_status:
                links = [link for link in links if _reorder_status(link) == selected_status]
            if sort_key == "status":
                rank = {"attention": 0, "above": 1, "unavailable": 2}
                links.sort(key=lambda link: ((-1 if descending else 1) * rank[_reorder_status(link)],
                                             link.product.sku, link.pk))
        page = paginate(request, links)
        product_links = page.object_list if computed else _prepare_stock_list(page.object_list, at=now)
        if can_adjust_stock:
            manageable = manageable_lifecycle_product_ids(
                request.user, inventory.business_id, [link.product_id for link in product_links],
            )
            for link in product_links:
                link.can_manage_lifecycle = link.product_id in manageable
    # TORY-68: one notice above the table instead of the same sentence on every row.
    active_ids = list(all_links.filter(product__is_active=True).values_list("pk", flat=True))
    no_forecast_count = sum(1 for forecast in forecasts_for_links(active_ids, at=timezone.now()).values()
                            if not forecast.available)
    return render(
        request,
        "catalogue/inventory_products.html",
        {"inventory": inventory, "product_links": product_links, "page": page,
         "filter_form": filter_form, "total_product_count": total_product_count,
         "has_filters": bool(request.GET.get("q") or request.GET.get("reorder") or request.GET.get("category")),
         "sort": filter_form.cleaned_data.get("sort", "") if valid_filters else "",
         "can_adjust_stock": can_adjust_stock, "no_forecast_count": no_forecast_count},
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
            if link.reorder.missing_settings:
                link.missing_text = f"Set {' and '.join(link.reorder.missing_settings)} to get a reorder point."
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


def can_view_activity_log(user, inventory):
    """Who may open the business Activity log from a product page: Managers and (TORY-67) Staff."""
    return BusinessMembership.objects.filter(user=user, business_id=inventory.business_id, is_active=True).exists()


def _product_header(user, inventory, link, now):
    """Context for the header shared by every product tab (TORY-68): status pill and actions."""
    position = stock_positions([link], at=now)[0]
    link.can_manage_lifecycle = can_manage_product_lifecycle(user, link.product)
    return {
        "link": link, "position": position,
        "status": position.status, "status_label": STATUS_LABELS[position.status],
        "can_adjust_stock": _is_inventory_manager(user, inventory),
        "can_edit_reorder": can_edit_shared_settings(user, link.product),
        "batch_count": link.receiving_batches.filter(remaining_quantity_units__gt=0).count(),
    }


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
    link = get_object_or_404(links.prefetch_related("receiving_batches").select_related("product__category"),
                             product_id=product_id)
    now = timezone.now()
    today = singapore_day(now)
    _prepare_stock_link(link, request.user, inventory, now)
    tab = "batches" if request.GET.get("tab") == "batches" else "overview"
    # TORY-66: Overview shows batches with stock left; the Batches tab also lists used-up ones.
    batches = fefo_batches(link, today=today, now=now, include_empty=tab == "batches")
    batch_page = paginate(request, batches)
    header = _product_header(request.user, inventory, link, now)
    position = header["position"]
    info = summary(position, today=today)
    projection, callout = outlook(position, info, today=today)
    scope = {"business_id": inventory.business_id, "inventory_id": inventory.pk, "product_id": link.product_id}
    sources = history_sources(scope)
    keys = history_keys(sources)
    recent = [history_row(event) for event in hydrate_history(sources, list(keys[:OVERVIEW_HISTORY_ROWS]))]
    return render(request, "catalogue/product_stock.html", {
        **header, "inventory": inventory, "product": link.product, "tab": tab,
        "batches": batch_page.object_list, "page": batch_page,
        "can_view_activity": can_view_activity_log(request.user, inventory),
        "info": info,
        "projection": projection, "callout": callout,
        "recent": recent, "history_count": keys.count(),
        "also_in": [shelf.name for shelf in authorized_inventories(request.user).filter(
            product_links__product_id=link.product_id).exclude(pk=inventory.pk).order_by("name")],
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
    sources = history_sources(scope)
    page = paginate(request, history_keys(sources))
    events = hydrate_history(sources, list(page.object_list))
    return render(request, "catalogue/stock_history.html", {
        **_product_header(request.user, inventory, link, timezone.now()),
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
    now = timezone.now()
    header = _product_header(request.user, inventory, link, now)
    return render(request, "catalogue/demand_forecast.html", {
        **header, "inventory": inventory, "product": link.product, "forecast": reorder.forecast,
        "reorder": reorder, "calc": forecast_calculation(reorder),
        # The strip uses the Overview tab's summary so both tabs always show the same numbers.
        "info": summary(header["position"], today=singapore_day(now)),
        "form": form, "is_manager": is_manager,
        "observation_active": observation_active,
    }, status=400 if request.method == "POST" else 200)


def forecast_calculation(reorder):
    """The real numbers behind the reorder point and suggested order (TORY-68), or None without them."""
    if reorder.reorder_point is None:
        return None
    average, lead = reorder.forecast.average, reorder.lead_time_days
    return {
        "total": int(average * 7), "average": average, "lead": lead, "safety": reorder.safety_stock_units,
        "cover": ORDER_COVER_DAYS, "cover_total": ORDER_COVER_DAYS + lead,
        "point": reorder.reorder_point, "point_units": whole_units(reorder.reorder_point),
        "target": average * (ORDER_COVER_DAYS + lead) + reorder.safety_stock_units,
        "available": reorder.available_units, "suggested": reorder.suggested_units,
    }


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
