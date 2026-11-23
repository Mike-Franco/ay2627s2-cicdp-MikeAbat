from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from inventory_access.models import Inventory

from .authorization import lock_manager_assignment_ids
from .forms import DUPLICATE_SKU, PRODUCT_FIELDS
from .models import Category, InventoryProduct, Product, ProductChangeAuditEvent


def _save_product(product):
    try:
        # Keep the caller's transaction usable if a concurrent create wins the SKU.
        with transaction.atomic():
            product.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) != "unique_business_sku_ci_trimmed":
            raise
        raise ValidationError({"sku": DUPLICATE_SKU}) from error
    except ValidationError as error:
        if any("unique_business_sku_ci_trimmed" in item.message
               for item in error.error_dict.get(NON_FIELD_ERRORS, [])):
            raise ValidationError({"sku": DUPLICATE_SKU}) from error
        raise


def _snapshot(product):
    return {field: getattr(product, "category_id" if field == "category" else field)
            for field in PRODUCT_FIELDS}


@transaction.atomic
def save_product_change(*, user, inventory, values, product_id=None, inventory_ids=()):
    assigned = lock_manager_assignment_ids(user.pk, inventory.business_id)
    if inventory.pk not in assigned:
        raise Http404
    if product_id is None:
        product = Product(business_id=inventory.business_id)
        selected = set(inventory_ids)
        before = None
    else:
        try:
            product = Product.objects.select_for_update().get(pk=product_id, business_id=inventory.business_id)
        except Product.DoesNotExist as error:
            raise Http404 from error
        selected = set(product.inventory_links.values_list("inventory_id", flat=True))
        if inventory.pk not in selected:
            raise Http404
        before = _snapshot(product)
    if not selected or not selected <= assigned:
        raise Http404
    locked = {
        shelf.pk: shelf for shelf in Inventory.objects.select_for_update().filter(
            pk__in=selected | {inventory.pk}, business_id=inventory.business_id,
        ).order_by("pk")
    }
    if (locked.keys() != selected | {inventory.pk} or not locked[inventory.pk].is_active
            or (before is None and any(not locked[pk].is_active for pk in selected))):
        raise Http404
    for field in PRODUCT_FIELDS:
        if before is None or field != "sku":
            # Optional fields keep their current value when a caller (the demo seed, an
            # older form) does not send them. supplier_name was added in TORY-66.
            if field in ("category", "supplier_name") and field not in values:
                continue
            setattr(product, field, values[field])
    if product.category_id:
        category = Category.objects.select_for_update().filter(
            pk=product.category_id, business_id=product.business_id,
        ).first()
        if category is None:
            raise ValidationError({"category": "Choose an existing category from this business."})
        product.category = category
    after = _snapshot(product)
    if after == before:
        return product
    _save_product(product)
    if before is None:
        InventoryProduct.objects.bulk_create([
            InventoryProduct(inventory_id=pk, product=product) for pk in sorted(selected)
        ])
    ProductChangeAuditEvent.objects.create(
        actor=user, business_id=inventory.business_id, inventory_id=min(selected) if before is None else inventory.pk,
        product=product, action="create" if before is None else "edit",
        before=before, after=_snapshot(product), occurred_at=timezone.now(),
    )
    return product


def _price_snapshot(link):
    return {"selling_price": None if link.selling_price is None else f"{link.selling_price:.2f}"}


@transaction.atomic
def save_selling_price(*, user, inventory, product_id, price):
    """Set one inventory's selling price for a product (SGD, None clears it).

    Prices are per inventory (BR-016/BR-018), so the audit event names the
    inventory. Locks follow the stock writers' Product -> Inventory -> link
    order, and only the selling_price column is written, so the stock-column
    triggers never fire. An unchanged price records nothing.
    """
    assigned = lock_manager_assignment_ids(user.pk, inventory.business_id)
    if inventory.pk not in assigned:
        raise Http404
    try:
        product = Product.objects.select_for_update().get(pk=product_id, business_id=inventory.business_id)
        locked_inventory = Inventory.objects.select_for_update().get(
            pk=inventory.pk, business_id=inventory.business_id, is_active=True)
        link = InventoryProduct.objects.select_for_update().get(inventory=locked_inventory, product=product)
    except (Product.DoesNotExist, Inventory.DoesNotExist, InventoryProduct.DoesNotExist) as error:
        raise Http404 from error
    before = _price_snapshot(link)
    link.selling_price = price
    after = _price_snapshot(link)
    if after == before:
        return link
    link.save(update_fields=["selling_price"])
    ProductChangeAuditEvent.objects.create(
        actor=user, business_id=inventory.business_id, inventory_id=inventory.pk, product=product,
        action="edit", before=before, after=after, occurred_at=timezone.now(),
    )
    return link
