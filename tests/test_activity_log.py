"""TORY-61: Manager activity log across a business."""

import csv
import io
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffInvitation
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.lifecycle import set_product_active
from catalogue.models import InventoryProduct, Product
from inventory_access.activity_log import KINDS
from inventory_access.inventory_changes import create_inventory
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.csv_import import import_stock_csv
from receiving.demand import verify_demand_day
from receiving.models import ObservationActivation
from receiving.services import (
    SINGAPORE, adjust_stock, dispose_quarantined, issue_stock, process_expiry_quarantine, receive_manual,
)


class ActivityLogTests(TransactionTestCase):
    # Deferred stock-integrity triggers run at commit, and the expiry fixture
    # alters the batch table, so each step must really commit (as in
    # tests/test_expiry_quarantine.py).

    def setUp(self):
        cls = self
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Activity business")
        cls.manager = users.create_user(email="act-manager@example.test", display_name="Mina Manager")
        cls.staff = users.create_user(email="act-staff@example.test", display_name="Sol Staff")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.manager_role = manager_role
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Main store")
        for role in (manager_role, staff_role):
            InventoryAssignment.objects.create(membership=role, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="ACT-1", name="Saline",
                                             base_unit_label="bottle", expiry_tracking_required=True,
                                             lead_time_days=2, safety_stock_units=1)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)
        # Deactivation needs zero stock, so lifecycle events use a stockless product.
        cls.spare = Product.objects.create(business=cls.business, sku="LIFE-1", name="Spare item",
                                           base_unit_label="each", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.spare)

        cls.other_business = Business.objects.create(name="Elsewhere business")
        cls.outsider = users.create_user(email="act-outsider@example.test")
        outsider_role = BusinessMembership.objects.create(business=cls.other_business, user=cls.outsider,
                                                          role="manager")
        cls.other_inventory = Inventory.objects.create(business=cls.other_business, name="Secret store")
        InventoryAssignment.objects.create(membership=outsider_role, inventory=cls.other_inventory)
        cls.other_product = Product.objects.create(business=cls.other_business, sku="SECRET-1", name="Secret",
                                                   base_unit_label="box", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.other_inventory, product=cls.other_product)

        self.url = reverse("activity-log", args=[self.business.pk])

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def receive(self, quantity=5, expiry_days=30, user=None):
        return receive_manual(user_id=(user or self.manager).pk, inventory_id=self.inventory.pk,
                              product_id=self.product.pk, request_token=uuid.uuid4(), quantity_units=quantity,
                              expiry_date=timezone.localdate() + timedelta(days=expiry_days))[0]

    def expire(self, batch):
        # Same test-only technique as tests/test_expiry_quarantine.py.
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_stock_out_guard")
            try:
                cursor.execute("UPDATE receiving_receivingbatch SET expiry_date=%s WHERE id=%s",
                               [timezone.localdate(), str(batch.pk)])
            finally:
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_stock_out_guard")
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_immutable_guard")

    def record_everything(self):
        """One event of every kind, by the expected actor."""
        # The expiry fixture alters the table, so it must run before other movements.
        doomed = self.receive(3, expiry_days=2)
        self.expire(doomed)
        batch = self.receive(10)                                                        # receipt (manager)
        issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk,              # issue (staff)
                    product_id=self.product.pk, quantity_units=2)
        adjust_stock(user_id=self.manager.pk, inventory_id=self.inventory.pk,           # adjustment
                     product_id=self.product.pk, reason="shelf recount", batch_counts=[{
                         "batch_id": batch.pk, "counted_quantity_units": 7, "manager_confirmed_identity": True}])
        process_expiry_quarantine()                                                     # quarantine (system)
        dispose_quarantined(user_id=self.manager.pk, inventory_id=self.inventory.pk,    # disposal
                            product_id=self.product.pk, batch_id=doomed.pk, quantity_units=3,
                            reason_code="Expired", reason_note="binned")
        now = timezone.now()
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=now.astimezone(SINGAPORE).date() - timedelta(days=7),
            origin_xid="1", actual_committed_at=now - timedelta(days=8), state="active")
        with patch("receiving.demand.tracking_enabled", return_value=True):
            verify_demand_day(user_id=self.manager.pk, inventory_id=self.inventory.pk,   # verification
                              product_id=self.product.pk, day=now.astimezone(SINGAPORE).date() - timedelta(days=1))
        set_product_active(user_id=self.manager.pk, inventory_id=self.inventory.pk,     # lifecycle
                           product_id=self.spare.pk, active=False)
        set_product_active(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                           product_id=self.spare.pk, active=True)
        create_inventory(user=self.manager, business_id=self.business.pk, name="Annex")  # inventory
        now = timezone.now()
        StaffInvitation.objects.create(                                                 # invitation
            target_email="new@example.test", business=self.business, manager_membership=self.manager_role,
            invited_by=self.manager, token_digest="a" * 64, issued_at=now, expires_at=now + timedelta(days=2))
        # Outside this business: must never appear.
        receive_manual(user_id=self.outsider.pk, inventory_id=self.other_inventory.pk,
                       product_id=self.other_product.pk, request_token=uuid.uuid4(), quantity_units=1,
                       expiry_date=None)

    def rows(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response.context["rows"], response

    def test_manager_only(self):
        self.assertRedirects(self.client.get(self.url), reverse("login"), fetch_redirect_response=False)
        self.login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(reverse("activity-log-csv", args=[self.business.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("inventory-list")), "Activity log")
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.login(self.manager)
        self.assertContains(self.client.get(reverse("inventory-list")), f'href="{self.url}"')

    def test_every_action_type_with_the_correct_actor_and_no_other_business(self):
        self.record_everything()
        self.login(self.manager)
        rows, response = self.rows()
        by_kind = {}
        for row in rows:
            by_kind.setdefault(row["kind"], []).append(row)
        self.assertEqual(set(by_kind), {kind for kind, _label in KINDS} - {"product"})
        expected_actor = {"receipt": self.manager, "issue": self.staff, "adjustment": self.manager,
                          "disposal": self.manager, "verification": self.manager, "lifecycle": self.manager,
                          "inventory": self.manager, "invitation": self.manager, "quarantine": None}
        for kind, actor in expected_actor.items():
            with self.subTest(kind=kind):
                self.assertEqual({row["actor"] for row in by_kind[kind]}, {actor})
        self.assertEqual(by_kind["quarantine"][0]["actor_label"], "System (expiry quarantine)")
        self.assertEqual(by_kind["issue"][0]["role"], "Staff")
        self.assertEqual(by_kind["issue"][0]["change"], -2)
        self.assertIn("Physical count 11 → 10", by_kind["adjustment"][0]["details"])
        self.assertIn("shelf recount", by_kind["adjustment"][0]["details"])
        self.assertIn("binned", by_kind["disposal"][0]["details"])
        self.assertIn("verified", by_kind["verification"][0]["details"])
        self.assertIn("Annex", by_kind["inventory"][0]["details"])
        self.assertIn("new@example.test", by_kind["invitation"][0]["details"])
        self.assertEqual({row["details"] for row in by_kind["lifecycle"]}, {"Deactivated", "Reactivated"})
        html = response.content.decode()
        self.assertIn('<span class="user-ref-name">Sol Staff</span>', html)
        for secret in ("Secret store", "SECRET-1", "act-outsider"):
            self.assertNotIn(secret, html)
        times = [row["at"] for row in rows]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_product_changes_and_csv_import_rows(self):
        self.login(self.manager)
        edit = reverse("product-edit", args=[self.inventory.pk, self.product.pk])
        self.assertEqual(self.client.post(edit, {"name": "Saline 0.9%", "base_unit_label": "bottle",
                                                 "expiry_tracking_required": "no"}).status_code, 302)
        Product.objects.filter(pk=self.product.pk).update(expiry_tracking_required=False)
        import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                         raw_bytes=b"sku,change\nACT-1,+4\nACT-1,-1\n")
        rows, _ = self.rows()
        product = [row for row in rows if row["kind"] == "product"]
        self.assertEqual(len(product), 1)
        self.assertIn("name", product[0]["details"])
        csv_rows = [row for row in rows if row["details"].startswith("CSV import")]
        self.assertEqual(sorted(row["kind"] for row in csv_rows), ["issue", "receipt"])

    def test_filters(self):
        self.record_everything()
        self.login(self.manager)
        rows, _ = self.rows(user=self.staff.pk)
        self.assertEqual({row["kind"] for row in rows}, {"issue"})
        rows, _ = self.rows(action="adjustment")
        self.assertEqual([row["kind"] for row in rows], ["adjustment"])
        annex = Inventory.objects.get(name="Annex")
        rows, _ = self.rows(inventory=annex.pk)
        self.assertEqual({row["kind"] for row in rows}, {"inventory"})
        rows, _ = self.rows(q="act-1")
        self.assertTrue(rows)
        self.assertTrue(all(row["product"] == self.product for row in rows))
        rows, _ = self.rows(q="nothing-matches")
        self.assertEqual(rows, [])
        today = timezone.now().astimezone(SINGAPORE).date()
        self.assertTrue(self.rows(start=today.isoformat(), end=today.isoformat())[0])
        self.assertEqual(self.rows(start=(today + timedelta(days=1)).isoformat())[0], [])
        self.assertEqual(self.client.get(self.url, {"start": "2026-11-20", "end": "2026-11-19"}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"user": self.outsider.pk}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"inventory": self.other_inventory.pk}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"action": "hack"}).status_code, 400)

    def test_pagination_is_50_and_keeps_filters(self):
        for _ in range(26):
            self.receive(1)
            issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                        quantity_units=1)
        self.login(self.manager)
        response = self.client.get(self.url, {"q": "ACT"})
        self.assertEqual(len(response.context["rows"]), 50)
        self.assertEqual(response.context["page"].paginator.count, 52)
        self.assertContains(response, "q=ACT&amp;page=2")
        self.assertEqual(len(self.client.get(self.url, {"q": "ACT", "page": 2}).context["rows"]), 2)

    def test_csv_export_follows_filters_and_escapes_formulas(self):
        self.record_everything()
        Product.objects.filter(pk=self.product.pk).update(name="=HYPERLINK(\"x\")")
        self.login(self.manager)
        response = self.client.get(reverse("activity-log-csv", args=[self.business.pk]), {"action": "issue"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))
        self.assertEqual(rows[0][:5], ["Time (Asia/Singapore)", "User", "Email", "Role", "Action"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1:5], ["Sol Staff", "act-staff@example.test", "Staff", "Stock issued"])
        self.assertEqual(rows[1][7], "'=HYPERLINK(\"x\")")

    def test_query_count_does_not_grow_with_rows(self):
        self.record_everything()
        self.login(self.manager)

        def count():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(self.url).status_code, 200)
            return len(queries)

        before = count()
        for _ in range(15):
            self.receive(1)
        self.assertEqual(count(), before)
