from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from accounts.sessions import protected_view
from catalogue.models import InventoryProduct
from inventory_access.authorization import get_authorized_inventory
from inventory_access.models import Inventory

from .forms import ManualReceiptForm, ManualStockOutForm
from .models import DemandAuditEvent, ReceiptAuditEvent, ReceivingBatch, StockOut
from .services import ReceiptRejected, issue_stock, receive_manual


def _load_receivable(user, inventory_id, product_id):
    inventory = get_authorized_inventory(user, inventory_id)
    try:
        link = InventoryProduct.objects.select_related("product").get(
            inventory=inventory,
            product_id=product_id,
            product__business_id=inventory.business_id,
            product__is_active=True,
        )
    except InventoryProduct.DoesNotExist as error:
        raise Http404 from error
    return inventory, link


@protected_view
@require_http_methods(["GET", "POST"])
def receive_batch(request, inventory_id, product_id):
    try:
        inventory, link = _load_receivable(request.user, inventory_id, product_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    product = link.product
    if product.base_unit_label is None or product.expiry_tracking_required is None:
        setup_required = True
    else:
        setup_required = False

    if request.method == "GET":
        return render(
            request,
            "receiving/receive_batch.html",
            {
                "inventory": inventory,
                "product": product,
                "setup_required": setup_required,
                "form": ManualReceiptForm.new_form(
                    expiry_required=product.expiry_tracking_required is True
                ),
            },
        )

    form = ManualReceiptForm(request.POST, expiry_required=product.expiry_tracking_required is True)
    if not form.is_valid():
        return render(
            request,
            "receiving/receive_batch.html",
            {"inventory": inventory, "product": product, "setup_required": setup_required, "form": form},
            status=400,
        )
    try:
        batch, replayed = receive_manual(
            user_id=request.user.pk,
            inventory_id=inventory_id,
            product_id=product_id,
            request_token=form.cleaned_data["request_token"],
            quantity_units=form.cleaned_data["quantity_units"],
            expiry_date=form.cleaned_data["expiry_date"],
        )
    except ReceiptRejected as error:
        form.add_error(error.field, str(error))
        return render(
            request,
            "receiving/receive_batch.html",
            {"inventory": inventory, "product": product, "setup_required": setup_required, "form": form},
            status=400,
        )
    return redirect("receipt-confirmation", receipt_id=batch.pk)


@protected_view
@require_GET
def receipt_confirmation(request, receipt_id):
    batch = get_object_or_404(
        ReceivingBatch.objects.select_related("inventory", "product", "actor", "audit_event"),
        pk=receipt_id,
    )
    try:
        inventory = get_authorized_inventory(request.user, batch.inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    if not InventoryProduct.objects.filter(
        inventory=inventory, product=batch.product, product__business_id=inventory.business_id
    ).exists():
        raise Http404
    return render(
        request,
        "receiving/receipt_confirmation.html",
        {"batch": batch, "audit": batch.audit_event},
    )


@protected_view
@require_http_methods(["GET", "POST"])
def issue_stock_view(request, inventory_id, product_id):
    try:
        inventory, link = _load_receivable(request.user, inventory_id, product_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    form = ManualStockOutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            stock_out = issue_stock(
                user_id=request.user.pk, inventory_id=inventory_id,
                product_id=product_id, quantity_units=form.cleaned_data["quantity_units"],
            )
        except ReceiptRejected as error:
            form.add_error(error.field, str(error))
            return render(request, "receiving/issue_stock.html", {"inventory": inventory, "product": link.product, "form": form}, status=400)
        return redirect("stock-out-confirmation", stock_out_id=stock_out.pk)
    return render(request, "receiving/issue_stock.html", {"inventory": inventory, "product": link.product, "form": form})


@protected_view
@require_GET
def stock_out_confirmation(request, stock_out_id):
    stock_out = get_object_or_404(StockOut.objects.select_related("inventory", "product", "actor").prefetch_related("allocations__batch"), pk=stock_out_id)
    try:
        inventory = get_authorized_inventory(request.user, stock_out.inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    if not InventoryProduct.objects.filter(inventory=inventory, product=stock_out.product, product__business_id=inventory.business_id).exists():
        raise Http404
    return render(request, "receiving/stock_out_confirmation.html", {"stock_out": stock_out, "allocations": stock_out.allocations.select_related("batch").order_by("batch__expiry_date", "batch__receipt_sequence", "batch_id")})

