"""Inventory Insights (TORY-64): KPI strip, four charts with text equivalents, two paged tables.

Every number has a "?" help tip (includes/help_tip.html) whose wording comes
from docs/ui-reference/v1.2/mockup/Insights.dc.html. ``?range=7d|30d|90d``
sets the period for the charts and the movement KPIs; ``?export=csv`` downloads
the two tables.
"""

import math
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from statistics import median

from django.db.models import F
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.sessions import protected_view
from inventory_access.models import Inventory
from receiving.demand import _totals
from receiving.models import ReceivingBatch
from receiving.services import SINGAPORE

from .authorization import visible_inventory_product_links
from .csv_exports import csv_download
from .metrics import (
    STATUS_LABELS, accuracy_points, daily_movements, forecast_accuracy, movement_metrics, singapore_day,
    stock_positions, verified_demand, week_start,
)
from .pagination import PER_PAGE_CHOICES, SMALL_PER_PAGE_CHOICES, paginate
from .templatetags.tory_format import one_decimal, sgd, sgdate, whole_units

RANGES = {"7d": 7, "30d": 30, "90d": 90}
DEFAULT_RANGE = "30d"
COVER_DAYS = 30  # a full "Cover" bar in the ranking means a month of stock
CHART_PRODUCTS = 20  # the stock-vs-reorder chart shows the most urgent products first

HELP = {
    "value": ("What is stock value?", "Stock value",
              "Available quantity × selling price, summed over every active product in {inventory}. "
              "Quarantined and expired units are left out. The change compares on-hand units at today's prices "
              "with the start of the period.", ""),
    "turnover": ("What is turnover?", "Turnover",
                 "Units issued ÷ average units on hand over the period. Higher means stock moves faster.",
                 "0.39× means about 39% of average stock was used in the period."),
    "supply": ("What is days of supply?", "Days of supply",
               "How long current stock lasts at the verified average daily demand. Median across products.", ""),
    "accuracy": ("What is forecast accuracy?", "Forecast accuracy (MAPE)",
                 "Average % gap between last week's 7-day forecast and verified demand. Lower is better. "
                 "Unverified days are not counted. Days with zero demand are skipped, because a percentage of zero "
                 "is undefined; if fewer than 3 days are left, Tory shows the weighted error instead "
                 "(total gap ÷ total demand, WAPE).", ""),
    "stock": ("About this chart", "Stock vs reorder point",
              "Bars show available units per product. The tick is the reorder point: when a bar drops below its "
              "tick, the product shows as Low stock.", "Oat Milk: 4 on hand, reorder at 12."),
    "traffic": ("About this chart", "Intake vs outtake",
                "Units received (stock in) and units issued or sold (stock out) per week. When outtake stays above "
                "intake, stock is running down.", ""),
    "breakdown": ("About this chart", "Stock value breakdown",
                  "Share of {value} by category, or by stock status. Use it to see where money is tied up.", ""),
    "demand": ("About this chart", "Daily demand and forecast",
               "Solid line: demand per day, all products. Dashed line: the next 7 days predicted from that "
               "history. Hollow dots are days not yet verified, so the forecast ignores them.",
               "Verify them on the Verify demand page."),
    "ranking": ("About this table", "Days of supply ranking",
                "Products ordered by how soon they run out at current demand. Anything under its lead time should "
                "be reordered now.", ""),
    "expiring": ("About this table", "Expiring stock by week",
                 "Batches that reach their expiry date in each of the next weeks, with the value at risk. Issue "
                 "these first (FEFO).", ""),
}


def parse_range(value):
    """Accept 7d/30d/90d (or 7/30/90); anything else falls back to 30 days."""
    value = (value or "").strip().lower()
    if value.isdigit():
        value += "d"
    return value if value in RANGES else DEFAULT_RANGE


def _help(key, **values):
    label, title, text, example = HELP[key]
    return {"id": f"tip-{key}", "label": label, "title": title, "text": text.format(**values), "example": example}


def _decimal(value):
    if value is None:
        return None
    value = Fraction(value)
    return Decimal(value.numerator) / Decimal(value.denominator)


# Charts ----------------------------------------------------------------------

def reorder_rows(positions):
    """Available units against the reorder point, below-reorder products first."""
    rows = []
    for position in positions:
        if not position.link.product.is_active:
            continue
        point = position.reorder.reorder_point if position.reorder else None
        rows.append({
            "sku": position.link.product.sku, "name": position.link.product.name, "available": position.available,
            "reorder_point": whole_units(point), "below": point is not None and position.available <= point,
        })
    rows.sort(key=lambda row: (not row["below"], row["sku"]))
    return rows[:CHART_PRODUCTS]


def traffic_series(ids, movements, *, at, days=30):
    """Units received and issued per Monday-start Singapore week covering the period (at least two weeks)."""
    if not ids:
        return []
    weeks = max(2, math.ceil(days / 7))
    start = week_start(singapore_day(at)) - timedelta(weeks=weeks - 1)
    intake, outtake = Counter(), Counter()
    for pk in ids:
        for day, row in movements.get(pk, {}).items():
            if day >= start:
                intake[week_start(day)] += row.received
                outtake[week_start(day)] += row.issued
    return [{"week": (start + timedelta(weeks=index)).isoformat(),
             "received": intake[start + timedelta(weeks=index)], "issued": outtake[start + timedelta(weeks=index)]}
            for index in range(weeks)]


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
    grand = sum(totals.values(), Decimal(0))
    return [{"label": label, "value": str(value),
             "share": int((value / grand * 100).quantize(Decimal(1))) if grand else 0}
            for label, value in sorted(totals.items(), key=lambda item: -item[1])]


def demand_series(inventory, positions, *, today, at, days=30):
    """Daily units issued with a verified flag, then a dashed 7-day forecast from the verified averages."""
    if not positions:
        return [], []
    start = today - timedelta(days=days - 1)
    issued = _totals({"business_id": inventory.business_id, "inventory_id": inventory.pk},
                     start, today + timedelta(days=1))
    active = [position.link.pk for position in positions if position.reorder is not None]
    complete = [start + timedelta(days=offset) for offset in range(days - 1)]  # today is not complete yet
    verified = Counter(day for _, day in verified_demand(active, complete, at=at))
    history = [{"day": (start + timedelta(days=offset)).isoformat(),
                "issued": issued.get(start + timedelta(days=offset), 0),
                "verified": bool(active) and verified[start + timedelta(days=offset)] == len(active)}
               for offset in range(days)]
    averages = [position.reorder.forecast.average for position in positions
                if position.reorder is not None and position.reorder.forecast.available]
    if not averages:
        return history, []
    daily = f"{_decimal(sum(averages)):.2f}"
    forecast = [{"day": (today + timedelta(days=offset)).isoformat(), "forecast": daily} for offset in range(1, 8)]
    return history, forecast


# Tables ----------------------------------------------------------------------

def ranking_rows(inventory, positions, *, most_first=False):
    ranked = sorted((position for position in positions if position.supply is not None),
                    key=lambda position: (position.supply, position.link.pk), reverse=most_first)
    rows = []
    for rank, position in enumerate(ranked, start=1):
        product = position.link.product
        cover = min(int(position.supply * 100 / COVER_DAYS), 100)
        rows.append({
            "rank": rank, "product": product, "sku": product.sku, "available": position.available,
            "average": position.reorder.forecast.displayed_average if position.reorder else None,
            "days": one_decimal(position.supply), "cover": cover - cover % 5,
            "urgent": product.lead_time_days is not None and position.supply < product.lead_time_days,
            "url": reverse("product-stock", args=[inventory.pk, product.pk]),
        })
    return rows


def _week_label(index):
    return {0: "This week", 1: "Next week"}.get(index, f"In {index + 1} weeks")


def expiring_rows(inventory, links, *, today):
    """Eligible (not quarantined) batches expiring in the next four weeks, earliest first."""
    start = today + timedelta(days=1)
    prices = {link.pk: link.selling_price for link in links}
    batches = ReceivingBatch.objects.filter(
        inventory=inventory, expiry_date__gte=start, expiry_date__lt=start + timedelta(days=28),
        remaining_quantity_units__gt=F("quarantined_quantity_units"),
    ).select_related("product").order_by("expiry_date", "pk")
    rows = []
    for batch in batches:
        units = batch.remaining_quantity_units - batch.quarantined_quantity_units
        price = prices.get(batch.inventory_product_id)
        rows.append({
            "week": _week_label((batch.expiry_date - start).days // 7), "product": batch.product,
            "batch": f"#{batch.receipt_sequence}", "units": units,
            "value": units * price if price is not None else None, "expires": batch.expiry_date,
            "url": reverse("product-stock", args=[inventory.pk, batch.product_id]),
        })
    return rows


def _export(inventory, ranking, expiring, *, at):
    stamp = at.astimezone(SINGAPORE).strftime("%Y%m%d-%H%M")
    header = ("Table", "SKU", "Product", "Units", "Average per day", "Days left", "Week", "Expires (Asia/Singapore)",
              "Value at risk (SGD)")
    rows = [("Days of supply ranking", row["sku"], row["product"].name, row["available"], row["average"] or "",
             row["days"], "", "", "") for row in ranking]
    rows += [("Expiring stock by week", row["product"].sku, row["product"].name, row["units"], "", "", row["week"],
              row["expires"].isoformat(), "" if row["value"] is None else f"{row['value']:.2f}") for row in expiring]
    return csv_download(f"tory-insights-{inventory.pk}-{stamp}.csv", header, rows)


# View ------------------------------------------------------------------------

def _data_card(request, key, title, headers, rows, *, text_columns=1, empty):
    page = paginate(request, rows, prefix=f"{key}_", default=10, fragment=key)
    return {"key": key, "title": title, "headers": headers, "page": page, "text_columns": text_columns,
            "empty": empty, "has_data": bool(rows)}


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
    range_key = parse_range(request.GET.get("range"))
    days = RANGES[range_key]
    grouping = request.GET.get("value_by", "category")
    if grouping not in ("status", "category"):
        grouping = "category"
    most_first = request.GET.get("supply_sort") == "most"

    positions = stock_positions(links, at=at)
    start = min(today - timedelta(days=days), week_start(today) - timedelta(weeks=max(2, math.ceil(days / 7)) - 1))
    movements = daily_movements(links, start=start, at=at)
    _, turnover = movement_metrics(positions, movements, at=at, days=days)
    period_start = today - timedelta(days=days)
    priced = [position for position in positions if position.value is not None]
    stock_value = sum((position.value for position in priced), Decimal(0))
    value_change = sum((position.link.selling_price * sum(
        movement.net for day, movement in movements.get(position.link.pk, {}).items() if day > period_start)
        for position in priced), Decimal(0))
    supplies = [position.supply for position in positions if position.supply is not None]
    accuracy = forecast_accuracy(accuracy_points(links, at=at))

    ranking = ranking_rows(inventory, positions, most_first=most_first)
    expiring = expiring_rows(inventory, links, today=today)
    if request.GET.get("export") == "csv":
        return _export(inventory, ranking, expiring, at=at)

    reorder = reorder_rows(positions)
    traffic = traffic_series([link.pk for link in links], movements, at=at, days=days)
    value = value_series(positions, grouping)
    history, forecast = demand_series(inventory, positions, today=today, at=at, days=days)
    unpriced = [position.link.product for position in positions if position.value is None]
    cards = [
        _data_card(request, "stock", "Stock vs reorder point", ("SKU", "Product", "Available", "Reorder point"),
                   [(row["sku"], row["name"], row["available"], row["reorder_point"]) for row in reorder],
                   text_columns=2, empty="No active products are linked to this inventory."),
        _data_card(request, "traffic", "Intake vs outtake", ("Week starting", "Units received", "Units issued"),
                   [(sgdate(row["week"]), row["received"], row["issued"]) for row in traffic],
                   empty="No receipts or issues were recorded in this period."),
        _data_card(request, "value", "Stock value breakdown",
                   ("Category" if grouping == "category" else "Status", "Retail value", "Share"),
                   [(row["label"], sgd(row["value"]), f"{row['share']}%") for row in value],
                   empty="No available stock has a selling price."),
        _data_card(request, "demand", "Daily demand and forecast", ("Singapore date", "Units issued", "Verified"),
                   [(sgdate(row["day"]), row["issued"], "Yes" if row["verified"] else "No") for row in history]
                   + [(sgdate(row["day"]), f"{row['forecast']} (forecast)", "") for row in forecast],
                   empty="No linked products or issue data are available yet."),
    ]
    for card in cards:
        card["help"] = _help("breakdown" if card["key"] == "value" else card["key"], value=sgd(stock_value))
    cards[0]["has_data"] = bool(reorder)
    cards[1]["has_data"] = any(row["received"] or row["issued"] for row in traffic)
    cards[2]["has_data"] = any(Decimal(row["value"]) > 0 for row in value)
    cards[3]["has_data"] = any(row["issued"] for row in history) or bool(forecast)

    query = request.GET.copy()
    for key in ("range", "export", "page"):
        query.pop(key, None)
    range_links = []
    for key in RANGES:
        query["range"] = key
        range_links.append({"key": key, "url": "?" + query.urlencode(), "current": key == range_key})
    export_query = request.GET.copy()
    export_query["export"] = "csv"
    group_query = request.GET.copy()
    group_links = []
    for key, label in (("category", "Category"), ("status", "Status")):
        group_query["value_by"] = key
        group_links.append({"key": key, "label": label, "url": "?" + group_query.urlencode() + "#value",
                            "current": key == grouping})
    sort_query = request.GET.copy()
    sort_query.pop("supply_page", None)

    return render(request, "catalogue/inventory_insights.html", {
        "inventory": inventory, "as_of": at, "as_of_iso": at.isoformat(timespec="seconds"),
        "range_key": range_key, "range_days": days, "range_links": range_links,
        "export_url": "?" + export_query.urlencode(), "group_links": group_links, "grouping": grouping,
        "most_first": most_first, "sort_hidden": [(k, v) for k, vs in sort_query.lists() if k != "supply_sort" for v in vs],
        "kpis": [
            {"key": "value", "label": "Stock value", "value": sgd(stock_value),
             "note": f"{'+' if value_change >= 0 else '−'}{sgd(abs(value_change))} vs {days}d ago",
             "help": _help("value", inventory=inventory.name)},
            {"key": "turnover", "label": "Turnover",
             "value": "—" if turnover is None else f"{_decimal(turnover):.2f}×", "note": f"{days}-day",
             "help": _help("turnover")},
            {"key": "supply", "label": "Median days of supply",
             "value": "—" if not supplies else one_decimal(median(supplies)), "note": "days",
             "help": _help("supply")},
            {"key": "accuracy", "label": "Forecast accuracy",
             "value": "—" if accuracy["value"] is None else f"{accuracy['value']:.0f}%",
             "note": ("Not enough verified data" if accuracy["value"] is None
                      else f"{accuracy['method']} error, last 7 days"),
             "help": _help("accuracy")},
        ],
        "cards": cards,
        "ranking_page": paginate(request, ranking, prefix="supply_", default=5, choices=SMALL_PER_PAGE_CHOICES,
                                 fragment="ranking"),
        "expiring_page": paginate(request, expiring, prefix="expiry_", default=10, choices=PER_PAGE_CHOICES,
                                  fragment="expiring"),
        "ranking_help": _help("ranking"), "expiring_help": _help("expiring"),
        "stock_data_json": reorder, "traffic_data_json": traffic, "value_data_json": value,
        "demand_data_json": history, "forecast_data_json": forecast,
        "stock_value": stock_value, "unpriced_products": unpriced,
    })
