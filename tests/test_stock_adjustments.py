from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import (DemandAuditEvent, ReceiptAuditEvent, ReceivingBatch,
                              StockAdjustment, StockAdjustmentAllocation,
                              StockAdjustmentAuditEvent, StockOut)
from receiving.services import ReceiptRejected, adjust_stock, issue_stock, receive_manual


class StockAdjustmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Adjustment business")
        cls.manager = get_user_model().objects.create_user(email="adjust-manager@example.test", password="test-password")
        cls.staff = get_user_model().objects.create_user(email="adjust-staff@example.test", password="test-password")
        cls.unassigned = get_user_model().objects.create_user(email="adjust-other@example.test", password="test-password")
        cls.manager_membership = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.staff_membership = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Count shelf")
        InventoryAssignment.objects.create(membership=cls.manager_membership, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.staff_membership, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="ADJ-1", name="Count product", base_unit_label="each", expiry_tracking_required=False)
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def receive(self, quantity=5, expiry=None):
        return receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                              product_id=self.product.pk, request_token=uuid.uuid4(),
                              quantity_units=quantity, expiry_date=expiry)[0]

    def adjust(self, counts, reason="cycle count"):
        counts = [{**row, "manager_confirmed_identity": True} for row in counts]
        return adjust_stock(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                            product_id=self.product.pk, batch_counts=counts, reason=reason)

    def test_count_increase_and_decrease_update_batch_aggregate_and_non_demand_audit(self):
        expiry = timezone.localdate() + timedelta(days=30)
        batch = self.receive(5, expiry)
        adjustment = self.adjust([{"batch_id": batch.pk, "counted_quantity_units": 8}], "verified shelf count")
        batch.refresh_from_db()
        self.link.refresh_from_db()
        adjustment.refresh_from_db()
        self.assertEqual((batch.remaining_quantity_units, batch.expiry_date), (8, expiry))
        self.assertEqual((self.link.physical_quantity_units, adjustment.quantity_change_units), (8, 3))
        self.assertEqual(adjustment.audit_event.classification, "non_demand")
        self.assertEqual(adjustment.allocations.get().quantity_change_units, 3)
        self.assertEqual(DemandAuditEvent.objects.count(), 0)
        self.adjust([{"batch_id": batch.pk, "counted_quantity_units": 2}])
        batch.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual((batch.remaining_quantity_units, self.link.physical_quantity_units), (2, 2))
        self.assertEqual(StockAdjustmentAuditEvent.objects.count(), 2)

    def test_zero_count_is_valid_and_operation_cannot_be_reused(self):
        batch = self.receive(4)
        adjustment = self.adjust([{"batch_id": batch.pk, "counted_quantity_units": 0}])
        batch.refresh_from_db()
        self.link.refresh_from_db()
        adjustment.refresh_from_db()
        self.assertEqual((batch.remaining_quantity_units, self.link.physical_quantity_units), (0, 0))
        self.assertTrue(adjustment.balance_applied)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE catalogue_inventoryproduct SET physical_quantity_units=1 WHERE id=%s", [self.link.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE receiving_receivingbatch SET remaining_quantity_units=1 WHERE id=%s", [str(batch.pk)])

    def test_adjustment_updates_selected_batches_without_fefo_reallocation(self):
        today = timezone.localdate()
        first = self.receive(3, today + timedelta(days=20))
        second = self.receive(4, today + timedelta(days=2))
        adjustment = self.adjust([
            {"batch_id": first.pk, "counted_quantity_units": 6},
            {"batch_id": second.pk, "counted_quantity_units": 1},
        ])
        self.assertEqual(list(adjustment.allocations.order_by("batch__receipt_sequence").values_list("batch_id", "counted_quantity_units")),
                         [(first.pk, 6), (second.pk, 1)])
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 7)

    def test_expired_batch_is_rejected_and_unlinked_quarantine_is_blocked(self):
        today = timezone.localdate()
        expired = self.receive(3, today + timedelta(days=1))
        quarantined = self.receive(2, today + timedelta(days=2))
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_stock_out_guard")
            cursor.execute("UPDATE receiving_receivingbatch SET expiry_date=%s WHERE id=%s", [today, str(expired.pk)])
            cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_stock_out_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        before = StockAdjustment.objects.count()
        with self.assertRaises(ReceiptRejected):
            self.adjust([{"batch_id": expired.pk, "counted_quantity_units": 0}])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReceivingBatch.objects.filter(pk=quarantined.pk).update(quarantined_quantity_units=1)
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 5)
        self.assertEqual(StockAdjustment.objects.count(), before)

    def test_invalid_counts_reason_staff_and_unassigned_are_rejected(self):
        batch = self.receive(3)
        requests = [
            (self.manager.pk, [{"batch_id": batch.pk, "counted_quantity_units": -1, "manager_confirmed_identity": True}], "reason"),
            (self.manager.pk, [{"batch_id": batch.pk, "counted_quantity_units": 1, "manager_confirmed_identity": True}], "  "),
            (self.staff.pk, [{"batch_id": batch.pk, "counted_quantity_units": 1, "manager_confirmed_identity": True}], "staff attempt"),
            (self.unassigned.pk, [{"batch_id": batch.pk, "counted_quantity_units": 1, "manager_confirmed_identity": True}], "unassigned attempt"),
        ]
        for user_id, counts, reason in requests:
            with self.assertRaises(ReceiptRejected):
                adjust_stock(user_id=user_id, inventory_id=self.inventory.pk,
                             product_id=self.product.pk, batch_counts=counts, reason=reason)
        with self.assertRaises(ReceiptRejected):
            self.adjust([{"batch_id": "not-a-batch-id", "counted_quantity_units": 1}])
        self.assertEqual(StockAdjustment.objects.count(), 0)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 3)

    def test_batch_identity_confirmation_is_required(self):
        batch = self.receive(3)
        with self.assertRaises(ReceiptRejected):
            adjust_stock(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                         product_id=self.product.pk,
                         batch_counts=[{"batch_id": batch.pk, "counted_quantity_units": 5}],
                         reason="unconfirmed count")
        self.assertEqual(StockAdjustment.objects.count(), 0)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 3)

    def test_database_rejects_preapplied_adjustment_markers_and_unconfirmed_identity(self):
        batch = self.receive(2)
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO receiving_stockadjustment "
                    "(id,actor_id,inventory_id,product_id,inventory_product_id,quantity_before_units,"
                    "quantity_after_units,quantity_change_units,reason,occurred_at,balance_applied) "
                    "VALUES (%s,%s,%s,%s,%s,2,2,0,'raw attempt',%s,TRUE)",
                    [str(uuid.uuid4()), self.manager.pk, self.inventory.pk, self.product.pk, self.link.pk, now],
                )
        with self.assertRaises(IntegrityError), transaction.atomic():
            adjustment = StockAdjustment.objects.create(
                actor=self.manager, inventory=self.inventory, product=self.product,
                inventory_product=self.link, quantity_before_units=2,
                quantity_after_units=2, quantity_change_units=0, reason="raw attempt", occurred_at=now,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO receiving_stockadjustmentallocation "
                    "(adjustment_id,batch_id,quantity_before_units,counted_quantity_units,quantity_change_units,"
                    "manager_confirmed_identity,applied) VALUES (%s,%s,2,2,0,FALSE,FALSE)",
                    [str(adjustment.pk), str(batch.pk)],
                )

    def test_completed_adjustment_rejects_late_unapplied_allocation(self):
        counted = self.receive(4)
        other = self.receive(3)
        adjustment = self.adjust([{"batch_id": counted.pk, "counted_quantity_units": 2}])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO receiving_stockadjustmentallocation "
                    "(adjustment_id,batch_id,quantity_before_units,counted_quantity_units,"
                    "quantity_change_units,manager_confirmed_identity,applied) "
                    "VALUES (%s,%s,3,3,0,TRUE,FALSE)",
                    [str(adjustment.pk), str(other.pk)],
                )
        adjustment.refresh_from_db()
        self.assertTrue(adjustment.balance_applied)
        self.assertEqual(list(adjustment.allocations.values_list("batch_id", flat=True)), [counted.pk])
        self.assertEqual(StockAdjustmentAuditEvent.objects.filter(adjustment=adjustment).count(), 1)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 5)

    def test_audit_failure_rolls_back_batch_balance_allocations_and_header(self):
        batch = self.receive(5)
        with patch("receiving.services.StockAdjustmentAuditEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.adjust([{"batch_id": batch.pk, "counted_quantity_units": 2}])
        batch.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual((batch.remaining_quantity_units, self.link.physical_quantity_units), (5, 5))
        self.assertEqual(StockAdjustment.objects.count(), 0)
        self.assertEqual(StockAdjustmentAllocation.objects.count(), 0)
        self.assertEqual(StockAdjustmentAuditEvent.objects.count(), 0)

    def test_manager_confirmation_form_and_confirmation_page(self):
        batch = self.receive(5, timezone.localdate() + timedelta(days=8))
        client = Client()
        client.force_login(self.manager)
        from accounts.sessions import ACTIVE_KEY, CREATED_KEY
        now = timezone.now().timestamp()
        session = client.session
        session[CREATED_KEY] = now
        session[ACTIVE_KEY] = now
        session.save()
        url = reverse("adjust-stock", args=[self.inventory.pk, self.product.pk])
        page = client.get(url)
        self.assertContains(page, str(batch.pk))
        data = {
            "reason": "verified count", "batches-TOTAL_FORMS": "1",
            "batches-INITIAL_FORMS": "1", "batches-MIN_NUM_FORMS": "0",
            "batches-MAX_NUM_FORMS": "500", "batches-0-batch_id": str(batch.pk),
            "batches-0-counted_quantity_units": "7", "batches-0-confirmed": "on",
        }
        response = client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content.decode())
        confirmation = client.get(response.url)
        self.assertContains(confirmation, "5 → 7")
        self.assertContains(confirmation, str(batch.pk))

    def test_staff_and_unassigned_users_cannot_open_adjustment_page(self):
        url = reverse("adjust-stock", args=[self.inventory.pk, self.product.pk])
        for user in (self.staff, self.unassigned):
            client = Client()
            client.force_login(user)
            from accounts.sessions import ACTIVE_KEY, CREATED_KEY
            now = timezone.now().timestamp()
            session = client.session
            session[CREATED_KEY] = now
            session[ACTIVE_KEY] = now
            session.save()
            self.assertEqual(client.get(url).status_code, 404)


class StockAdjustmentConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.business = Business.objects.create(name="Adjustment race")
        self.user = get_user_model().objects.create_user(email="adjust-race@example.test", password="test-password")
        membership = BusinessMembership.objects.create(business=self.business, user=self.user, role="manager")
        self.inventory = Inventory.objects.create(business=self.business, name="Race shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.product = Product.objects.create(business=self.business, sku="ADJ-R", name="Race count", base_unit_label="each", expiry_tracking_required=False)
        self.link = InventoryProduct.objects.create(inventory=self.inventory, product=self.product)
        self.batch = receive_manual(user_id=self.user.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                                    request_token=uuid.uuid4(), quantity_units=5, expiry_date=None)[0]

    def call(self, barrier, operation):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            if operation == "issue":
                return issue_stock(user_id=self.user.pk, inventory_id=self.inventory.pk,
                                   product_id=self.product.pk, quantity_units=1)
            if operation == "receive":
                return receive_manual(user_id=self.user.pk, inventory_id=self.inventory.pk,
                                      product_id=self.product.pk, request_token=uuid.uuid4(),
                                      quantity_units=2, expiry_date=None)
            return adjust_stock(user_id=self.user.pk, inventory_id=self.inventory.pk,
                                product_id=self.product.pk,
                                batch_counts=[{"batch_id": self.batch.pk, "counted_quantity_units": 4, "manager_confirmed_identity": True}],
                                reason="concurrent verified count")
        finally:
            close_old_connections()

    def run_race(self, other_operation):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.call, barrier, "adjust"), pool.submit(self.call, barrier, other_operation)]
            results = [future.result(timeout=15) for future in futures]
        self.link.refresh_from_db()
        batches = list(ReceivingBatch.objects.filter(inventory_product=self.link))
        self.assertEqual(self.link.physical_quantity_units, sum(batch.remaining_quantity_units for batch in batches))
        self.assertGreaterEqual(self.link.physical_quantity_units, 0)
        self.assertEqual(StockAdjustment.objects.count(), 1)
        self.assertEqual(StockAdjustmentAuditEvent.objects.count(), 1)
        return results

    def test_adjustment_serializes_with_receiving(self):
        self.run_race("receive")
        self.assertEqual(ReceivingBatch.objects.count(), 2)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 2)

    def test_adjustment_serializes_with_stock_out(self):
        self.run_race("issue")
        self.assertEqual(StockOut.objects.count(), 1)
        self.assertEqual(DemandAuditEvent.objects.count(), 1)

    def test_late_allocation_waits_for_finalization_then_rejects(self):
        other = receive_manual(user_id=self.user.pk, inventory_id=self.inventory.pk,
                               product_id=self.product.pk, request_token=uuid.uuid4(),
                               quantity_units=2, expiry_date=None)[0]
        finalizing = Event()
        release = Event()
        started = Event()
        adjustment_id = []
        original_create = StockAdjustmentAuditEvent.objects.create

        def pause_after_balance(**kwargs):
            adjustment_id.append(kwargs["adjustment"].pk)
            finalizing.set()
            if not release.wait(timeout=10):
                raise TimeoutError("adjustment finalization was not released")
            return original_create(**kwargs)

        def writer():
            close_old_connections()
            try:
                return adjust_stock(user_id=self.user.pk, inventory_id=self.inventory.pk,
                                    product_id=self.product.pk,
                                    batch_counts=[{"batch_id": self.batch.pk, "counted_quantity_units": 4,
                                                   "manager_confirmed_identity": True}], reason="count")
            finally:
                close_old_connections()

        def late_insert():
            close_old_connections()
            try:
                started.set()
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO receiving_stockadjustmentallocation "
                            "(adjustment_id,batch_id,quantity_before_units,counted_quantity_units,"
                            "quantity_change_units,manager_confirmed_identity,applied) "
                            "VALUES (%s,%s,2,2,0,TRUE,FALSE)",
                            [str(adjustment_id[0]), str(other.pk)],
                        )
            finally:
                close_old_connections()

        with patch("receiving.services.StockAdjustmentAuditEvent.objects.create", side_effect=pause_after_balance):
            with ThreadPoolExecutor(max_workers=2) as pool:
                committed = pool.submit(writer)
                try:
                    self.assertTrue(finalizing.wait(timeout=10))
                    rejected = pool.submit(late_insert)
                    self.assertTrue(started.wait(timeout=5))
                    self.assertFalse(rejected.done())
                finally:
                    release.set()
                committed.result(timeout=15)
                with self.assertRaises(IntegrityError):
                    rejected.result(timeout=15)
        self.assertEqual(StockAdjustmentAllocation.objects.count(), 1)
        self.assertEqual(StockAdjustmentAuditEvent.objects.count(), 1)
