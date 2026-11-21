from collections import defaultdict
from datetime import timedelta

from django.db.models import Case, F, Sum, Value, When

from catalogue.authorization import visible_product_links
from catalogue.reorder import recommendation_from_evidence
from inventory_access.authorization import authorized_inventories
from receiving.demand import available_forecasts_for_links
from receiving.models import (
    DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent, ReceiptAuditEvent,
    ReceivingBatch, StockAdjustmentAuditEvent,
)
from receiving.services import SINGAPORE


def _recent_activity(inventories):
    def rows(model, action, time="occurred_at"):
        return model.objects.filter(
            inventory_id__in=inventories,
            business_id=F("inventory__business_id"),
        ).order_by().values(
            "id", "inventory_id", "product_id", inventory_name=F("inventory__name"),
            product_name=F("product__name"), movement=Value(action), movement_at=F(time),
        )

    return rows(ReceiptAuditEvent, "Received").union(
        rows(DemandAuditEvent, "Issued"),
        rows(StockAdjustmentAuditEvent, "Count adjusted"),
        rows(ExpiryQuarantineEvent, "Quarantined", "recorded_at"),
        rows(DisposalAuditEvent, "Disposed"),
        all=True,
    ).order_by("-movement_at", "movement", "-id")[:10]


def inventory_dashboard(user, *, at):
    today = at.astimezone(SINGAPORE).date()
    seven_days = today + timedelta(days=7)
    thirty_days = today + timedelta(days=30)
    inventories = list(authorized_inventories(user))
    links = list(visible_product_links(user))
    link_ids = [link.pk for link in links]
    batches = ReceivingBatch.objects.filter(inventory_product_id__in=link_ids, remaining_quantity_units__gt=0)
    quarantined = dict(batches.order_by().values("inventory_product_id").annotate(
        units=Sum(Case(
            When(expiry_date__lte=today, then=F("remaining_quantity_units")),
            default=F("quarantined_quantity_units"),
        )),
    ).values_list("inventory_product_id", "units"))
    inventory_totals = defaultdict(int)
    for link in links:
        inventory_totals[link.inventory_id] += quarantined.get(link.pk, 0)
    eligible = [link.pk for link in links if link.product.is_active
                and link.product.lead_time_days is not None and link.product.safety_stock_units is not None]
    forecasts = available_forecasts_for_links(eligible, at=at)
    low_stock = []
    checked_count = 0
    for link in links:
        forecast = forecasts.get(link.pk)
        if forecast is None or not forecast.available:
            continue
        result = recommendation_from_evidence(
            link.product, link.physical_quantity_units, forecast, quarantined.get(link.pk, 0),
        )
        checked_count += 1
        if result.alert:
            low_stock.append((link, result))
    expiring_week = []
    expiring_later = []
    for batch in batches.filter(
        expiry_date__gt=today, expiry_date__lte=thirty_days,
        remaining_quantity_units__gt=F("quarantined_quantity_units"),
    ).select_related("product", "inventory").order_by("expiry_date", "pk"):
        batch.eligible_units = batch.remaining_quantity_units - batch.quarantined_quantity_units
        (expiring_week if batch.expiry_date <= seven_days else expiring_later).append(batch)
    return {
        "inventory_totals": [(inventory, inventory_totals[inventory.pk]) for inventory in inventories],
        "low_stock": low_stock,
        "reorder_unavailable": sum(link.product.is_active for link in links) - checked_count,
        "expiring_week": expiring_week,
        "expiring_later": expiring_later,
        "recent_activity": list(_recent_activity([inventory.pk for inventory in inventories])),
    }
