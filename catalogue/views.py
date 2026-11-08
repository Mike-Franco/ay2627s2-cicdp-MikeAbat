from django.http import Http404
from django.shortcuts import get_object_or_404, render

from accounts.sessions import protected_view
from catalogue.models import InventoryProduct
from inventory_access.authorization import get_authorized_inventory
from inventory_access.models import BusinessMembership, Inventory
from django.utils import timezone
from receiving.models import (DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent,
                              ReceiptAuditEvent, StockAdjustmentAuditEvent)
from receiving.services import quarantine_quantity

from .authorization import visible_inventory_product_links, visible_product_links


@protected_view
def product_catalogue(request):
    return render(
        request,
        "catalogue/product_catalogue.html",
        {"product_links": visible_product_links(request.user)},
    )


@protected_view
def inventory_products(request, inventory_id):
    try:
        inventory, links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    product_links = list(links.prefetch_related("receiving_batches"))
    now = timezone.now()
    for link in product_links:
        link.display_quarantine_units = sum(
            quarantine_quantity(batch, at=now) for batch in link.receiving_batches.all()
        )
        link.display_available_units = link.physical_quantity_units - link.display_quarantine_units
    return render(
        request,
        "catalogue/inventory_products.html",
        {"inventory": inventory, "product_links": product_links,
         "can_adjust_stock": BusinessMembership.objects.filter(
             user=request.user, business=inventory.business,
             role=BusinessMembership.Role.MANAGER, is_active=True,
             inventory_assignments__inventory=inventory,
             inventory_assignments__is_active=True,
         ).exists()},
    )


@protected_view
def stock_history(request, inventory_id, product_id):
    """Show committed audit evidence within one assigned inventory/product."""
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    link = get_object_or_404(
        InventoryProduct.objects.select_related("product"),
        inventory=inventory, product_id=product_id,
        product__business_id=inventory.business_id,
    )
    scope = {"business_id": inventory.business_id,
             "inventory_id": inventory.pk, "product_id": link.product_id}
    events = []

    for audit in ReceiptAuditEvent.objects.filter(**scope).select_related("actor", "batch"):
        events.append({"kind": "receipt", "at": audit.occurred_at, "audit": audit})
    for audit in DemandAuditEvent.objects.filter(**scope).select_related("actor").prefetch_related(
        "stock_out__allocations__batch"
    ):
        events.append({"kind": "issue", "at": audit.occurred_at, "audit": audit})
    for audit in StockAdjustmentAuditEvent.objects.filter(**scope).select_related("actor").prefetch_related(
        "adjustment__allocations__batch"
    ):
        events.append({"kind": "adjustment", "at": audit.occurred_at, "audit": audit})
    for audit in ExpiryQuarantineEvent.objects.filter(**scope).select_related("batch"):
        events.append({"kind": "quarantine", "at": audit.recorded_at, "audit": audit})
    for audit in DisposalAuditEvent.objects.filter(**scope).select_related("actor", "batch"):
        events.append({"kind": "disposal", "at": audit.occurred_at, "audit": audit})

    events.sort(key=lambda event: (event["at"], event["audit"].pk, event["kind"]), reverse=True)
    return render(request, "catalogue/stock_history.html", {
        "inventory": inventory, "product": link.product, "events": events,
    })
