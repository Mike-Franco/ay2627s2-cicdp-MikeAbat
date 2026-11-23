"""Inventory-scoped chart data and text equivalents."""

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import F
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.sessions import protected_view
from inventory_access.models import Inventory
from receiving.demand import _totals
from receiving.models import ReceivingBatch

from .authorization import visible_inventory_product_links
from .metrics import (
    STATUS_LABELS, complete_days, daily_movements, daily_on_hand, kpis, movement_metrics, singapore_day,
    stock_positions, unverified_days, week_start,
)
from .templatetags.tory_format import one_decimal, sgdate, sgd, whole_units


def stock_series(position, history, *, at):
    if position is None:
        return []
    days = complete_days(at, 30)
    balances = daily_on_hand(position.link.physical_quantity_units,
                             {day: row.net for day, row in history.items()}, days, today=singapore_day(at))
    reorder = position.reorder.reorder_point if position.reorder else None
    return [
        {"day": day.isoformat(), "on_hand": balance,
         "reorder_point": whole_units(reorder),
         "safety_stock": position.link.product.safety_stock_units}
        for day, balance in zip(days, balances, strict=True)
    ]


def traffic_series(ids, movements, *, at):
    current_week = week_start(singapore_day(at))
    start = current_week - timedelta(weeks=7)
    intake = Counter()
    outtake = Counter()
    for pk in ids:
        for day, row in movements.get(pk, {}).items():
            if day >= start:
                monday = week_start(day)
                intake[monday] += row.received
                outtake[monday] += row.issued
    return [
        {"week": (start + timedelta(weeks=index)).isoformat(),
         "received": intake[start + timedelta(weeks=index)],
         "issued": outtake[start + timedelta(weeks=index)]}
        for index in range(8)
    ] if ids else []


def supply_series(positions):
    ranked = sorted((position for position in positions if position.supply is not None),
                    key=lambda position: (position.supply, position.link.pk))
    return [
        {"sku": row.link.product.sku, "name": row.link.product.name, "days": float(one_decimal(row.supply))}
        for row in ranked[:10]
    ]


def value_series(positions, grouping):
    totals = defaultdict(Decimal)
    if grouping == "category":
        for row in positions:
            if row.value is not None:
                category = row.link.product.category
                label = category.name if category else "Uncategorised"
                if category and label.casefold() == "uncategorised":
                    label = f"{label} (category)"
                totals[label] += row.value
    else:
        for status in STATUS_LABELS.values():
            totals[status] = Decimal(0)
        for row in positions:
            if row.value is not None:
                totals[STATUS_LABELS[row.status]] += row.value
    return [{"label": label, "value": str(value)} for label, value in totals.items()]


def _demand_series(inventory, positions, today):
    if not positions:
        return []
    start = today - timedelta(days=29)
    demand = _totals({"business_id": inventory.business_id, "inventory_id": inventory.pk},
                     start, today + timedelta(days=1))
    forecasts = [row.reorder.forecast for row in positions if row.reorder is not None]
    average = None
    if forecasts and all(forecast.available for forecast in forecasts):
        total = sum(forecast.average for forecast in forecasts)
        average = f"{Decimal(total.numerator) / Decimal(total.denominator):.2f}"
    return [
        {"day": day.isoformat(), "issued": demand.get(day, 0), "verified_average": average}
        for day in (start + timedelta(days=offset) for offset in range(30))
    ]


def _expiry_series(inventory, today):
    start = today + timedelta(days=1)
    eligible = Counter()
    batches = ReceivingBatch.objects.filter(
        inventory=inventory, expiry_date__gte=start, expiry_date__lt=start + timedelta(days=28),
        remaining_quantity_units__gt=F("quarantined_quantity_units"),
    ).values_list("expiry_date", "remaining_quantity_units", "quarantined_quantity_units")
    for date, units, quarantined in batches.iterator(chunk_size=2000):
        eligible[(date - start).days // 7] += units - quarantined
    return [
        {"week": f"{sgdate(day)} – {sgdate(day + timedelta(days=6))}", "units": eligible[index]}
        for index, day in enumerate(start + timedelta(weeks=offset) for offset in range(4))
    ]


def _control(request, key, label, choices, value):
    return {
        "key": key, "label": label, "choices": choices, "value": value,
        "hidden": [(name, item) for name, values in request.GET.lists()
                   if name != key for item in values],
    }


def _card(key, title, explanation, headers, rows, *, empty, has_data=None, control=None):
    return {
        "key": key, "title": title, "shows": explanation[0], "read": explanation[1], "action": explanation[2],
        "headers": headers, "rows": rows, "empty": empty, "has_data": bool(rows) if has_data is None else has_data,
        "control": control,
    }


def _chart_cards(request, *, product_choices, product, category_choices, category, grouping, datasets):
    stock, traffic, supply, value, demand, expiry = datasets
    return [
        _card(
            "stock", "Stock level vs reorder point",
            ("Daily closing on-hand stock for the last 30 complete Singapore dates, with today's reorder point and safety stock.",
             "Compare the stock line with the two current reference levels.",
             "Check available stock and open the forecast when stock approaches the reorder point."),
            ("Singapore date", "On hand", "Reorder point", "Safety stock"),
            [
                (sgdate(row["day"]), row["on_hand"],
                 row["reorder_point"], row["safety_stock"])
                for row in stock
            ],
            empty="No products are linked to this inventory.",
            control=_control(request, "product", "Product", product_choices, product),
        ),
        _card(
            "traffic", "Weekly intake vs outtake",
            ("Units received and issued across eight Singapore weeks, including the current partial week.",
             "Compare the two bars within each Monday-start week.",
             "Investigate weeks when issued units repeatedly exceed receipts."),
            ("Week starting", "Units received", "Units issued"),
            [(sgdate(row["week"]), row["received"], row["issued"]) for row in traffic],
            has_data=any(row["received"] or row["issued"] for row in traffic),
            empty="No receipts or issues were recorded for this selection in the last eight weeks.",
            control=_control(request, "category", "Category", category_choices, category),
        ),
        _card(
            "supply", "Days of supply ranking",
            ("Up to ten active products with the least stock cover at their verified seven-day rate.",
             "The shortest bars have the fewest days of stock left, and zero means no available units.",
             "Review the shortest-cover products first, then verify demand for products missing from the ranking."),
            ("SKU", "Product", "Days of supply"),
            [(row["sku"], row["name"], one_decimal(row["days"])) for row in supply],
            empty="No active products have a verified, nonzero demand rate.",
        ),
        _card(
            "value", "Retail stock value breakdown",
            ("Available units valued at this inventory's selling prices, grouped by status or category.",
             "Larger slices represent more retail value, and products without prices are excluded.",
             "Review the largest groups and fill in missing selling prices before using the total."),
            (("Category" if grouping == "category" else "Status"), "Retail value"),
            [(row["label"], sgd(row["value"])) for row in value],
            has_data=any(Decimal(row["value"]) > 0 for row in value),
            empty="No available stock has a positive selling-price value.",
            control=_control(request, "value_by", "Group by", [("status", "Status"), ("category", "Category")], grouping),
        ),
        _card(
            "demand", "Daily units issued",
            ("Recorded daily issues for 30 Singapore dates and the verified seven-day average when available.",
             "Compare daily peaks and gaps with the flat average line.",
             "Verify complete demand dates before relying on the average or reorder point."),
            ("Singapore date", "Units issued", "Verified seven-day average"),
            [(sgdate(row["day"]), row["issued"], row["verified_average"]) for row in demand],
            has_data=any(row["issued"] or row["verified_average"] is not None for row in demand),
            empty="No linked products or issue data are available yet.",
        ),
        _card(
            "expiry", "Eligible units expiring each week",
            ("Available units with expiry dates in the next four rolling Singapore weeks.",
             "Each bar covers seven dates starting tomorrow and omits quarantined stock.",
             "Review near-term batches and prioritise eligible stock with the earliest expiry."),
            ("Singapore week", "Eligible units"),
            [(row["week"], row["units"]) for row in expiry],
            has_data=any(row["units"] for row in expiry),
            empty="No eligible stock is recorded as expiring in the next four weeks.",
        ),
    ]


@protected_view
@require_GET
def inventory_insights(request, inventory_id):
    try:
        inventory, links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    links = list(links.select_related("product__category"))
    at = timezone.now()
    today = singapore_day(at)
    positions = stock_positions(links, at=at)
    selected_id = request.GET.get("product", str(links[0].product_id) if links else "")
    by_product = {str(position.link.product_id): position for position in positions}
    selected = by_product.get(selected_id)
    if selected_id and selected is None:
        raise Http404

    categories = {str(link.product.category_id): link.product.category.name for link in links if link.product.category_id}
    category = request.GET.get("category", "")
    if category not in ("", "uncategorised") and category not in categories:
        raise Http404
    selected_links = [
        link.pk for link in links if not category
        or (category == "uncategorised" and not link.product.category_id)
        or str(link.product.category_id) == category
    ]
    grouping = request.GET.get("value_by", "status")
    if grouping not in ("status", "category"):
        grouping = "status"

    start = week_start(today) - timedelta(weeks=7)
    movements = daily_movements(links, start=start, at=at)
    _, turnover = movement_metrics(positions, movements, at=at)
    unverified = unverified_days(positions, at=at)
    stock = stock_series(selected, movements.get(selected.link.pk, {}) if selected else {}, at=at)
    traffic = traffic_series(selected_links, movements, at=at)
    supply = supply_series(positions)
    value = value_series(positions, grouping)
    demand = _demand_series(inventory, positions, today)
    expiry = _expiry_series(inventory, today)

    product_choices = [(str(link.product_id), f"{link.product.sku} · {link.product.name}") for link in links]
    category_choices = [("", "All categories"), ("uncategorised", "Uncategorised"),
                        *sorted(categories.items(), key=lambda item: (item[1].casefold(), item[0]))]
    cards = _chart_cards(
        request, product_choices=product_choices, product=selected_id, category_choices=category_choices,
        category=category, grouping=grouping, datasets=(stock, traffic, supply, value, demand, expiry),
    )
    priced = [row.value for row in positions if row.value is not None]
    unpriced = [row.link.product for row in positions if row.value is None]
    reorder = [
        {"sku": row.link.product.sku, "name": row.link.product.name, "available": row.available,
         "reorder_point": whole_units(row.reorder.reorder_point) if row.reorder else None,
         "alert": bool(row.reorder and row.reorder.alert)}
        for row in positions
    ]
    return render(request, "catalogue/inventory_insights.html", {
        "inventory": inventory, "as_of": at, "as_of_iso": at.isoformat(timespec="seconds"), "cards": cards,
        "kpi_cards": kpis(positions, turnover_30d=turnover, unverified=unverified),
        "stock_data_json": stock, "traffic_data_json": traffic, "supply_data_json": supply, "value_data_json": value,
        "demand_data_json": demand, "expiry_data_json": expiry, "reorder_data_json": reorder,
        "stock_value": sum(priced, Decimal(0)), "priced_count": len(priced), "unpriced_products": unpriced,
    })
