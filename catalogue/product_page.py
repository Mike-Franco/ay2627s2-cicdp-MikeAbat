"""Product page (TORY-66): summary strip, FEFO batches, 7-day outlook and recent history.

Overview and Batches are two tabs of the product-stock view; History and
Forecast keep their own pages. Everything here reads the same evidence as the
dashboard: stock_positions() for available/quarantined/forecast/reorder, and the
audit tables for history.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from math import floor

from django.db.models import CharField, F, Value

from catalogue.models import ProductLifecycleAuditEvent
from receiving.models import (
    DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent, ReceiptAuditEvent, StockAdjustmentAuditEvent,
)
from receiving.services import quarantine_quantity

from .reorder import ORDER_COVER_DAYS
from .templatetags.tory_format import one_decimal, sgd, whole_units

OVERVIEW_HISTORY_ROWS = 4
OUTLOOK_DAYS = 7


# History (shared with the History tab) -----------------------------------------

def history_sources(scope):
    return {
        "receipt": ReceiptAuditEvent.objects.filter(**scope).select_related("actor", "batch"),
        "issue": DemandAuditEvent.objects.filter(**scope).select_related("actor", "stock_out").prefetch_related(
            "stock_out__allocations__batch"),
        "adjustment": StockAdjustmentAuditEvent.objects.filter(**scope).select_related("actor").prefetch_related(
            "adjustment__allocations__batch"),
        "quarantine": ExpiryQuarantineEvent.objects.filter(**scope).select_related("batch"),
        "disposal": DisposalAuditEvent.objects.filter(**scope).select_related("actor", "batch"),
        "lifecycle": ProductLifecycleAuditEvent.objects.filter(**scope).select_related("actor"),
    }


TIMESTAMPS = {"quarantine": "recorded_at"}


def history_keys(sources):
    """Newest-first union of (event_time, event_kind, event_id) across the audit tables."""
    parts = [sources[kind].order_by().annotate(
        event_time=F(TIMESTAMPS.get(kind, "occurred_at")), event_kind=Value(kind, output_field=CharField()),
        event_id=F("id"),
    ).values("event_time", "event_kind", "event_id") for kind in sources]
    first, *rest = parts
    return first.union(*rest, all=True).order_by("-event_time", "-event_kind", "-event_id")


def hydrate_history(sources, keys):
    ids_by_kind = defaultdict(list)
    for key in keys:
        ids_by_kind[key["event_kind"]].append(key["event_id"])
    audits = {kind: sources[kind].filter(pk__in=ids).in_bulk() for kind, ids in ids_by_kind.items()}
    return [{"kind": key["event_kind"], "audit": audits[key["event_kind"]][key["event_id"]]} for key in keys]


def history_row(event):
    """One compact row for the Overview: when, who, action, signed quantity, physical after, note."""
    kind, audit = event["kind"], event["audit"]
    actor = getattr(audit, "actor", None)
    row = {"at": getattr(audit, "occurred_at", None) or audit.recorded_at, "actor": actor, "change": None,
           "after": None, "note": ""}
    if kind == "receipt":
        row.update(action="Received", change=audit.quantity_change_units, after=audit.quantity_after_units,
                   note=f"Batch #{audit.batch.receipt_sequence}")
    elif kind == "issue":
        row.update(action="Issued", change=-audit.quantity_change_units, after=audit.quantity_after_units)
    elif kind == "adjustment":
        row.update(action="Counted", change=audit.quantity_change_units, after=audit.quantity_after_units,
                   note=audit.reason)
    elif kind == "quarantine":
        row.update(action="Quarantined", change=audit.quarantine_after_units - audit.quarantine_before_units,
                   note=f"Batch #{audit.batch.receipt_sequence} expired")
    elif kind == "disposal":
        row.update(action="Disposed", change=-audit.quantity_units, after=audit.physical_after_units,
                   note=f"Batch #{audit.batch.receipt_sequence} · {audit.reason_code}")
    else:
        row.update(action="Deactivated" if audit.action == "deactivate" else "Reactivated", note="No stock change")
    row["magnitude"] = abs(row["change"]) if row["change"] is not None else None
    return row


# Batches ---------------------------------------------------------------------

def fefo_batches(link, *, today, now, include_empty):
    """Batches in the order stock is issued: earliest expiry first, undated last."""
    batches = sorted(link.receiving_batches.all(),
                     key=lambda batch: (batch.expiry_date is None, batch.expiry_date or today, batch.receipt_sequence))
    rows = []
    for batch in batches:
        if not batch.remaining_quantity_units and not include_empty:
            continue
        held = quarantine_quantity(batch, at=now)
        days = (batch.expiry_date - today).days if batch.expiry_date else None
        if not batch.remaining_quantity_units:
            status, tone = "Used up", "neutral"
        elif held:
            status, tone = ("Expired" if days is not None and days <= 0 else "Quarantined"), "red"
        elif days is not None and days <= 7:
            status, tone = "Expiring", "amber"
        else:
            status, tone = "Available", "green"
        rows.append({"batch": batch, "quarantined": held, "days": days, "status": status, "tone": tone})
    return rows


# Summary and outlook ---------------------------------------------------------

def _decimal(value):
    value = Fraction(value)
    return Decimal(value.numerator) / Decimal(value.denominator)


def summary(position, *, today):
    """The six numbers in the strip, each with its note (or the reason it is missing)."""
    link, product, reorder = position.link, position.link.product, position.reorder
    unit = product.base_unit_label or "unit"
    forecast = reorder.forecast if reorder else None
    point = reorder.reorder_point if reorder else None
    reason = position.supply_reason or (
        "Set " + " and ".join(reorder.missing_settings) + "." if reorder and reorder.missing_settings else "")
    if forecast is not None and not forecast.available:
        reason = forecast.reason
    run_out = None
    if position.supply is not None:
        run_out = today + timedelta(days=floor(position.supply))
    suggested = reorder.suggested_units if reorder else None
    price = link.selling_price
    return {
        "unit": unit,
        "available": position.available,
        "reorder_point": whole_units(point),
        "quarantined": position.quarantined,
        "average": forecast.displayed_average if forecast is not None and forecast.available else None,
        "supply": None if position.supply is None else one_decimal(position.supply),
        "run_out": run_out,
        "suggested": suggested,
        "price": price,
        "value": None if price is None else sgd(price * position.available),
        "reason": reason or ("The product is inactive." if not product.is_active else ""),
        "cover_days": ORDER_COVER_DAYS,
    }


def outlook(position, info, *, today):
    """Projected available stock for the next 7 days at the verified average, and the order callout."""
    forecast = position.reorder.forecast if position.reorder else None
    if forecast is None or not forecast.available:
        return [], None
    average = _decimal(forecast.average)
    point = info["reorder_point"]
    days = [{"day": (today + timedelta(days=offset)).isoformat(),
             "stock": float(max(Decimal(0), position.available - average * offset).quantize(Decimal("0.1"))),
             "reorder_point": point}
            for offset in range(OUTLOOK_DAYS + 1)]
    product = position.link.product
    lead = product.lead_time_days
    suggested = info["suggested"]
    if suggested is None:
        return days, None
    unit = info["unit"]
    if suggested == 0:
        text = f"No order needed today: stock covers more than {ORDER_COVER_DAYS} days after the lead time."
    else:
        arrival = today + timedelta(days=lead)
        when = arrival.strftime("%a %d %b").replace(" 0", " ")
        text = f"Order {suggested} {unit}{'' if suggested == 1 else 's'} today. Lead time is {lead} day" \
               f"{'' if lead == 1 else 's'}, so stock arrives {when}"
        if info["run_out"] is not None and info["run_out"] < arrival:
            text += f", after it runs out on {info['run_out'].strftime('%a %d %b').replace(' 0', ' ')}."
        else:
            text += " before it runs out."
    return days, text
