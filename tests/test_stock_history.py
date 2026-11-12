from datetime import timedelta
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import ExpiryQuarantineEvent
from receiving.services import (adjust_stock, dispose_quarantined, expiry_boundary,
                                issue_stock, process_expiry_quarantine, receive_manual)


class StockHistoryTests(TransactionTestCase):
    def setUp(self):
        self.business = Business.objects.create(name="History business")
        self.manager = get_user_model().objects.create_user(
            email="history-manager@example.test", password="test-password",
        )
        self.staff = get_user_model().objects.create_user(
            email="history-staff@example.test", password="test-password",
        )
        self.unassigned = get_user_model().objects.create_user(
            email="history-unassigned@example.test", password="test-password",
        )
        manager_membership = BusinessMembership.objects.create(
            business=self.business, user=self.manager, role="manager",
        )
        staff_membership = BusinessMembership.objects.create(
            business=self.business, user=self.staff, role="staff",
        )
        self.inventory = Inventory.objects.create(business=self.business, name="History shelf")
        InventoryAssignment.objects.create(membership=manager_membership, inventory=self.inventory)
        InventoryAssignment.objects.create(membership=staff_membership, inventory=self.inventory)
        self.product = Product.objects.create(
            business=self.business, sku="HISTORY-1", name="History item",
            base_unit_label="each", expiry_tracking_required=False,
        )
        InventoryProduct.objects.create(inventory=self.inventory, product=self.product)
        self.other_business = Business.objects.create(name="Other history business")
        self.other_user = get_user_model().objects.create_user(
            email="history-other-business@example.test", password="test-password",
        )
        other_membership = BusinessMembership.objects.create(
            business=self.other_business, user=self.other_user, role="manager",
        )
        self.other_inventory = Inventory.objects.create(
            business=self.other_business, name="Other history shelf",
        )
        InventoryAssignment.objects.create(membership=other_membership, inventory=self.other_inventory)
        self.other_product = Product.objects.create(
            business=self.other_business, sku="HISTORY-1", name="Other business item",
            base_unit_label="each", expiry_tracking_required=False,
        )
        InventoryProduct.objects.create(inventory=self.other_inventory, product=self.other_product)

    def authenticate(self, user, *, at=None):
        self.client.force_login(user)
        session = self.client.session
        stamp = (at or timezone.now()).timestamp()
        session[CREATED_KEY] = stamp
        session[ACTIVE_KEY] = stamp
        session.save()

    def product_url(self):
        return reverse("inventory-products", args=[self.inventory.pk])

    def history_url(self, inventory=None, product=None):
        return reverse("stock-history", args=[
            (inventory or self.inventory).pk, (product or self.product).pk,
        ])

    def receive(self, quantity, expiry=None, *, user=None, inventory=None, product=None):
        return receive_manual(
            user_id=(user or self.manager).pk,
            inventory_id=(inventory or self.inventory).pk,
            product_id=(product or self.product).pk,
            request_token=uuid.uuid4(), quantity_units=quantity, expiry_date=expiry,
        )[0]

    def expired_batch(self, quantity=5):
        batch = self.receive(quantity, timezone.localdate() + timedelta(days=1))
        # Ordinary receiving rejects already-expired dates. Backdate only this
        # test fixture, using the existing PostgreSQL integration-test method.
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_stock_out_guard")
            try:
                cursor.execute(
                    "UPDATE receiving_receivingbatch SET expiry_date=%s WHERE id=%s",
                    [timezone.localdate(), str(batch.pk)],
                )
            finally:
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_stock_out_guard")
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_immutable_guard")
        batch.refresh_from_db()
        return batch

    def test_both_roles_see_scoped_history_and_empty_state(self):
        self.receive(4)
        self.receive(1, user=self.other_user, inventory=self.other_inventory,
                     product=self.other_product)
        for user in (self.manager, self.staff):
            self.authenticate(user)
            products = self.client.get(self.product_url())
            self.assertContains(products, self.history_url())
            response = self.client.get(self.history_url())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context["events"]), 1)
            self.assertContains(response, "history-manager@example.test")
            self.assertNotContains(response, "history-other-business@example.test")
        empty_product = Product.objects.create(
            business=self.business, sku="HISTORY-EMPTY", name="Empty history",
        )
        InventoryProduct.objects.create(inventory=self.inventory, product=empty_product)
        self.assertContains(self.client.get(self.history_url(product=empty_product)),
                            "No stock history has been recorded")

    def test_direct_history_urls_reject_unassigned_and_other_business_users(self):
        self.assertEqual(self.client.get(self.history_url()).status_code, 302)
        for user in (self.unassigned, self.other_user):
            self.authenticate(user)
            self.assertEqual(self.client.get(self.history_url()).status_code, 404)
            self.assertEqual(self.client.get(self.history_url() + "?page=2").status_code, 404)
        self.authenticate(self.manager)
        self.assertEqual(self.client.get(self.history_url(inventory=self.other_inventory,
                                                          product=self.other_product)).status_code, 404)
        self.assertEqual(self.client.get(self.history_url(product=self.other_product)).status_code, 404)

    def test_history_pages_use_database_limit_and_stable_timestamp_ties(self):
        fixed = timezone.now()
        with patch("receiving.services.timezone.now", return_value=fixed):
            receipts = [self.receive(1) for _ in range(55)]
            issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                        product_id=self.product.pk, quantity_units=1)
        self.authenticate(self.manager)
        with CaptureQueriesContext(connection) as queries:
            first = self.client.get(self.history_url())
        self.assertEqual(first.status_code, 200)
        self.assertTrue(any("UNION ALL" in query["sql"] and "LIMIT 50" in query["sql"]
                            for query in queries.captured_queries))
        first_events = first.context["events"]
        self.assertEqual(len(first_events), 50)
        self.assertEqual([event["audit"].batch_id for event in first_events],
                         [batch.pk for batch in reversed(receipts[5:])])
        self.assertContains(first, "Page 1 of 2")
        self.assertContains(first, '?page=2')

        second = self.client.get(self.history_url() + "?page=2")
        second_events = second.context["events"]
        self.assertEqual(len(second_events), 6)
        self.assertEqual([event["kind"] for event in second_events], ["receipt"] * 5 + ["issue"])
        self.assertEqual([event["audit"].batch_id for event in second_events[:5]],
                         [batch.pk for batch in reversed(receipts[:5])])
        self.assertContains(second, "Page 2 of 2")
        self.assertContains(second, '?page=1')
        self.assertEqual(len({(event["kind"], event["audit"].pk)
                              for event in first_events + second_events}), 56)

        for value, expected in (("bad", 1), ("0", 2), ("-1", 2), ("9999", 2)):
            with self.subTest(page=value):
                response = self.client.get(self.history_url() + f"?page={value}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page"].number, expected)

    def test_balance_changes_at_midnight_before_quarantine_event(self):
        expired = self.expired_batch()
        self.receive(3, timezone.localdate() + timedelta(days=1))
        boundary = expiry_boundary(expired.expiry_date)
        self.authenticate(self.staff, at=boundary - timedelta(seconds=1))
        with patch("catalogue.views.timezone.now", return_value=boundary - timedelta(seconds=1)):
            before = self.client.get(self.product_url())
        link = before.context["product_links"][0]
        self.assertEqual((link.display_physical_units, link.display_quarantine_units, link.display_available_units), (8, 0, 8))
        with patch("catalogue.views.timezone.now", return_value=boundary):
            after = self.client.get(self.product_url())
        link = after.context["product_links"][0]
        self.assertEqual((link.display_physical_units, link.display_quarantine_units, link.display_available_units), (8, 5, 3))
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 0)

    def test_pending_expiry_balance_and_disposal_then_recording(self):
        expired = self.expired_batch()
        self.receive(3, timezone.localdate() + timedelta(days=1))
        self.authenticate(self.manager)
        before = self.client.get(self.product_url())
        link = before.context["product_links"][0]
        self.assertEqual((link.display_physical_units, link.display_quarantine_units, link.display_available_units), (8, 5, 3))
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 0)
        dispose_quarantined(
            user_id=self.manager.pk, inventory_id=self.inventory.pk,
            product_id=self.product.pk, batch_id=expired.pk,
            quantity_units=2, reason_code="Other", reason_note="  damaged packaging  ",
        )
        pending = self.client.get(self.product_url())
        link = pending.context["product_links"][0]
        self.assertEqual((link.display_physical_units, link.display_quarantine_units, link.display_available_units), (6, 3, 3))
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 0)
        self.assertEqual([event["kind"] for event in self.client.get(self.history_url()).context["events"]].count("quarantine"), 0)
        self.assertEqual(process_expiry_quarantine(), 1)
        recorded = self.client.get(self.product_url())
        link = recorded.context["product_links"][0]
        self.assertEqual((link.display_physical_units, link.display_quarantine_units, link.display_available_units), (6, 3, 3))
        history = self.client.get(self.history_url())
        self.assertContains(history, "Disposed before recording: 2 units")
        self.assertContains(history, "Reason: Other")
        self.assertContains(history, "Note: damaged packaging")

    def test_history_shows_all_five_audit_actions_and_retains_actor(self):
        ordinary = self.receive(5, timezone.localdate() + timedelta(days=2))
        issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                    product_id=self.product.pk, quantity_units=2)
        adjust_stock(
            user_id=self.manager.pk, inventory_id=self.inventory.pk,
            product_id=self.product.pk,
            batch_counts=[{"batch_id": ordinary.pk, "counted_quantity_units": 4,
                           "manager_confirmed_identity": True}],
            reason="verified count",
        )
        expired = self.expired_batch()
        self.assertEqual(process_expiry_quarantine(), 1)
        dispose_quarantined(
            user_id=self.manager.pk, inventory_id=self.inventory.pk,
            product_id=self.product.pk, batch_id=expired.pk,
            quantity_units=2, reason_code="Damaged", reason_note="seal torn",
        )
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        self.authenticate(self.manager)
        response = self.client.get(self.history_url())
        self.assertEqual(response.status_code, 200)
        events = response.context["events"]
        self.assertEqual(len(events), 6)
        self.assertEqual({event["kind"] for event in events},
                         {"receipt", "issue", "adjustment", "quarantine", "disposal"})
        self.assertContains(response, "history-staff@example.test")
        self.assertContains(response, "Reason: verified count")
        self.assertContains(response, "Reason: Damaged")
        self.assertContains(response, "Note: seal torn")
        self.assertContains(response, "system:expiry_quarantine")
        self.assertContains(response, "Effective:")
        self.assertContains(response, "Recorded:")
        self.assertContains(response, "Physical at recording: 5")
        self.assertContains(response, "Available at boundary: 5")
