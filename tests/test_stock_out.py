from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import DemandAuditEvent, ReceiptAuditEvent, ReceivingBatch, StockOut, StockOutAllocation
from receiving.services import ReceiptRejected, issue_stock, receive_manual


class StockOutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Issue business")
        cls.manager = get_user_model().objects.create_user(email="issue-manager@example.test", password="test-password")
        cls.staff = get_user_model().objects.create_user(email="issue-staff@example.test", password="test-password")
        cls.other = get_user_model().objects.create_user(email="issue-other@example.test", password="test-password")
        cls.manager_membership = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.staff_membership = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Issue shelf")
        InventoryAssignment.objects.create(membership=cls.manager_membership, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.staff_membership, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="ISS-1", name="Issue product", base_unit_label="each", expiry_tracking_required=False)
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def receive(self, quantity, expiry=None):
        return receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                              request_token=uuid.uuid4(), quantity_units=quantity, expiry_date=expiry)[0]

    def issue(self, quantity=1, user=None):
        return issue_stock(user_id=(user or self.manager).pk, inventory_id=self.inventory.pk,
                           product_id=self.product.pk, quantity_units=quantity)

    def test_fefo_dated_then_undated_and_equal_expiry_sequence_tie(self):
        today = timezone.localdate()
        late = self.receive(2, today + timedelta(days=5))
        tie1 = self.receive(2, today + timedelta(days=2))
        tie2 = self.receive(1, today + timedelta(days=2))
        undated = self.receive(4)
        out = self.issue(8)
        allocations = list(out.allocations.order_by("batch__expiry_date", "batch__receipt_sequence", "batch_id").values_list("batch_id", "quantity_units"))
        self.assertEqual(allocations, [(tie1.pk, 2), (tie2.pk, 1), (late.pk, 2), (undated.pk, 3)])
        self.assertEqual(out.audit_event.quantity_change_units, 8)
        self.assertEqual(self.link.__class__.objects.get(pk=self.link.pk).physical_quantity_units, 1)

    def test_excludes_expired_units_and_applies_midnight_rule(self):
        today = timezone.localdate()
        expired = self.receive(3, today + timedelta(days=1))
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_stock_out_guard")
            cursor.execute("UPDATE receiving_receivingbatch SET expiry_date=%s WHERE id=%s", [today, str(expired.pk)])
            cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_stock_out_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        eligible = self.receive(5, today + timedelta(days=1))
        out = self.issue(5)
        self.assertEqual(list(out.allocations.values_list("batch_id", "quantity_units")), [(eligible.pk, 5)])
        with self.assertRaises(ReceiptRejected):
            self.issue(1)

    def test_shortage_rejects_without_mutation_and_manager_staff_authorized(self):
        batch = self.receive(2)
        with self.assertRaises(ReceiptRejected):
            self.issue(3)
        self.assertEqual(StockOut.objects.count(), 0)
        self.assertEqual(self.link.__class__.objects.get(pk=self.link.pk).physical_quantity_units, 2)
        out = self.issue(1, self.staff)
        self.assertEqual(out.actor_id, self.staff.pk)
        with self.assertRaises(ReceiptRejected):
            self.issue(1, self.other)

    def test_audit_failure_rolls_back_batch_balance_and_allocation(self):
        self.receive(4)
        with patch("receiving.services._create_demand_audit", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                self.issue(2)
        self.assertEqual(StockOut.objects.count(), 0)
        self.assertEqual(StockOutAllocation.objects.count(), 0)
        batch = ReceivingBatch.objects.get()
        self.assertEqual(batch.remaining_quantity_units, 4)
        self.assertEqual(self.link.__class__.objects.get(pk=self.link.pk).physical_quantity_units, 4)
        self.assertEqual(DemandAuditEvent.objects.count(), 0)

    def test_setting_former_transaction_flag_cannot_bypass_balance_or_sequence_guards(self):
        self.receive(4)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('tory.stock_out_write', 'on', true)")
                cursor.execute("UPDATE catalogue_inventoryproduct SET physical_quantity_units=3 WHERE id=%s", [self.link.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE catalogue_inventoryproduct SET last_receipt_sequence=2 WHERE id=%s", [self.link.pk])
        self.link.refresh_from_db()
        self.assertEqual((self.link.physical_quantity_units, self.link.last_receipt_sequence), (4, 1))

    def test_old_stock_out_allocation_cannot_authorize_second_balance_decrement(self):
        self.receive(6)
        self.issue(3)
        self.receive(3)
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 6)
        issued_batch = ReceivingBatch.objects.order_by("receipt_sequence").first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE receiving_receivingbatch SET remaining_quantity_units=0 WHERE id=%s", [str(issued_batch.pk)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE catalogue_inventoryproduct SET physical_quantity_units=3 WHERE id=%s", [self.link.pk])
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 6)
        self.assertEqual(StockOut.objects.count(), 1)
        self.assertEqual(StockOutAllocation.objects.count(), 1)
        self.assertEqual(DemandAuditEvent.objects.count(), 1)
        self.assertEqual(ReceivingBatch.objects.count(), 2)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 2)

    def test_raw_batch_decrement_without_stock_out_is_rejected(self):
        batch = self.receive(5)
        receipt_count = ReceiptAuditEvent.objects.count()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE receiving_receivingbatch SET remaining_quantity_units=2 WHERE id=%s", [str(batch.pk)])
        batch.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual(batch.remaining_quantity_units, 5)
        self.assertEqual(self.link.physical_quantity_units, 5)
        self.assertEqual(StockOut.objects.count(), 0)
        self.assertEqual(StockOutAllocation.objects.count(), 0)
        self.assertEqual(ReceivingBatch.objects.count(), 1)
        self.assertEqual(ReceiptAuditEvent.objects.count(), receipt_count)

    def test_stockout_balance_marker_must_start_false_for_sql_and_bulk_inserts(self):
        now = timezone.now()
        fields = [str(uuid.uuid4()), self.manager.pk, self.inventory.pk, self.product.pk, self.link.pk, now]
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO receiving_stockout "
                    "(id, actor_id, inventory_id, product_id, inventory_product_id, quantity_units, "
                    "quantity_before_units, quantity_after_units, occurred_at, balance_applied) "
                    "VALUES (%s,%s,%s,%s,%s,3,6,3,%s,TRUE)", fields,
                )
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockOut.objects.bulk_create([StockOut(
                id=uuid.uuid4(), actor=self.manager, inventory=self.inventory, product=self.product,
                inventory_product=self.link, quantity_units=3, quantity_before_units=6,
                quantity_after_units=3, occurred_at=now, balance_applied=True,
            )])

    def test_allocation_applied_marker_must_start_false_for_sql_and_bulk_inserts(self):
        batch = self.receive(6)
        stock_out = self.issue(3)
        raw_batch = self.receive(1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO receiving_stockoutallocation (stock_out_id,batch_id,quantity_units,applied) "
                    "VALUES (%s,%s,1,TRUE)", [str(stock_out.pk), str(raw_batch.pk)],
                )
        bulk_batch = self.receive(1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockOutAllocation.objects.bulk_create([StockOutAllocation(
                stock_out=stock_out, batch=bulk_batch, quantity_units=1, applied=True,
            )])
        stock_out.refresh_from_db()
        self.assertTrue(stock_out.balance_applied)

    def test_preapplied_allocation_cannot_authorize_balance_without_batch_decrement(self):
        batch = self.receive(6)
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                stock_out_id = uuid.uuid4()
                cursor.execute(
                    "INSERT INTO receiving_stockout "
                    "(id,actor_id,inventory_id,product_id,inventory_product_id,quantity_units,"
                    "quantity_before_units,quantity_after_units,occurred_at,balance_applied) "
                    "VALUES (%s,%s,%s,%s,%s,3,6,3,%s,FALSE)",
                    [str(stock_out_id), self.manager.pk, self.inventory.pk, self.product.pk, self.link.pk, now],
                )
                cursor.execute(
                    "INSERT INTO receiving_stockoutallocation (stock_out_id,batch_id,quantity_units,applied) "
                    "VALUES (%s,%s,3,TRUE)", [str(stock_out_id), str(batch.pk)],
                )
                cursor.execute("UPDATE catalogue_inventoryproduct SET physical_quantity_units=3 WHERE id=%s", [self.link.pk])
                DemandAuditEvent.objects.create(
                    stock_out_id=stock_out_id, actor=self.manager, business=self.business,
                    inventory=self.inventory, product=self.product, quantity_before_units=6,
                    quantity_change_units=3, quantity_after_units=3, occurred_at=now,
                )
        self.link.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 6)
        self.assertEqual(batch.remaining_quantity_units, 6)
        self.assertEqual(StockOut.objects.count(), 0)
        self.assertEqual(StockOutAllocation.objects.count(), 0)

    def test_issue_action_and_confirmation_list_batches(self):
        self.receive(2)
        client = Client()
        client.force_login(self.manager)
        session = client.session
        now = timezone.now().timestamp()
        from accounts.sessions import ACTIVE_KEY, CREATED_KEY
        session[CREATED_KEY] = now
        session[ACTIVE_KEY] = now
        session.save()
        url = reverse("issue-stock", args=[self.inventory.pk, self.product.pk])
        self.assertEqual(client.get(url).status_code, 200)
        response = client.post(url, {"quantity_units": "1"})
        self.assertEqual(response.status_code, 302)
        confirmation = client.get(response.url)
        self.assertContains(confirmation, "Batches used")
        self.assertContains(confirmation, "1 each")


class StockOutConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.business = Business.objects.create(name="Issue race")
        self.user = get_user_model().objects.create_user(email="issue-race@example.test", password="test-password")
        membership = BusinessMembership.objects.create(business=self.business, user=self.user, role="manager")
        self.inventory = Inventory.objects.create(business=self.business, name="Race shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.product = Product.objects.create(business=self.business, sku="RACE-I", name="Race", base_unit_label="unit", expiry_tracking_required=False)
        self.link = InventoryProduct.objects.create(inventory=self.inventory, product=self.product)
        receive_manual(user_id=self.user.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                       request_token=uuid.uuid4(), quantity_units=1, expiry_date=None)

    def call(self, barrier, action):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            if action == "issue":
                return issue_stock(user_id=self.user.pk, inventory_id=self.inventory.pk, product_id=self.product.pk, quantity_units=1)
            return receive_manual(user_id=self.user.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                                  request_token=uuid.uuid4(), quantity_units=1, expiry_date=None)
        finally:
            close_old_connections()

    def test_competing_issues_cannot_double_allocate(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.call, barrier, "issue") for _ in range(2)]
            results = []
            for future in futures:
                try:
                    results.append(future.result(timeout=10))
                except ReceiptRejected:
                    results.append(None)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(StockOut.objects.count(), 1)
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 0)
        self.assertEqual(StockOutAllocation.objects.count(), 1)
        self.assertEqual(DemandAuditEvent.objects.count(), 1)

    def test_receiving_and_stock_out_serialize_without_lost_balance(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.call, barrier, action) for action in ("issue", "receive")]
            results = [future.result(timeout=10) for future in futures]
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 1)
        self.assertEqual(StockOut.objects.count(), 1)
        self.assertEqual(ReceivingBatch.objects.count(), 2)
        self.assertEqual(DemandAuditEvent.objects.count(), 1)
