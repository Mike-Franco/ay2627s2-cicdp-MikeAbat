from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, current_thread
from time import sleep
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.lifecycle import ProductLifecycleRejected, set_product_active
from catalogue.models import InventoryProduct, Product, ProductLifecycleAuditEvent
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.csv_import import CsvImportRejected, import_stock_csv
from receiving.models import ReceiptAuditEvent, ReceivingBatch
from receiving.services import (ReceiptRejected, adjust_stock, dispose_quarantined,
                                issue_stock, process_expiry_quarantine, receive_manual)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Lifecycle")
        cls.other_business = Business.objects.create(name="Other lifecycle")
        cls.manager = get_user_model().objects.create_user(email="lifecycle-manager@example.test", password="pass")
        cls.partial_manager = get_user_model().objects.create_user(email="lifecycle-partial@example.test", password="pass")
        cls.staff = get_user_model().objects.create_user(email="lifecycle-staff@example.test", password="pass")
        cls.outsider = get_user_model().objects.create_user(email="lifecycle-outsider@example.test", password="pass")
        cls.first = Inventory.objects.create(business=cls.business, name="First")
        cls.second = Inventory.objects.create(business=cls.business, name="Second unassigned")
        cls.outside = Inventory.objects.create(business=cls.other_business, name="Outside")
        for user, business, role, inventory in (
            (cls.manager, cls.business, "manager", cls.first),
            (cls.partial_manager, cls.business, "manager", cls.first),
            (cls.staff, cls.business, "staff", cls.first),
            (cls.outsider, cls.other_business, "manager", cls.outside),
        ):
            membership = BusinessMembership.objects.create(user=user, business=business, role=role)
            InventoryAssignment.objects.create(membership=membership, inventory=inventory)
            if user == cls.manager:
                InventoryAssignment.objects.create(membership=membership, inventory=cls.second)
        cls.product = Product.objects.create(business=cls.business, sku="LIFE", name="Lifecycle product",
                                             base_unit_label="each", expiry_tracking_required=False)
        cls.other_product = Product.objects.create(business=cls.other_business, sku="LIFE", name="Outside product")
        cls.first_link = InventoryProduct.objects.create(inventory=cls.first, product=cls.product)
        cls.second_link = InventoryProduct.objects.create(inventory=cls.second, product=cls.product)
        InventoryProduct.objects.create(inventory=cls.outside, product=cls.other_product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def change(self, active):
        return set_product_active(user_id=self.manager.pk, inventory_id=self.first.pk,
                                  product_id=self.product.pk, active=active)

    def test_zero_stock_deactivate_reactivate_preserves_identity_and_history(self):
        batch, _ = receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                                  product_id=self.product.pk, request_token=uuid.uuid4(),
                                  quantity_units=2, expiry_date=None)
        issue_stock(user_id=self.manager.pk, inventory_id=self.first.pk,
                    product_id=self.product.pk, quantity_units=2)
        self.login(self.manager)
        url = reverse("product-lifecycle", args=[self.first.pk, self.product.pk])
        self.assertContains(self.client.get(url), "Deactivate product")
        self.assertEqual(self.client.post(url, {"action": "deactivate"}).status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertEqual(ReceiptAuditEvent.objects.get(batch=batch).product_id, self.product.pk)
        self.assertEqual(self.client.get(reverse("stock-history", args=[self.first.pk, self.product.pk])).status_code, 200)
        self.assertContains(self.client.get(url), "Reactivate product")
        self.assertEqual(self.client.post(url, {"action": "reactivate"}).status_code, 302)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertEqual(self.product.sku, "LIFE")

    def test_lifecycle_audit_contents_history_scope_and_no_ops(self):
        self.change(False)
        event = ProductLifecycleAuditEvent.objects.get()
        self.assertEqual(event.actor_id, self.manager.pk)
        self.assertEqual(event.business_id, self.business.pk)
        self.assertEqual(event.inventory_id, self.first.pk)
        self.assertEqual(event.product_id, self.product.pk)
        self.assertEqual((event.action, event.classification), ("deactivate", "non_demand"))
        self.assertEqual((event.previous_is_active, event.new_is_active), (True, False))
        self.assertIsNotNone(event.occurred_at)
        self.change(False)
        self.assertEqual(ProductLifecycleAuditEvent.objects.count(), 1)

        self.login(self.staff)
        first_history = self.client.get(reverse("stock-history", args=[self.first.pk, self.product.pk]))
        self.assertContains(first_history, "Product deactivated")
        self.assertContains(first_history, "Active → Inactive")
        self.assertContains(first_history, self.manager.email)
        self.assertContains(first_history, "Initiated from First")
        self.login(self.manager)
        second_history = self.client.get(reverse("stock-history", args=[self.second.pk, self.product.pk]))
        self.assertNotContains(second_history, "Product deactivated")

        set_product_active(user_id=self.manager.pk, inventory_id=self.second.pk,
                           product_id=self.product.pk, active=True)
        events = list(ProductLifecycleAuditEvent.objects.order_by("pk"))
        self.assertEqual(len(events), 2)
        restored = events[1]
        self.assertEqual((restored.action, restored.previous_is_active, restored.new_is_active),
                         ("reactivate", False, True))
        self.assertEqual(restored.inventory_id, self.second.pk)
        self.change(True)
        self.assertEqual(ProductLifecycleAuditEvent.objects.count(), 2)
        second_history = self.client.get(reverse("stock-history", args=[self.second.pk, self.product.pk]))
        self.assertContains(second_history, "Product reactivated")
        self.assertContains(second_history, "Inactive → Active")
        self.assertNotContains(second_history, "Product deactivated")

    def test_audit_failure_rolls_back_status_and_failed_status_leaves_no_audit(self):
        with patch.object(ProductLifecycleAuditEvent.objects, "create", side_effect=RuntimeError("audit failed")):
            with self.assertRaisesRegex(RuntimeError, "audit failed"):
                self.change(False)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertEqual(ProductLifecycleAuditEvent.objects.count(), 0)

        with self.assertRaisesRegex(RuntimeError, "outer transaction failed"):
            with transaction.atomic():
                self.change(False)
                self.assertEqual(ProductLifecycleAuditEvent.objects.count(), 1)
                raise RuntimeError("outer transaction failed")
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertEqual(ProductLifecycleAuditEvent.objects.count(), 0)

        with patch.object(Product, "save", side_effect=RuntimeError("status failed")):
            with self.assertRaisesRegex(RuntimeError, "status failed"):
                self.change(False)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertEqual(ProductLifecycleAuditEvent.objects.count(), 0)

    def test_lifecycle_audit_is_immutable_in_postgresql(self):
        self.change(False)
        event = ProductLifecycleAuditEvent.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductLifecycleAuditEvent.objects.filter(pk=event.pk).update(action="reactivate")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductLifecycleAuditEvent.objects.filter(pk=event.pk).delete()
        self.assertEqual(ProductLifecycleAuditEvent.objects.count(), 1)

    def test_any_business_inventory_physical_stock_blocks_even_if_inactive(self):
        second_manager = get_user_model().objects.create_user(email="second-manager@example.test", password="pass")
        membership = BusinessMembership.objects.create(user=second_manager, business=self.business, role="manager")
        InventoryAssignment.objects.create(membership=membership, inventory=self.second)
        receive_manual(user_id=second_manager.pk, inventory_id=self.second.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        self.second.is_active = False
        self.second.save(update_fields=["is_active"])
        with self.assertRaisesRegex(ProductLifecycleRejected, "Physical stock must be zero"):
            self.change(False)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_authorization_and_direct_urls(self):
        url = reverse("product-lifecycle", args=[self.first.pk, self.product.pk])
        outside = reverse("product-lifecycle", args=[self.outside.pk, self.other_product.pk])
        second = reverse("product-lifecycle", args=[self.second.pk, self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        for user in (self.staff, self.outsider, self.partial_manager):
            self.login(user)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {"action": "deactivate"}).status_code, 404)
            self.assertEqual(self.client.post(url, {"action": "reactivate"}).status_code, 404)
        self.login(self.partial_manager)
        self.assertNotContains(self.client.get(reverse("inventory-products", args=[self.first.pk])),
                               reverse("product-lifecycle", args=[self.first.pk, self.product.pk]))
        for active in (False, True):
            with self.assertRaises(ProductLifecycleRejected):
                set_product_active(user_id=self.partial_manager.pk, inventory_id=self.first.pk,
                                   product_id=self.product.pk, active=active)
        self.second.is_active = False
        self.second.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(url).status_code, 404)
        with self.assertRaises(ProductLifecycleRejected):
            set_product_active(user_id=self.partial_manager.pk, inventory_id=self.first.pk,
                               product_id=self.product.pk, active=False)
        self.second.is_active = True
        self.second.save(update_fields=["is_active"])
        self.login(self.manager)
        self.assertEqual(self.client.get(second).status_code, 200)
        self.assertEqual(self.client.get(outside).status_code, 404)
        self.assertEqual(self.client.post(outside, {"action": "deactivate"}).status_code, 404)
        self.assertEqual(self.client.post(url, {"action": "invalid"}).status_code, 400)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_all_linked_assignments_required_for_both_status_changes(self):
        self.login(self.manager)
        url = reverse("product-lifecycle", args=[self.first.pk, self.product.pk])
        self.assertContains(self.client.get(reverse("inventory-products", args=[self.first.pk])),
                            reverse("product-lifecycle", args=[self.first.pk, self.product.pk]))
        self.assertEqual(self.client.post(url, {"action": "deactivate"}).status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        assignment = InventoryAssignment.objects.get(
            membership__user=self.manager, inventory=self.second,
        )
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"action": "reactivate"}).status_code, 404)
        with self.assertRaises(ProductLifecycleRejected):
            self.change(True)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        assignment.is_active = True
        assignment.save(update_fields=["is_active"])
        self.assertEqual(self.client.post(url, {"action": "reactivate"}).status_code, 302)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_inactive_product_denies_all_user_stock_writers_and_direct_urls(self):
        batch, _ = receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                                  product_id=self.product.pk, request_token=uuid.uuid4(),
                                  quantity_units=1, expiry_date=None)
        issue_stock(user_id=self.manager.pk, inventory_id=self.first.pk,
                    product_id=self.product.pk, quantity_units=1)
        self.change(False)
        call_args = dict(user_id=self.manager.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        for operation in (
            lambda: receive_manual(**call_args, request_token=uuid.uuid4(), quantity_units=1, expiry_date=None),
            lambda: issue_stock(**call_args, quantity_units=1),
            lambda: adjust_stock(**call_args, batch_counts=[{
                "batch_id": batch.pk, "counted_quantity_units": 1, "manager_confirmed_identity": True,
            }], reason="actual count"),
            lambda: dispose_quarantined(**call_args, batch_id=batch.pk, quantity_units=1,
                                        reason_code="expired", reason_note=""),
        ):
            with self.assertRaises(ReceiptRejected):
                operation()
        for change in ("+1", "-1"):
            with self.assertRaises(CsvImportRejected):
                import_stock_csv(user_id=self.manager.pk, inventory_id=self.first.pk,
                                 raw_bytes=f"sku,change\nLIFE,{change}\n".encode())
        self.login(self.manager)
        for name in ("receive-batch", "issue-stock", "adjust-stock", "dispose-stock"):
            url = reverse(name, args=[self.first.pk, self.product.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {}).status_code, 404)
        self.assertEqual(self.client.get(reverse("stock-history", args=[self.first.pk, self.product.pk])).status_code, 200)
        self.assertEqual(ReceivingBatch.objects.count(), 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductLifecycleConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Lifecycle race")
        self.manager = get_user_model().objects.create_user(email="lifecycle-race@example.test", password="pass")
        membership = BusinessMembership.objects.create(user=self.manager, business=self.business, role="manager")
        self.inventory = Inventory.objects.create(business=self.business, name="Race shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.product = Product.objects.create(business=self.business, sku="RACE-L", name="Race item",
                                              base_unit_label="each", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=self.inventory, product=self.product)

    def receive(self):
        close_old_connections()
        try:
            return receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                  product_id=self.product.pk, request_token=uuid.uuid4(),
                                  quantity_units=1, expiry_date=None)
        finally:
            close_old_connections()

    def deactivate(self):
        close_old_connections()
        try:
            return set_product_active(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                      product_id=self.product.pk, active=False)
        finally:
            close_old_connections()

    def test_receipt_first_blocks_deactivation(self):
        entered, release = Event(), Event()
        from receiving import services
        original = services._create_receipt_audit

        def held_audit(*args):
            entered.set()
            self.assertTrue(release.wait(10))
            return original(*args)

        with patch("receiving.services._create_receipt_audit", side_effect=held_audit):
            with ThreadPoolExecutor(max_workers=2) as pool:
                receipt = pool.submit(self.receive)
                self.assertTrue(entered.wait(10))
                deactivation = pool.submit(self.deactivate)
                sleep(0.1)
                release.set()
                receipt.result(timeout=15)
                with self.assertRaises(ProductLifecycleRejected):
                    deactivation.result(timeout=15)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertEqual(InventoryProduct.objects.get(product=self.product).physical_quantity_units, 1)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)

    def test_deactivation_first_blocks_receipt(self):
        entered, release = Event(), Event()
        original = Product.save
        product_id = self.product.pk

        def held_save(product, *args, **kwargs):
            if product.pk == product_id and kwargs.get("update_fields") == ["is_active"]:
                entered.set()
                self.assertTrue(release.wait(10))
            return original(product, *args, **kwargs)

        with patch.object(Product, "save", held_save):
            with ThreadPoolExecutor(max_workers=2) as pool:
                deactivation = pool.submit(self.deactivate)
                self.assertTrue(entered.wait(10))
                receipt = pool.submit(self.receive)
                sleep(0.1)
                release.set()
                deactivation.result(timeout=15)
                with self.assertRaises(ReceiptRejected):
                    receipt.result(timeout=15)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertEqual(InventoryProduct.objects.get(product=self.product).physical_quantity_units, 0)
        self.assertEqual(ReceivingBatch.objects.count(), 0)

    def test_quarantined_physical_stock_blocks_deactivation(self):
        batch, _ = self.receive_with_expiry()
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_stock_out_guard")
            try:
                cursor.execute("UPDATE receiving_receivingbatch SET expiry_date=%s WHERE id=%s",
                               [timezone.localdate() - timedelta(days=1), str(batch.pk)])
            finally:
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_stock_out_guard")
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_immutable_guard")
        self.assertEqual(process_expiry_quarantine(), 1)
        batch.refresh_from_db()
        self.assertEqual(batch.quarantined_quantity_units, 1)
        with self.assertRaises(ProductLifecycleRejected):
            self.deactivate()
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_csv_lookup_before_lock_rechecks_deactivation(self):
        entered, release = Event(), Event()
        original = Product.objects.select_for_update

        def held_product_lock(*args, **kwargs):
            if current_thread().name.startswith("csv-import-worker"):
                entered.set()
                self.assertTrue(release.wait(10))
            return original(*args, **kwargs)

        def import_worker():
            current_thread().name = "csv-import-worker"
            close_old_connections()
            try:
                return import_stock_csv(
                    user_id=self.manager.pk, inventory_id=self.inventory.pk,
                    raw_bytes=b"sku,change\nRACE-L,+1\n",
                )
            finally:
                close_old_connections()

        with patch.object(Product.objects, "select_for_update", side_effect=held_product_lock):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(import_worker)
                self.assertTrue(entered.wait(10))
                self.deactivate()
                release.set()
                with self.assertRaises(CsvImportRejected):
                    future.result(timeout=15)
        self.assertEqual(ReceivingBatch.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def receive_with_expiry(self):
        return receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                              product_id=self.product.pk, request_token=uuid.uuid4(),
                              quantity_units=1, expiry_date=timezone.localdate() + timedelta(days=1))
