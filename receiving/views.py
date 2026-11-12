from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.sessions import protected_view
from catalogue.models import InventoryProduct
from inventory_access.authorization import get_authorized_inventory
from inventory_access.models import BusinessMembership, Inventory

from .forms import (BatchCountFormSet, ManualReceiptForm, ManualStockAdjustmentForm,
                    ManualStockDisposalForm, ManualStockOutForm, StockCsvImportForm)
from .csv_import import CsvImportRejected, MAX_BYTES, import_stock_csv
from .models import ReceivingBatch, StockOut, StockAdjustment, StockDisposal
from .services import ReceiptRejected, adjust_stock, dispose_quarantined, issue_stock, receive_manual


@protected_view
@require_http_methods(["GET", "POST"])
def import_stock_csv_view(request, inventory_id):
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    if not BusinessMembership.objects.filter(
        user=request.user, business=inventory.business, role=BusinessMembership.Role.MANAGER,
        is_active=True, inventory_assignments__inventory=inventory,
        inventory_assignments__is_active=True,
    ).exists():
        raise Http404
    form = StockCsvImportForm(request.POST or None, request.FILES or None)
    imported = None
    if request.method == "POST" and form.is_valid():
        try:
            raw = form.cleaned_data["file"].read(MAX_BYTES + 1)
            imported = import_stock_csv(user_id=request.user.pk, inventory_id=inventory.pk, raw_bytes=raw)
        except CsvImportRejected as error:
            location = f"Row {error.row}, {error.field}: " if error.row and error.field else (
                f"Row {error.row}: " if error.row else f"{error.category}: "
            )
            form.add_error("file", location + str(error))
    return render(request, "receiving/import_csv.html", {
        "inventory": inventory, "form": form, "imported": imported,
    }, status=400 if request.method == "POST" and (form.errors or not imported) else 200)


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
    request.tory_inventory_id = inventory.pk
    return render(
        request,
        "receiving/receipt_confirmation.html",
        {"inventory": inventory, "product": batch.product, "batch": batch, "audit": batch.audit_event},
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
    request.tory_inventory_id = inventory.pk
    return render(request, "receiving/stock_out_confirmation.html", {"inventory": inventory, "product": stock_out.product, "stock_out": stock_out, "allocations": stock_out.allocations.select_related("batch").order_by("batch__expiry_date", "batch__receipt_sequence", "batch_id")})


def _load_manager_scope(user, inventory_id, product_id):
    inventory, link = _load_receivable(user, inventory_id, product_id)
    manager_assigned = BusinessMembership.objects.filter(
        user=user, business=inventory.business, role=BusinessMembership.Role.MANAGER,
        is_active=True, inventory_assignments__inventory=inventory,
        inventory_assignments__is_active=True,
    ).exists()
    if not manager_assigned:
        raise Http404
    return inventory, link


def _adjustment_batches(link):
    return list(ReceivingBatch.objects.filter(
        inventory_product=link, quarantined_quantity_units=0,
    ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gt=timezone.localdate())).order_by(
        "receipt_sequence", "id"
    ))


@protected_view
@require_http_methods(["GET", "POST"])
def adjust_stock_view(request, inventory_id, product_id):
    try:
        inventory, link = _load_manager_scope(request.user, inventory_id, product_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    except InventoryProduct.DoesNotExist as error:
        raise Http404 from error
    eligible_batches = _adjustment_batches(link)
    form = ManualStockAdjustmentForm(request.POST or None)
    if request.method == "POST":
        prefix = "batches"
        try:
            submitted_total = min(int(request.POST.get(f"{prefix}-TOTAL_FORMS", "0")), 500)
        except (TypeError, ValueError):
            submitted_total = 0
        submitted_ids = [request.POST.get(f"{prefix}-{index}-batch_id") for index in range(submitted_total)]
        batch_lookup = {str(batch.pk): batch for batch in ReceivingBatch.objects.filter(inventory_product=link, pk__in=submitted_ids)}
        initial_rows = [{"batch_id": value, "batch": batch_lookup.get(value)} for value in submitted_ids]
    else:
        initial_rows = [{"batch_id": batch.pk, "batch": batch} for batch in eligible_batches]
    formset = BatchCountFormSet(
        request.POST or None,
        initial=initial_rows,
        prefix="batches",
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        batch_counts = [
            {"batch_id": row.cleaned_data["batch_id"],
             "counted_quantity_units": row.cleaned_data["counted_quantity_units"],
             "manager_confirmed_identity": True}
            for row in formset.forms
            if row.cleaned_data and row.cleaned_data.get("confirmed")
        ]
        try:
            adjustment = adjust_stock(
                user_id=request.user.pk, inventory_id=inventory_id,
                product_id=product_id, batch_counts=batch_counts,
                reason=form.cleaned_data["reason"],
            )
        except ReceiptRejected as error:
            form.add_error(None, str(error))
        else:
            return redirect("stock-adjustment-confirmation", adjustment_id=adjustment.pk)
    return render(request, "receiving/adjust_stock.html", {
        "inventory": inventory, "product": link.product, "link": link, "form": form,
        "formset": formset, "batches": eligible_batches,
    }, status=400 if request.method == "POST" and (form.errors or formset.errors or formset.non_form_errors()) else 200)


@protected_view
@require_GET
def stock_adjustment_confirmation(request, adjustment_id):
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related("inventory", "product", "actor", "audit_event")
        .prefetch_related("allocations__batch"), pk=adjustment_id,
    )
    try:
        inventory = get_authorized_inventory(request.user, adjustment.inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    if not InventoryProduct.objects.filter(
        inventory=inventory, product=adjustment.product,
        product__business_id=inventory.business_id,
    ).exists():
        raise Http404
    request.tory_inventory_id = inventory.pk
    return render(request, "receiving/stock_adjustment_confirmation.html", {
        "inventory": inventory, "product": adjustment.product, "adjustment": adjustment,
        "allocations": adjustment.allocations.select_related("batch").order_by("batch__receipt_sequence", "batch_id"),
    })


@protected_view
@require_http_methods(["GET", "POST"])
def dispose_stock_view(request, inventory_id, product_id):
    try:
        inventory, link = _load_manager_scope(request.user, inventory_id, product_id)
    except (Inventory.DoesNotExist, InventoryProduct.DoesNotExist) as error:
        raise Http404 from error
    batches = list(ReceivingBatch.objects.filter(
        inventory_product=link, expiry_date__lte=timezone.localdate(),
        remaining_quantity_units__gt=0,
    ).order_by("expiry_date", "receipt_sequence", "id"))
    form = ManualStockDisposalForm(request.POST or None, batches=batches)
    if request.method == "POST" and form.is_valid():
        try:
            disposal = dispose_quarantined(
                user_id=request.user.pk, inventory_id=inventory_id,
                product_id=product_id, batch_id=form.cleaned_data["batch_id"],
                quantity_units=form.cleaned_data["quantity_units"],
                reason_code=form.cleaned_data["reason_code"],
                reason_note=form.cleaned_data["reason_note"],
            )
        except ReceiptRejected as error:
            form.add_error(error.field, str(error))
        else:
            return redirect("disposal-confirmation", disposal_id=disposal.pk)
    return render(request, "receiving/dispose_stock.html", {
        "inventory": inventory, "product": link.product, "form": form,
        "batches": batches,
    }, status=400 if request.method == "POST" else 200)


@protected_view
@require_GET
def disposal_confirmation(request, disposal_id):
    disposal = get_object_or_404(
        StockDisposal.objects.select_related("inventory", "product", "batch", "actor", "audit_event"),
        pk=disposal_id,
    )
    try:
        inventory = get_authorized_inventory(request.user, disposal.inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    if not InventoryProduct.objects.filter(
        inventory=inventory, product=disposal.product,
        product__business_id=inventory.business_id,
    ).exists():
        raise Http404
    request.tory_inventory_id = inventory.pk
    return render(request, "receiving/disposal_confirmation.html", {"inventory": inventory, "product": disposal.product, "disposal": disposal})

