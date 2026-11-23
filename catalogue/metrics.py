"""Read-only inventory metrics in units and retail SGD, for already-scoped product links."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from statistics import median

from django.db.models import F, Sum
from django.db.models.functions import TruncDate

from receiving.demand import _totals, forecasts_for_links, reviewable_days
from receiving.models import (
    DemandAuditEvent, DemandCoverageEvent, DisposalAuditEvent, ReceiptAuditEvent, ReceivingBatch, StockAdjustmentAuditEvent,
)
from receiving.services import SINGAPORE

from .reorder import recommendation_from_evidence


STATUS_LABELS = {
    "healthy": "Healthy", "low": "Low stock", "out": "Out of stock",
    "expiring": "Expiring within 7 days", "quarantined": "Quarantined",
}


def singapore_day(at):
    return at.astimezone(SINGAPORE).date()


def complete_days(at, count):
    today = singapore_day(at)
    return tuple(today - timedelta(days=offset) for offset in range(count, 0, -1))


def week_start(day):
    return day - timedelta(days=day.weekday())


def ratio(numerator, denominator):
    return Decimal(numerator) / Decimal(denominator) if denominator else None


def days_of_supply(available, forecast):
    if forecast is None:
        return None, "The product is inactive."
    if not forecast.available:
        return None, forecast.reason
    if not forecast.average:
        return None, "Verified average demand is zero."
    return ratio(available * forecast.average.denominator, forecast.average.numerator), ""


def retail_value(available, price):
    return None if price is None else available * price


def status_bucket(*, active, available, reorder_point, expiring, quarantined):
    # Each row belongs to exactly one bucket for value totals.
    if quarantined:
        return "quarantined"
    if active and available == 0:
        return "out"
    if expiring:
        return "expiring"
    if active and reorder_point is not None and available <= reorder_point:
        return "low"
    return "healthy"


@dataclass(frozen=True)
class StockPosition:
    link: object
    quarantined: int
    expiring: int
    reorder: object
    supply: Decimal | None
    supply_reason: str

    @property
    def available(self):
        return self.link.physical_quantity_units - self.quarantined

    @property
    def out(self):
        return self.link.product.is_active and self.available == 0

    @property
    def low(self):
        return bool(self.reorder and self.reorder.alert and not self.out)

    @property
    def value(self):
        return retail_value(self.available, self.link.selling_price)

    @property
    def status(self):
        return status_bucket(
            active=self.link.product.is_active, available=self.available,
            reorder_point=self.reorder.reorder_point if self.reorder else None,
            expiring=self.expiring, quarantined=self.quarantined,
        )


def stock_positions(links, *, at):
    today = singapore_day(at)
    expiry_limit = today + timedelta(days=7)
    batches = ReceivingBatch.objects.filter(
        inventory_product_id__in=[link.pk for link in links], remaining_quantity_units__gt=0,
    ).values_list("inventory_product_id", "expiry_date", "remaining_quantity_units", "quarantined_quantity_units")
    quarantine = Counter()
    expiry = Counter()
    for pk, day, remaining, held in batches.iterator(chunk_size=2000):
        quarantine[pk] += remaining if day is not None and day <= today else held
        if day is not None and today < day <= expiry_limit:
            expiry[pk] += remaining - held
    forecasts = forecasts_for_links([link.pk for link in links if link.product.is_active], at=at)
    positions = []
    for link in links:
        held = quarantine[link.pk]
        forecast = forecasts.get(link.pk)
        reorder = recommendation_from_evidence(link.product, link.physical_quantity_units, forecast, held) if forecast else None
        supply, reason = days_of_supply(link.physical_quantity_units - held, forecast)
        positions.append(StockPosition(link, held, expiry[link.pk], reorder, supply, reason))
    return positions


@dataclass
class DailyMovement:
    received: int = 0
    issued: int = 0
    adjusted: int = 0
    disposed: int = 0

    @property
    def net(self):
        return self.received - self.issued + self.adjusted - self.disposed


MOVEMENTS = (
    (ReceiptAuditEvent, "received", "quantity_change_units"),
    (DemandAuditEvent, "issued", "quantity_change_units"),
    (StockAdjustmentAuditEvent, "adjusted", "quantity_change_units"),
    (DisposalAuditEvent, "disposed", "quantity_units"),
)


def daily_movements(links, *, start, at):
    """Fetch daily physical movements and gross issue/receipt units in four grouped queries."""
    ids = {(link.inventory_id, link.product_id): link.pk for link in links}
    if not ids:
        return {}
    since = datetime.combine(start, time.min, SINGAPORE)
    scope = {
        "business_id": F("inventory__business_id"),
        "inventory_id__in": {inventory for inventory, _ in ids},
        "product_id__in": {product for _, product in ids},
        "occurred_at__gte": since, "occurred_at__lte": at,
    }
    grouped = defaultdict(dict)
    for model, field, units_field in MOVEMENTS:
        rows = model.objects.filter(**scope).order_by().annotate(
            day=TruncDate("occurred_at", tzinfo=SINGAPORE),
        ).values("inventory_id", "product_id", "day").annotate(
            units=Sum(units_field),
        ).values_list("inventory_id", "product_id", "day", "units")
        for inventory, product, day, units in rows.iterator(chunk_size=2000):
            pk = ids.get((inventory, product))
            if pk is not None:
                movement = grouped[pk].setdefault(day, DailyMovement())
                setattr(movement, field, units)
    return grouped


def daily_on_hand(current, net_by_day, days, *, today):
    """Rewind from current stock to each complete day-end, including today's partial movements."""
    balance = current - net_by_day.get(today, 0)
    values = []
    for day in reversed(days):
        values.append(balance)
        balance -= net_by_day.get(day, 0)
    return tuple(reversed(values))


def stock_to_sales(current_on_hand, issued):
    return ratio(current_on_hand, issued)


def turnover(issued, balances):
    return ratio(issued * len(balances), sum(balances))


def movement_metrics(positions, movements, *, at, days=30):
    days = complete_days(at, days)
    today = singapore_day(at)
    net = Counter()
    sales = Counter()
    for position in positions:
        for day, movement in movements.get(position.link.pk, {}).items():
            net[day] += movement.net
            sales[day] += movement.issued
    current = sum(position.link.physical_quantity_units for position in positions)
    issued = sum(sales[day] for day in days)
    balances = daily_on_hand(current, net, days, today=today)
    return stock_to_sales(current, issued), turnover(issued, balances)


def verified_demand(link_ids, dates, *, at):
    """{(link id, day): units} for product-days whose latest coverage event is a
    verification that still matches the recorded issues. Unverified days are absent."""
    if not link_ids or not dates:
        return {}
    latest = DemandCoverageEvent.objects.filter(
        coverage_day__inventory_product_id__in=link_ids, coverage_day__day__in=dates,
    ).order_by("coverage_day_id", "-pk").distinct("coverage_day_id").values_list(
        "coverage_day__inventory_product_id", "coverage_day__day", "action", "verified_total_units",
    )
    verified = {(link_id, day): total for link_id, day, action, total in latest if action == "verified"}
    if not verified:
        return {}
    group = "stock_out__inventory_product_id"
    observed = _totals(
        {f"{group}__in": {link_id for link_id, _ in verified}}, min(dates), singapore_day(at), group_by=(group,),
    )
    return {key: total for key, total in verified.items() if total == observed.get(key, 0)}


def _unverified_pairs(positions, *, at):
    """(link id -> inventory id, unverified (link id, day) pairs), or None before activation."""
    dates = reviewable_days(at)
    if not dates:
        return None
    links = {position.link.pk: position.link.inventory_id for position in positions if position.reorder is not None}
    pending = {(link_id, day) for link_id in links for day in dates}
    pending.difference_update(verified_demand(list(links), dates, at=at))
    return links, pending


def unverified_summary(positions, *, at):
    """(unverified product-days per inventory, demand tasks per inventory) from one query.

    The counts are None before demand observation is activated; every
    inventory with products is a key. A task (TORY-63) lists the dates that
    still need verifying and how many products wait on them.
    """
    result = _unverified_pairs(positions, at=at)
    if result is None:
        return None, {}
    links, pending = result
    counts = Counter({inventory_id: 0 for inventory_id in links.values()})
    days, products = defaultdict(set), defaultdict(set)
    for link_id, day in pending:
        counts[links[link_id]] += 1
        days[links[link_id]].add(day)
        products[links[link_id]].add(link_id)
    tasks = {inventory_id: {"days": sorted(dates), "products": len(products[inventory_id])}
             for inventory_id, dates in days.items()}
    return counts, tasks


def unverified_days(positions, *, at):
    """Unverified product-days per inventory, or None before activation."""
    return unverified_summary(positions, at=at)[0]


def kpis(positions, *, turnover_30d, unverified):
    supplies = [position.supply for position in positions if position.supply is not None]
    values = [position.value for position in positions if position.value is not None]
    unpriced = len(positions) - len(values)
    return [
        {"label": "Out of stock", "value": sum(position.out for position in positions),
         "description": "Active inventory products with zero available units."},
        {"label": "Low stock", "value": sum(position.low for position in positions),
         "description": "Active inventory products with stock at or below their verified reorder point."},
        {"label": "Median days of supply", "value": median(supplies) if supplies else None, "format": "days",
         "description": "Median of available units divided by verified seven-day average daily demand."},
        {"label": "Retail stock value", "value": sum(values, Decimal(0)), "format": "currency",
         "note": f"{unpriced} without a selling price",
         "description": "Available units multiplied by each inventory product’s selling price in SGD."},
        {"label": "Turnover (30d)", "value": turnover_30d, "format": "decimal",
         "description": "Units issued divided by average day-end on-hand units over 30 complete Singapore days."},
        {"label": "Unverified demand days", "value": sum(unverified.values()) if unverified is not None else None,
         "description": "Active product-days in the reviewable demand window without verified coverage."},
    ]


# Forecast accuracy (TORY-64) -------------------------------------------------
# Each point is (forecast units, verified actual units) for one product-day.
MIN_ACCURACY_POINTS = 3


def _percent(value):
    value = Fraction(value) * 100
    return Decimal(value.numerator) / Decimal(value.denominator)


def mape(points):
    """Mean absolute percentage error over points with non-zero actual demand (a % of zero is undefined)."""
    usable = [(Fraction(forecast), actual) for forecast, actual in points if actual]
    if not usable:
        return None, 0
    total = sum(abs(forecast - actual) / actual for forecast, actual in usable)
    return _percent(total / len(usable)), len(usable)


def wape(points):
    """Weighted absolute percentage error: sum of absolute errors / sum of actual demand."""
    points = [(Fraction(forecast), actual) for forecast, actual in points]
    actual = sum(actual for _, actual in points)
    if not points or not actual:
        return None, len(points)
    return _percent(sum(abs(forecast - actual) for forecast, actual in points) / actual), len(points)


def forecast_accuracy(points):
    """MAPE when at least three non-zero days exist, else the WAPE fallback; None below three points.

    Returns {"value": percent or None, "method": "MAPE" | "WAPE" | None, "points": n}.
    """
    points = list(points)
    value, used = mape(points)
    if value is not None and used >= MIN_ACCURACY_POINTS:
        return {"value": value, "method": "MAPE", "points": used}
    value, used = wape(points)
    if value is not None and used >= MIN_ACCURACY_POINTS:
        return {"value": value, "method": "WAPE", "points": used}
    return {"value": None, "method": None, "points": len(points)}


def accuracy_points(links, *, at):
    """Pair last week's 7-day forecast (made seven days ago) with each verified day since."""
    link_ids = [link.pk for link in links if link.product.is_active]
    week_ago = at - timedelta(days=7)
    forecasts = {pk: forecast for pk, forecast in forecasts_for_links(link_ids, at=week_ago).items()
                 if forecast.available}
    dates = complete_days(at, 7)
    actual = verified_demand(list(forecasts), dates, at=at)
    return [(forecasts[link_id].average, units) for (link_id, _), units in sorted(actual.items())]
