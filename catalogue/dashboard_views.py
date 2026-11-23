from collections import Counter
from datetime import timedelta

from django.db.models import F, Value
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.sessions import protected_view
from inventory_access.authorization import authorized_inventories, manageable_inventories
from receiving.models import (
    DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent, ReceiptAuditEvent,
    ReceivingBatch, StockAdjustmentAuditEvent,
)

from .authorization import visible_product_links
from .pagination import paginate
from .metrics import (
    STATUS_LABELS, complete_days, daily_movements, kpis, movement_metrics, singapore_day, stock_positions,
    unverified_summary,
)


def _activity(inventories):
    def rows(model, action, quantity, time="occurred_at"):
        return model.objects.filter(
            inventory_id__in=inventories, business_id=F("inventory__business_id"),
        ).order_by().values(
            "id", "inventory_id", "product_id",
            product_name=F("product__name"), unit=F("product__base_unit_label"),
            movement=Value(action), quantity=quantity, movement_at=F(time),
        )

    return rows(ReceiptAuditEvent, "Received", F("quantity_change_units")).union(
        rows(DemandAuditEvent, "Issued", F("quantity_change_units")),
        rows(StockAdjustmentAuditEvent, "Count adjusted", F("quantity_change_units")),
        rows(ExpiryQuarantineEvent, "Quarantined",
             F("quarantine_after_units") - F("quarantine_before_units"), "recorded_at"),
        rows(DisposalAuditEvent, "Disposed", F("quantity_units")),
        all=True,
    ).order_by("-movement_at", "movement", "-id")


def _action_rows(positions):
    rows = []
    for position in positions:
        reorder = position.reorder
        if reorder is None:
            continue
        if position.out:
            urgency, label = 0, STATUS_LABELS["out"]
        elif position.low:
            urgency, label = 1, STATUS_LABELS["low"]
        elif position.quarantined:
            urgency, label = 2, STATUS_LABELS["quarantined"]
        elif position.expiring:
            urgency, label = 3, STATUS_LABELS["expiring"]
        elif reorder.reorder_point is None:
            urgency, label = 4, "Reorder point unavailable"
        else:
            continue
        rows.append({
            "position": position, "link": position.link, "label": label, "urgency": urgency,
        })
    rows.sort(key=lambda row: (
        row["urgency"], row["position"].supply is None, row["position"].supply or 0, row["link"].pk,
    ))
    return rows


def _panel(request, key, rows, preview):
    expanded = request.GET.get("panel") == key
    if expanded:
        page = paginate(request, rows, fragment=key)
        return {"key": key, "rows": list(page.object_list), "page": page, "expanded": True}
    total = len(rows) if isinstance(rows, list) else rows.count()
    return {"key": key, "rows": list(rows[:preview]), "total": total}


@protected_view
@require_GET
def dashboard(request):
    at = timezone.now()
    today = singapore_day(at)
    assigned = list(authorized_inventories(request.user))
    chosen = request.GET.get("inventory", "")
    selected = [inventory for inventory in assigned if str(inventory.pk) == chosen] if chosen else assigned
    if chosen and not selected:
        raise Http404
    inventories = {inventory.pk: inventory for inventory in selected}
    links = list(visible_product_links(request.user).filter(inventory_id__in=inventories).select_related("product__category"))
    positions = stock_positions(links, at=at)
    movements = daily_movements(links, start=complete_days(at, 30)[0], at=at)
    stock_to_sales_30d, turnover_30d = movement_metrics(positions, movements, at=at)
    unverified, tasks = unverified_summary(positions, at=at)
    managed = set(manageable_inventories(request.user).filter(pk__in=inventories).values_list("pk", flat=True))
    expiry_rows = ReceivingBatch.objects.filter(
        inventory_product_id__in=[link.pk for link in links],
        expiry_date__gt=today, expiry_date__lte=today + timedelta(days=30),
        remaining_quantity_units__gt=F("quarantined_quantity_units"),
    ).select_related("product", "inventory").annotate(
        eligible_units=F("remaining_quantity_units") - F("quarantined_quantity_units"),
    ).order_by("expiry_date", "pk")
    expiring = _panel(request, "expiry", expiry_rows, 5)
    activities = _panel(request, "activity", _activity(inventories), 10) if inventories else {"rows": []}
    for row in activities["rows"]:
        row["inventory"] = inventories[row["inventory_id"]]
    totals = Counter()
    for position in positions:
        totals[position.link.inventory_id] += position.quarantined
    actions = _panel(request, "actions", _action_rows(positions), 10)
    until = today + timedelta(days=7)
    demand_tasks = [{"inventory": inventories[pk], **tasks[pk]} for pk in sorted(managed) if pk in tasks]
    return render(request, "accounts/home.html", {
        "assigned": assigned, "chosen": chosen, "kpi_cards": kpis(positions, turnover_30d=turnover_30d, unverified=unverified),
        "stock_to_sales_30d": stock_to_sales_30d,
        "actions": actions, "expiring": expiring, "activities": activities,
        "expiring_week": [batch for batch in expiring["rows"] if batch.expiry_date <= until],
        "expiring_later": [batch for batch in expiring["rows"] if batch.expiry_date > until],
        "recent_activity": activities["rows"],
        "inventory_totals": [(inventory, totals[inventory.pk]) for inventory in selected],
        # "Do this first" (TORY-63): only Managers can verify demand, so only they see the task.
        "demand_tasks": demand_tasks,
        "demand_days_total": sum(len(task["days"]) for task in demand_tasks),
        "reorder_unavailable": sum(position.reorder is not None and position.reorder.reorder_point is None
                                   for position in positions),
    })
