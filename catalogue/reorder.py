"""Inventory-scoped reorder advice and business-shared setting changes."""

from dataclasses import dataclass
from math import ceil

from django.db import connection, transaction
from django.utils import timezone

from inventory_access.models import BusinessMembership, Inventory, InventoryAssignment
from receiving.demand import _forecast_locked
from receiving.services import ReceiptRejected, _lock_authorized_scope, quarantine_quantity

from .models import InventoryProduct, Product


MAX_UNITS = 2_147_483_647


@dataclass(frozen=True)
class ReorderResult:
    forecast: object
    available_units: int
    quarantined_units: int
    lead_time_days: int | None
    safety_stock_units: int | None
    missing_settings: tuple[str, ...]
    reorder_point: object = None
    alert: bool | None = None
    suggested_units: int | None = None


def recommendation(*, user_id, inventory_id, product_id, at=None):
    # Stock writers take Product -> Inventory -> link -> batch locks. Holding
    # those parent locks also keeps coverage and movement reads consistent.
    with transaction.atomic():
        _, _, _, product, inventory, link = _lock_authorized_scope(
            user_id, inventory_id, product_id,
        )
        observed_at = at or timezone.now()
        forecast = _forecast_locked(product, inventory, link, at=observed_at)
        quarantined = sum(quarantine_quantity(batch, at=observed_at)
                          for batch in link.receiving_batches.all())
        available = link.physical_quantity_units - quarantined
        missing = tuple(label for label, value in (
            ("lead time", product.lead_time_days),
            ("safety stock", product.safety_stock_units),
        ) if value is None)
        if not forecast.available or missing:
            return ReorderResult(forecast, available, quarantined,
                                 product.lead_time_days, product.safety_stock_units, missing)
        point = forecast.average * product.lead_time_days + product.safety_stock_units
        return ReorderResult(forecast, available, quarantined,
                             product.lead_time_days, product.safety_stock_units, missing,
                             point, available <= point, max(0, ceil(point - available)))


def can_edit_shared_settings(user, product):
    if not user.is_authenticated or not user.is_active or not product.is_active:
        return False
    membership = BusinessMembership.objects.filter(
        user=user, business_id=product.business_id,
        role=BusinessMembership.Role.MANAGER, is_active=True,
    ).first()
    if membership is None:
        return False
    linked_ids = set(InventoryProduct.objects.filter(
        product=product, inventory__is_active=True,
    ).values_list("inventory_id", flat=True))
    assigned_ids = set(InventoryAssignment.objects.filter(
        membership=membership, is_active=True, inventory__is_active=True,
    ).values_list("inventory_id", flat=True))
    return bool(linked_ids) and linked_ids <= assigned_ids


def save_shared_settings(*, user_id, inventory_id, product_id,
                         lead_time_days, safety_stock_units):
    if lead_time_days is not None and (type(lead_time_days) is not int or not 1 <= lead_time_days <= 365):
        raise ReceiptRejected("lead_time_days", "Enter 1 to 365 whole calendar days, or leave blank.")
    if safety_stock_units is not None and (type(safety_stock_units) is not int or not 0 <= safety_stock_units <= MAX_UNITS):
        raise ReceiptRejected("safety_stock_units", "Enter 0 to 2,147,483,647 whole units, or leave blank.")
    with transaction.atomic():
        try:
            hint = Inventory.objects.only("business_id").get(pk=inventory_id, is_active=True)
        except Inventory.DoesNotExist as error:
            raise ReceiptRejected("__all__", "This inventory or product is unavailable.") from error
        # Lock *all* Manager assignments before Product, matching stock writers'
        # authorization -> Product -> Inventory order. A newly linked inventory
        # absent from this locked set makes the edit fail safely on recheck.
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_active FROM accounts_user WHERE id=%s FOR SHARE", [user_id])
            user_row = cursor.fetchone()
            cursor.execute(
                "SELECT id, role, is_active FROM inventory_access_businessmembership "
                "WHERE user_id=%s AND business_id=%s FOR SHARE",
                [user_id, hint.business_id],
            )
            membership = cursor.fetchone()
            if not user_row or not user_row[0] or not membership or membership[1:] != ("manager", True):
                raise ReceiptRejected("__all__", "This inventory or product is unavailable.")
            cursor.execute(
                "SELECT inventory_id, is_active FROM inventory_access_inventoryassignment "
                "WHERE membership_id=%s ORDER BY inventory_id FOR SHARE", [membership[0]],
            )
            assigned_ids = {row[0] for row in cursor.fetchall() if row[1]}
        try:
            product = Product.objects.select_for_update().get(
                pk=product_id, business_id=hint.business_id, is_active=True,
            )
        except Product.DoesNotExist as error:
            raise ReceiptRejected("__all__", "This inventory or product is unavailable.") from error
        linked_inventories = list(Inventory.objects.select_for_update(of=("self",)).filter(
            business_id=hint.business_id, product_links__product=product,
        ).order_by("pk"))
        active_ids = {inventory.pk for inventory in linked_inventories if inventory.is_active}
        if inventory_id not in active_ids or not active_ids <= assigned_ids:
            raise ReceiptRejected("__all__", "This inventory or product is unavailable.")
        product.lead_time_days = lead_time_days
        product.safety_stock_units = safety_stock_units
        product.save(update_fields=["lead_time_days", "safety_stock_units"])
        return product
