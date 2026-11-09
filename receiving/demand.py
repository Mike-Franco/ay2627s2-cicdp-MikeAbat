"""Verified Singapore-day demand from committed issue audit evidence."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone as utc_timezone
from decimal import Decimal
from fractions import Fraction

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from inventory_access.models import BusinessMembership

from .commit_times import finalize_stock_import, tracking_enabled
from .models import (DemandAuditEvent, DemandCoverageDay, DemandCoverageEvent,
                     ObservationActivation, StockImport)
from .services import ReceiptRejected, SINGAPORE, _lock_authorized_scope


@dataclass(frozen=True)
class ForecastResult:
    available: bool
    reason: str
    days: tuple
    average: Fraction | None = None
    displayed_average: str | None = None


def _today(at=None):
    return (at or timezone.now()).astimezone(SINGAPORE).date()


def _activation():
    return ObservationActivation.objects.filter(
        environment=settings.DJANGO_ENV, state="active",
    ).order_by("-pk").first()


def _pending_imports(link):
    return StockImport.objects.filter(
        observation_eligible=True, stockout__inventory_product=link,
    ).exclude(commit_attribution="resolved").distinct()


def _resolve_pending(link):
    for import_id in _pending_imports(link).filter(commit_attribution="pending").values_list("pk", flat=True):
        finalize_stock_import(import_id)
    return _pending_imports(link).exists()


def verify_demand_day(*, user_id, inventory_id, product_id, day, at=None):
    with transaction.atomic():
        _, _, _, product, inventory, link = _lock_authorized_scope(
            user_id, inventory_id, product_id,
            allowed_roles=(BusinessMembership.Role.MANAGER,),
        )
        activation = _activation()
        if not activation or day < activation.first_observed_date or day >= _today(at):
            raise ReceiptRejected("day", "Choose a complete observed Singapore date.")
        if not tracking_enabled() or _resolve_pending(link):
            raise ReceiptRejected("day", "Demand attribution is unresolved for this product.")
        coverage, _ = DemandCoverageDay.objects.get_or_create(inventory_product=link, day=day)
        coverage = DemandCoverageDay.objects.select_for_update().get(pk=coverage.pk)
        if coverage.events.exists():
            raise ReceiptRejected("day", "This day has already been reviewed; no correction path is available.")
        totals = _totals({"business_id": inventory.business_id,
                          "inventory_id": inventory.pk, "product_id": product.pk},
                         day, day + timedelta(days=1))
        return DemandCoverageEvent.objects.create(
            coverage_day=coverage, actor_id=user_id, action="verified", reason="",
            recorded_at=timezone.now(), verified_total_units=totals.get(day, 0),
        )


def mark_demand_day_incomplete(*, user_id, inventory_id, product_id, day, reason):
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 2000:
        raise ReceiptRejected("reason", "Enter a reason of no more than 2,000 characters.")
    with transaction.atomic():
        _, _, _, _, _, link = _lock_authorized_scope(
            user_id, inventory_id, product_id,
            allowed_roles=(BusinessMembership.Role.MANAGER,),
        )
        if not _activation():
            raise ReceiptRejected("day", "Demand observation has not been activated.")
        coverage = DemandCoverageDay.objects.select_for_update().filter(
            inventory_product=link, day=day,
        ).first()
        if coverage is None or coverage.events.order_by("-pk").values_list("action", flat=True).first() != "verified":
            raise ReceiptRejected("day", "Only a previously verified day can be marked incomplete.")
        return DemandCoverageEvent.objects.create(
            coverage_day=coverage, actor_id=user_id, action="incomplete",
            reason=reason, recorded_at=timezone.now(),
        )


def _totals(scope, start, end):
    start_at = datetime.combine(start, time.min, SINGAPORE).astimezone(utc_timezone.utc)
    end_at = datetime.combine(end, time.min, SINGAPORE).astimezone(utc_timezone.utc)
    totals = {}
    manual = DemandAuditEvent.objects.filter(
        **scope, stock_out__import_record__isnull=True,
        occurred_at__gte=start_at, occurred_at__lt=end_at,
    ).annotate(local_day=TruncDate("occurred_at", tzinfo=SINGAPORE)).values("local_day").annotate(
        total=Sum("quantity_change_units"),
    )
    csv = DemandAuditEvent.objects.filter(
        **scope, stock_out__import_record__commit_attribution="resolved",
        stock_out__import_record__actual_committed_at__gte=start_at,
        stock_out__import_record__actual_committed_at__lt=end_at,
    ).annotate(local_day=TruncDate(
        "stock_out__import_record__actual_committed_at", tzinfo=SINGAPORE,
    )).values("local_day").annotate(total=Sum("quantity_change_units"))
    for rows in (manual, csv):
        for row in rows:
            totals[row["local_day"]] = totals.get(row["local_day"], 0) + row["total"]
    return totals


def seven_day_forecast(*, user_id, inventory_id, product_id, at=None):
    """Serialize with stock writers; never infer zero from absent coverage."""
    with transaction.atomic():
        _, _, _, product, inventory, link = _lock_authorized_scope(user_id, inventory_id, product_id)
        today = _today(at)
        dates = tuple(today - timedelta(days=offset) for offset in range(7, 0, -1))
        activation = _activation()
        statuses = {}
        latest_events = {}
        if activation:
            for coverage in DemandCoverageDay.objects.filter(
                inventory_product=link, day__in=dates,
            ).prefetch_related(Prefetch("events", queryset=DemandCoverageEvent.objects.order_by("pk"))):
                events = list(coverage.events.all())
                statuses[coverage.day] = events[-1].action if events else "missing"
                if events:
                    latest_events[coverage.day] = events[-1]
        days = tuple((day, statuses.get(day, "missing")) for day in dates)
        if not tracking_enabled():
            return ForecastResult(False, "PostgreSQL commit-time tracking is unavailable.", days)
        if not activation:
            return ForecastResult(False, "Demand observation has not been activated.", days)
        if dates[0] < activation.first_observed_date:
            return ForecastResult(False, "Seven complete dates after activation are required.", days)
        if _resolve_pending(link):
            return ForecastResult(False, "CSV demand attribution is unresolved.", days)
        if any(state != "verified" for _, state in days):
            return ForecastResult(False, "Every date needs explicit Manager verification.", days)
        totals = _totals({"business_id": inventory.business_id,
                          "inventory_id": inventory.pk, "product_id": product.pk},
                         dates[0], today)
        late_days = [day for day in dates
                     if latest_events[day].verified_total_units != totals.get(day, 0)]
        if late_days:
            days = tuple((day, "invalidated" if day in late_days else state) for day, state in days)
            return ForecastResult(False, "Later issue evidence changed a verified date.", days)
        total = sum(totals.get(day, 0) for day in dates)
        average = Fraction(total, 7)
        displayed = f"{Decimal(total) / Decimal(7):.2f}"
        return ForecastResult(True, "", days, average, displayed)
