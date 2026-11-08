"""Atomic, inventory-scoped stock transaction CSV import."""

import csv
import hashlib
import io
import re
import uuid

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from catalogue.models import InventoryProduct, Product
from inventory_access.models import BusinessMembership, Inventory

from .models import MAX_RECEIPT_UNITS, ReceivingBatch, StockImport
from .services import ReceiptRejected, _create_receipt_audit, _fingerprint, issue_stock


MAX_BYTES = 262_144
MAX_ROWS = 1_000
CHANGE = re.compile(r"[+-]?[0-9]+\Z")


class CsvImportRejected(Exception):
    def __init__(self, message, *, row=None, field=None, category="invalid_file"):
        self.row = row
        self.field = field
        self.category = category
        super().__init__(message)


def _check_quote_syntax(record, number):
    """Reject bare quotes that Python's CSV reader otherwise accepts."""
    state = "start"
    index = 0
    while index < len(record):
        char = record[index]
        if state == "start":
            state = "quoted" if char == '"' else ("start" if char == "," else "unquoted")
        elif state == "unquoted":
            if char == '"':
                raise CsvImportRejected("Malformed CSV quoting.", row=number, category="row_shape")
            if char == ",":
                state = "start"
        elif state == "quoted":
            if char == '"':
                if index + 1 < len(record) and record[index + 1] == '"':
                    index += 1
                else:
                    state = "closed"
        elif char == ",":
            state = "start"
        else:
            raise CsvImportRejected("Malformed CSV quoting.", row=number, category="row_shape")
        index += 1
    if state == "quoted":
        raise CsvImportRejected("Malformed CSV quoting.", row=number, category="row_shape")


def parse_csv(raw):
    if not isinstance(raw, bytes):
        raise CsvImportRejected("Upload a CSV file.")
    if len(raw) > MAX_BYTES:
        raise CsvImportRejected("File exceeds 262,144 raw bytes.", category="file_size")
    if not raw:
        raise CsvImportRejected("File is empty.", category="empty_file")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CsvImportRejected("UTF-8 BOM is not allowed.", category="encoding")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise CsvImportRejected("File must be strict UTF-8.", category="encoding") from error
    if "\r" in text.replace("\r\n", ""):
        raise CsvImportRejected("Use LF or CRLF line endings.", category="line_endings")
    if text.split("\n", 1)[0].removesuffix("\r") != "sku,change":
        raise CsvImportRejected("Header must be exactly sku,change.", category="header")
    for number, record in enumerate(text.split("\n")[1:], start=2):
        _check_quote_syntax(record.removesuffix("\r"), number)
    rows = []
    try:
        csv.field_size_limit(MAX_BYTES)
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        next(reader)
        for number, fields in enumerate(reader, start=2):
            if number > MAX_ROWS + 1:
                raise CsvImportRejected("File exceeds 1,000 data rows.", category="row_limit")
            if len(fields) != 2:
                raise CsvImportRejected("Expected exactly two fields.", row=number, category="row_shape")
            sku, change = fields
            if "\n" in sku or "\r" in sku or "\n" in change or "\r" in change:
                raise CsvImportRejected("Embedded record newline is not allowed.", row=number, category="row_shape")
            sku = sku.strip(" ")
            if not sku:
                raise CsvImportRejected("SKU is required.", row=number, field="sku")
            if not CHANGE.fullmatch(change):
                raise CsvImportRejected("Change must be a nonzero whole number.", row=number, field="change")
            digits = change.lstrip("+-").lstrip("0")
            if len(digits) > 10 or (len(digits) == 10 and digits > str(MAX_RECEIPT_UNITS)):
                raise CsvImportRejected("Change exceeds the supported stock range.", row=number, field="change")
            if not digits:
                raise CsvImportRejected("Change must be nonzero within the stock limit.", row=number, field="change")
            amount = int(digits) * (-1 if change.startswith("-") else 1)
            rows.append((number, sku, amount))
    except csv.Error as error:
        raise CsvImportRejected("Malformed CSV record.", row=len(rows) + 2,
                                category="row_shape") from error
    if not rows:
        raise CsvImportRejected("File has no data rows.", category="header_only")
    return rows


def import_stock_csv(*, user_id, inventory_id, raw_bytes):
    rows = parse_csv(raw_bytes)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    with transaction.atomic():
        try:
            hint = Inventory.objects.only("business_id").get(pk=inventory_id, is_active=True)
        except Inventory.DoesNotExist as error:
            raise CsvImportRejected("Inventory is unavailable.", category="authorization") from error
        # Shared authorization locks match the existing stock writers. Product,
        # inventory and link locks follow their established parent order.
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_active FROM accounts_user WHERE id=%s FOR SHARE", [user_id])
            user_row = cursor.fetchone()
            cursor.execute(
                "SELECT id, role, is_active FROM inventory_access_businessmembership "
                "WHERE user_id=%s AND business_id=%s FOR SHARE", [user_id, hint.business_id],
            )
            membership = cursor.fetchone()
            if not user_row or not user_row[0] or not membership or membership[1:] != ("manager", True):
                raise CsvImportRejected("Inventory is unavailable.", category="authorization")
            cursor.execute(
                "SELECT is_active FROM inventory_access_inventoryassignment "
                "WHERE membership_id=%s AND inventory_id=%s FOR SHARE", [membership[0], inventory_id],
            )
            assignment = cursor.fetchone()
            if not assignment or not assignment[0]:
                raise CsvImportRejected("Inventory is unavailable.", category="authorization")
        user = get_user_model().objects.get(pk=user_id)
        products = {}
        for number, sku, _ in rows:
            key = sku.casefold()
            if key not in products:
                product = Product.objects.filter(
                    business_id=hint.business_id, sku__iexact=sku, is_active=True,
                ).first()
                if product is None:
                    raise CsvImportRejected("SKU is unavailable in this inventory.", row=number, field="sku")
                products[key] = product
        for product_id in sorted({product.pk for product in products.values()}):
            Product.objects.select_for_update().get(pk=product_id)
        inventory = Inventory.objects.select_for_update().get(pk=inventory_id, business_id=hint.business_id, is_active=True)
        links = {}
        for product_id in sorted({product.pk for product in products.values()}):
            link = InventoryProduct.objects.select_for_update().filter(
                inventory=inventory, product_id=product_id,
            ).first()
            if link is None:
                row = next(number for number, sku, _ in rows if products[sku.casefold()].pk == product_id)
                raise CsvImportRejected("SKU is unavailable in this inventory.", row=row, field="sku")
            links[product_id] = link
        for prior in StockImport.objects.filter(inventory=inventory, sha256=digest):
            if bytes(prior.raw_bytes) == raw_bytes:
                raise CsvImportRejected("File was already imported into this inventory.", category="duplicate")
        import_record = StockImport.objects.create(
            actor=user, inventory=inventory, raw_bytes=raw_bytes,
            sha256=digest, committed_at=timezone.now(),
        )
        for number, sku, change in rows:
            product = products[sku.casefold()]
            link = links[product.pk]
            if change > 0:
                if product.expiry_tracking_required is not False or not product.base_unit_label:
                    raise CsvImportRejected("Product cannot receive stock from CSV.", row=number, field="sku")
                link.refresh_from_db()
                before = link.physical_quantity_units
                if before + change > MAX_RECEIPT_UNITS:
                    raise CsvImportRejected("Physical stock limit would be exceeded.", row=number, field="change")
                batch = ReceivingBatch.objects.create(
                    actor=user, inventory=inventory, product=product, inventory_product=link,
                    source=ReceivingBatch.Source.CSV, request_token=uuid.uuid4(),
                    input_fingerprint=_fingerprint(inventory_id, product.pk, change, None),
                    quantity_units=change, remaining_quantity_units=change,
                    unit_label_snapshot=product.base_unit_label, expiry_date=None,
                    receipt_sequence=link.last_receipt_sequence + 1, received_at=timezone.now(),
                    import_record=import_record, import_row_number=number,
                )
                _create_receipt_audit(batch, before)
            else:
                try:
                    issue_stock(user_id=user_id, inventory_id=inventory_id,
                                product_id=product.pk, quantity_units=-change,
                                import_record=import_record, import_row_number=number)
                except ReceiptRejected as error:
                    raise CsvImportRejected(str(error), row=number, field="change") from error
        import_record.committed_at = timezone.now()
        import_record.save(update_fields=["committed_at"])
        return import_record
