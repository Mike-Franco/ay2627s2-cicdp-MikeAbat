from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone as datetime_timezone
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
import uuid
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.csv_import import CsvImportRejected, import_stock_csv, parse_csv
from receiving.models import DemandAuditEvent, ReceiptAuditEvent, ReceivingBatch, StockImport, StockOut
from receiving.services import ReceiptRejected, issue_stock, receive_manual


class CsvImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="CSV business")
        cls.manager = get_user_model().objects.create_user(email="csv-manager@example.test", password="test-password")
        cls.staff = get_user_model().objects.create_user(email="csv-staff@example.test", password="test-password")
        cls.other = get_user_model().objects.create_user(email="csv-other@example.test", password="test-password")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="CSV shelf")
        cls.second = Inventory.objects.create(business=cls.business, name="Second CSV shelf")
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.second)
        InventoryAssignment.objects.create(membership=staff_role, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="P", name="Plain", base_unit_label="each", expiry_tracking_required=False)
        cls.tracked = Product.objects.create(business=cls.business, sku="T", name="Tracked", base_unit_label="each", expiry_tracking_required=True)
        cls.comma = Product.objects.create(business=cls.business, sku="P,2", name="Quoted", base_unit_label="each", expiry_tracking_required=False)
        for inventory in (cls.inventory, cls.second):
            for product in (cls.product, cls.tracked, cls.comma):
                InventoryProduct.objects.create(inventory=inventory, product=product)

    def run_import(self, raw, *, inventory=None, user=None):
        return import_stock_csv(user_id=(user or self.manager).pk,
                                inventory_id=(inventory or self.inventory).pk, raw_bytes=raw)

    def test_rows_are_ordered_and_linked_to_one_successful_import(self):
        marker = self.run_import(b"sku,change\r\n P ,+5\r\nP,+3\r\nP,-6\r\n\"P,2\",+1\r\n")
        batches = list(ReceivingBatch.objects.filter(import_record=marker).order_by("import_row_number"))
        self.assertEqual([(b.quantity_units, b.remaining_quantity_units, b.import_row_number) for b in batches],
                         [(5, 0, 2), (3, 2, 3), (1, 1, 5)])
        self.assertEqual([b.source for b in batches], ["csv"] * 3)
        out = StockOut.objects.get(import_record=marker)
        self.assertEqual(out.import_row_number, 4)
        self.assertEqual(list(out.allocations.order_by("batch__receipt_sequence").values_list("quantity_units", flat=True)), [5, 1])
        self.assertEqual(DemandAuditEvent.objects.get(stock_out=out).quantity_change_units, 6)
        self.assertEqual(ReceiptAuditEvent.objects.filter(batch__import_record=marker).count(), 3)
        self.assertEqual(InventoryProduct.objects.get(inventory=self.inventory, product=self.product).physical_quantity_units, 2)
        self.assertEqual(InventoryProduct.objects.get(inventory=self.inventory, product=self.comma).physical_quantity_units, 1)

    def test_reverse_order_or_late_invalid_row_rolls_back_everything(self):
        for raw in (b"sku,change\nP,-2\nP,+5\n", b"sku,change\nP,+5\nT,+1\n",
                    b"sku,change\nP,+1\nP,-1\nT,+1\n"):
            with self.subTest(raw=raw), self.assertRaises(CsvImportRejected):
                self.run_import(raw)
            self.assertEqual(StockImport.objects.count(), 0)
            self.assertEqual(ReceivingBatch.objects.count(), 0)
            self.assertEqual(ReceiptAuditEvent.objects.count(), 0)
            self.assertEqual(DemandAuditEvent.objects.count(), 0)
        self.assertEqual(InventoryProduct.objects.get(inventory=self.inventory, product=self.product).physical_quantity_units, 0)

    def test_exact_bytes_are_duplicate_only_after_same_inventory_success(self):
        raw = b"sku,change\nP,+1\n"
        self.run_import(raw)
        with self.assertRaises(CsvImportRejected) as error:
            self.run_import(raw)
        self.assertEqual(error.exception.category, "duplicate")
        self.run_import(raw, inventory=self.second)
        self.run_import(b"sku,change\r\nP,+1\r\n")
        self.assertEqual(StockImport.objects.count(), 3)

    def test_import_marker_day_after_issue_row_crosses_singapore_midnight(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        before = datetime(2026, 11, 7, 15, 59, 59, tzinfo=datetime_timezone.utc)
        after = datetime(2026, 11, 7, 16, 0, 1, tzinfo=datetime_timezone.utc)
        import_clock = iter((before, after))
        with patch("receiving.csv_import.timezone", SimpleNamespace(now=lambda: next(import_clock))):
            with patch("receiving.services.timezone", SimpleNamespace(
                now=lambda: before, localdate=timezone.localdate,
            )):
                marker = self.run_import(b"sku,change\nP,-1\n")
        issue = StockOut.objects.get(import_record=marker)
        audit = DemandAuditEvent.objects.get(stock_out=issue)
        singapore = ZoneInfo("Asia/Singapore")
        self.assertEqual(marker.committed_at.astimezone(singapore).date().isoformat(), "2026-11-08")
        self.assertEqual(issue.occurred_at.astimezone(singapore).date().isoformat(), "2026-11-07")
        self.assertEqual(audit.occurred_at, issue.occurred_at)
        self.assertEqual(issue.import_row_number, 2)

    def test_parser_rejects_invalid_contract_with_location_or_category(self):
        bad = [b"", b"sku,change\n", b"\xef\xbb\xbfsku,change\nP,+1\n",
               b"sku,change\nP,0\n", b"sku,change\nP,-0\n", b"sku,change\nP, 5\n",
               b"sku,change\nP,1.5\n", b"sku,change\nP,1e3\n", b"sku,change\n\n",
               b"sku,change\nP,+1,extra\n", b" sku,change\nP,+1\n",
               b"sku,change\nP,+1\r", b"sku,change\n\xff,+1\n",
               b"sku,change\n\"P\nX\",+1\n", b"sku,change\nP\"X,+1\n",
               b"sku,change\n\"P\"X,+1\n"]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(CsvImportRejected) as error:
                parse_csv(raw)
            self.assertTrue(error.exception.row or error.exception.category)
        self.assertEqual(StockImport.objects.count(), 0)
        self.assertEqual(parse_csv(b'sku,change\n"P""X",+1\n')[0][1], 'P"X')
        self.assertEqual(parse_csv(b"sku,change\nP,+0000000000001\n")[0][2], 1)
        with self.assertRaises(CsvImportRejected):
            parse_csv(b"sku,change\nP,+2147483648\n")

    def test_raw_byte_and_row_limits_are_inclusive(self):
        prefix = b"sku,change\n"
        valid = prefix + b" " * (262_144 - len(prefix) - len(b"P,+1\n")) + b"P,+1\n"
        self.assertEqual(len(valid), 262_144)
        self.assertEqual(len(parse_csv(valid)), 1)
        with self.assertRaises(CsvImportRejected):
            parse_csv(valid + b" ")
        thousand = prefix + b"P,+1\n" * 1000
        self.assertEqual(len(parse_csv(thousand)), 1000)
        with self.assertRaises(CsvImportRejected):
            parse_csv(thousand + b"P,+1\n")

    def test_quantity_cap_and_permission_scope(self):
        self.run_import(b"sku,change\nP,+2147483647\n")
        with self.assertRaises(CsvImportRejected) as error:
            self.run_import(b"sku,change\nP,+1\n")
        self.assertEqual((error.exception.row, error.exception.field), (2, "change"))
        with self.assertRaises(CsvImportRejected):
            self.run_import(b"sku,change\nP,+1\n", user=self.staff)
        with self.assertRaises(CsvImportRejected):
            self.run_import(b"sku,change\nP,+1\n", user=self.other)
        self.assertEqual(StockImport.objects.count(), 1)

    def test_unknown_and_other_business_sku_have_same_feedback(self):
        other_business = Business.objects.create(name="Hidden CSV business")
        Product.objects.create(business=other_business, sku="SECRET", name="Hidden")
        messages = []
        for sku in ("SECRET", "UNKNOWN"):
            with self.assertRaises(CsvImportRejected) as error:
                self.run_import(f"sku,change\n{sku},+1\n".encode())
            self.assertEqual((error.exception.row, error.exception.field), (2, "sku"))
            messages.append(str(error.exception))
        self.assertEqual(messages[0], messages[1])

    def test_view_requires_manager_and_reports_row_error(self):
        path = reverse("import-stock-csv", args=[self.inventory.pk])
        self.assertEqual(self.client.get(path).status_code, 302)
        self.client.force_login(self.staff)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.assertContains(self.client.get(path), self.inventory.name)
        response = self.client.post(path, {"file": SimpleUploadedFile("bad.csv", b"sku,change\nP,+1\nT,+1\n")})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Row 3, sku", status_code=400)
        self.assertEqual(StockImport.objects.count(), 0)
        self.assertEqual(self.client.post(path, {"file": SimpleUploadedFile("good.csv", b"sku,change\nP,+1\n")}).status_code, 200)


class ConcurrentCsvImportTests(TransactionTestCase):
    def setUp(self):
        business = Business.objects.create(name="Concurrent CSV")
        self.manager = get_user_model().objects.create_user(email="concurrent-csv@example.test", password="test-password")
        membership = BusinessMembership.objects.create(business=business, user=self.manager, role="manager")
        self.inventory = Inventory.objects.create(business=business, name="Concurrent shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.product = Product.objects.create(business=business, sku="P", name="Plain", base_unit_label="each", expiry_tracking_required=False)
        self.link = InventoryProduct.objects.create(inventory=self.inventory, product=self.product)

    def test_identical_files_commit_once(self):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                     raw_bytes=b"sku,change\nP,+1\n")
                    return "ok"
                except CsvImportRejected as error:
                    return error.category
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=20) for future in [pool.submit(worker), pool.submit(worker)]]
        self.assertCountEqual(results, ["ok", "duplicate"])
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 1)
        self.assertEqual(StockImport.objects.count(), 1)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)

    def test_competing_different_issue_files_cannot_oversell(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        barrier = Barrier(2)

        def worker(raw):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk, raw_bytes=raw)
                    return "ok"
                except CsvImportRejected as error:
                    return (error.row, error.field)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, raw) for raw in
                       (b"sku,change\nP,-1\n", b"sku,change\r\nP,-1\r\n")]
            outcomes = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(outcomes, ["ok", (2, "change")])
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 0)
        self.assertEqual(StockImport.objects.count(), 1)
        self.assertEqual(DemandAuditEvent.objects.count(), 1)

    def test_import_and_ordinary_issue_follow_compatible_lock_order(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        barrier = Barrier(2)

        def worker(import_file):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    if import_file:
                        import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                         raw_bytes=b"sku,change\nP,-1\n")
                    else:
                        issue_stock(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                    product_id=self.product.pk, quantity_units=1)
                    return "ok"
                except (CsvImportRejected, ReceiptRejected):
                    return "insufficient"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, import_file) for import_file in (True, False)]
            outcomes = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(outcomes, ["ok", "insufficient"])
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 0)
        self.assertEqual(StockOut.objects.count(), 1)
        self.assertEqual(DemandAuditEvent.objects.count(), 1)
