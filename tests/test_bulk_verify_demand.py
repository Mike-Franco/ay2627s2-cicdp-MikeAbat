import os
from datetime import UTC, datetime, time, timedelta
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.dashboard import inventory_dashboard
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from catalogue.reorder import recommendation
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.demand import (
    reviewable_days,
    unreviewed_demand_days,
    verify_demand_days_for_inventory,
)
from receiving.models import DemandCoverageEvent, ObservationActivation
from receiving.services import ReceiptRejected, issue_stock, receive_manual

SINGAPORE = ZoneInfo("Asia/Singapore")


class BulkVerifyDemandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Bulk business")
        cls.manager = users.create_user(email="bulk-manager@example.test")
        cls.staff = users.create_user(email="bulk-staff@example.test")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Bulk shelf")
        for role in (manager_role, staff_role):
            InventoryAssignment.objects.create(membership=role, inventory=cls.inventory)
        cls.products = [
            Product.objects.create(business=cls.business, sku=f"B-{i}", name=f"Bulk item {i}",
                                   base_unit_label="each", expiry_tracking_required=False,
                                   lead_time_days=2, safety_stock_units=1)
            for i in range(3)
        ]
        for product in cls.products:
            InventoryProduct.objects.create(inventory=cls.inventory, product=product)
        other = Business.objects.create(name="Other bulk business")
        cls.outsider = users.create_user(email="bulk-outsider@example.test")
        outsider_role = BusinessMembership.objects.create(business=other, user=cls.outsider, role="manager")
        cls.other_inventory = Inventory.objects.create(business=other, name="Other shelf")
        InventoryAssignment.objects.create(membership=outsider_role, inventory=cls.other_inventory)

    def setUp(self):
        self.now = timezone.now()
        self.today = self.now.astimezone(SINGAPORE).date()
        self.yesterday = self.today - timedelta(days=1)
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=self.today - timedelta(days=7),
            origin_xid="1", actual_committed_at=self.now - timedelta(days=8), state="active",
        )
        tracking = patch("receiving.demand.tracking_enabled", return_value=True)
        tracking.start()
        self.addCleanup(tracking.stop)
        self.url = reverse("bulk-verify-demand", args=[self.inventory.pk])

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def bulk(self, days, *, user=None, at=None):
        return verify_demand_days_for_inventory(
            user_id=(user or self.manager).pk, inventory_id=self.inventory.pk, days=days, at=at or self.now,
        )

    def test_manager_verifies_yesterday_for_every_product_with_audit_events(self):
        self.login(self.manager)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.post(self.url, {"scope": "day", "day": self.yesterday.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verified 3 product-days, skipped 0")
        events = DemandCoverageEvent.objects.filter(action="verified", actor=self.manager)
        self.assertEqual(events.count(), 3)
        self.assertSetEqual(set(events.values_list("coverage_day__day", flat=True)), {self.yesterday})

    def test_staff_and_other_business_are_denied(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"scope": "day", "day": self.yesterday.isoformat()}).status_code, 404)
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"scope": "week"}).status_code, 404)
        with self.assertRaises(ReceiptRejected):
            self.bulk([self.yesterday], user=self.staff)
        self.assertFalse(DemandCoverageEvent.objects.exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_repeat_is_idempotent_and_reports_skips(self):
        first = self.bulk([self.yesterday])
        second = self.bulk([self.yesterday])
        self.assertEqual((len(first.verified), len(second.verified)), (3, 0))
        self.assertEqual(second.skipped_reasons,
                         [("This day has already been reviewed; no correction path is available.", 3)])
        self.assertEqual(DemandCoverageEvent.objects.count(), 3)

    def test_guards_still_apply_per_product(self):
        self.products[1].is_active = False
        self.products[1].save()
        with patch("receiving.demand._resolve_pending", side_effect=lambda link: link.product_id == self.products[2].pk):
            result = self.bulk([self.yesterday])
        self.assertEqual([product.pk for product, _ in result.verified], [self.products[0].pk])
        self.assertEqual(dict(result.skipped_reasons), {
            "Product is inactive.": 1,
            "Demand attribution is unresolved for this product.": 1,
        })

    def test_rejects_incomplete_or_unobserved_dates_without_partial_writes(self):
        for days in ([self.today], [self.today + timedelta(days=1)], [self.today - timedelta(days=8)],
                     [self.yesterday, self.today], []):
            with self.subTest(days=days), self.assertRaises(ReceiptRejected):
                self.bulk(days)
        self.login(self.manager)
        response = self.client.post(self.url, {"scope": "day", "day": self.today.isoformat()})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DemandCoverageEvent.objects.exists())

    def test_week_scope_makes_forecasts_numeric(self):
        self.login(self.manager)
        response = self.client.post(self.url, {"scope": "week"})
        self.assertContains(response, "Verified 21 product-days, skipped 0")
        for product in self.products:
            result = recommendation(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                    product_id=product.pk, at=self.now)
            self.assertTrue(result.forecast.available)
            self.assertIsNotNone(result.reorder_point)

    def test_week_action_is_manager_only(self):
        for user in (self.staff, self.outsider):
            self.login(user)
            self.assertEqual(self.client.post(self.url, {"scope": "week"}).status_code, 404)
        with self.assertRaises(ReceiptRejected):
            self.bulk(reviewable_days(self.now), user=self.staff)
        self.assertFalse(DemandCoverageEvent.objects.exists())

    def test_week_action_is_idempotent_and_fills_only_gaps(self):
        self.bulk([self.yesterday])
        self.login(self.manager)
        first = self.client.post(self.url, {"scope": "week"})
        self.assertContains(first, "Verified 18 product-days, skipped 3")
        second = self.client.post(self.url, {"scope": "week"})
        self.assertContains(second, "Verified 0 product-days, skipped 21")
        self.assertContains(second, "Skipped 21: This day has already been reviewed")
        self.assertEqual(DemandCoverageEvent.objects.count(), 21)

    def test_week_action_respects_guards_and_writes_audit(self):
        self.products[1].is_active = False
        self.products[1].save()
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.products[0].pk,
                       request_token=uuid4(), quantity_units=5, expiry_date=None)
        issued_on = self.today - timedelta(days=3)
        with patch("receiving.services.timezone", SimpleNamespace(
            now=lambda: datetime.combine(issued_on, time(12), SINGAPORE), localdate=timezone.localdate,
        )):
            issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                        product_id=self.products[0].pk, quantity_units=2)
        with patch("receiving.demand._resolve_pending",
                   side_effect=lambda link: link.product_id == self.products[2].pk):
            result = self.bulk(reviewable_days(self.now))
        self.assertEqual(len(result.verified), 7)
        self.assertEqual(dict(result.skipped_reasons), {
            "Product is inactive.": 7, "Demand attribution is unresolved for this product.": 7,
        })
        events = DemandCoverageEvent.objects.filter(coverage_day__inventory_product__product=self.products[0])
        self.assertEqual(events.count(), 7)
        self.assertTrue(all(event.actor_id == self.manager.pk and event.action == "verified" for event in events))
        self.assertEqual({event.coverage_day.day: event.verified_total_units for event in events if event.verified_total_units},
                         {issued_on: 2})

    def test_week_window_uses_singapore_dates_and_activation(self):
        # 00:30 on 21 Nov in Singapore is still 20 Nov in UTC.
        at = datetime(2026, 11, 20, 16, 30, tzinfo=UTC)
        ObservationActivation.objects.update(first_observed_date=datetime(2026, 11, 14).date())
        self.assertEqual([day.isoformat() for day in reviewable_days(at)],
                         [f"2026-11-{day}" for day in range(14, 21)])
        ObservationActivation.objects.update(first_observed_date=datetime(2026, 11, 18).date())
        self.assertEqual([day.isoformat() for day in reviewable_days(at)],
                         ["2026-11-18", "2026-11-19", "2026-11-20"])
        result = self.bulk(reviewable_days(at), at=at)
        self.assertEqual(len(result.verified), 9)
        self.assertNotIn(at.astimezone(SINGAPORE).date(), {day for _, day in result.verified})

    def test_singapore_date_boundaries(self):
        # 00:30 in Singapore on 21 Nov is still 20 Nov in UTC.
        at = datetime(2026, 11, 20, 16, 30, tzinfo=UTC)
        sg_today = at.astimezone(SINGAPORE).date()
        self.assertEqual(sg_today.isoformat(), "2026-11-21")
        ObservationActivation.objects.update(first_observed_date=sg_today - timedelta(days=7))
        self.assertEqual(reviewable_days(at)[-1].isoformat(), "2026-11-20")
        with self.assertRaises(ReceiptRejected):
            self.bulk([sg_today], at=at)
        # An issue at 23:30 Singapore time on 20 Nov (15:30 UTC) belongs to 20 Nov.
        late = datetime.combine(sg_today - timedelta(days=1), time(23, 30), SINGAPORE)
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.products[0].pk,
                       request_token=uuid4(), quantity_units=5, expiry_date=None)
        with patch("receiving.services.timezone", SimpleNamespace(now=lambda: late, localdate=timezone.localdate)):
            issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                        product_id=self.products[0].pk, quantity_units=2)
        result = self.bulk([sg_today - timedelta(days=1)], at=at)
        self.assertEqual(len(result.verified), 3)
        event = DemandCoverageEvent.objects.get(coverage_day__inventory_product__product=self.products[0])
        self.assertEqual(event.verified_total_units, 2)

    def test_dashboard_nudge_counts_unreviewed_days_for_managers_only(self):
        self.bulk([self.yesterday])
        expected = 3 * 7 - 3
        self.assertEqual(unreviewed_demand_days([self.inventory.pk], at=self.now), {self.inventory.pk: expected})
        self.assertEqual(inventory_dashboard(self.manager, at=self.now)["unreviewed_demand"],
                         [(self.inventory, expected)])
        self.assertEqual(inventory_dashboard(self.staff, at=self.now)["unreviewed_demand"], [])
        self.login(self.manager)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f"{expected} unverified demand days")
        self.assertContains(response, f"{self.url}?scope=week")

    def test_forecast_page_shows_status_chips(self):
        self.bulk([self.yesterday])
        self.login(self.manager)
        response = self.client.get(reverse("demand-forecast", args=[self.inventory.pk, self.products[0].pk]))
        self.assertContains(response, 'class="status-pill success"', count=1)
        self.assertContains(response, 'class="status-pill neutral"', count=6)
        self.assertContains(response, f"{self.url}?scope=week")


class BulkVerifySeedDemoTests(TestCase):
    ENV = {"DEMO_MANAGER_EMAIL": "bulk-seed-manager@example.test",
           "DEMO_STAFF_EMAIL": "bulk-seed-staff@example.test",
           "DEMO_MANAGER_PASSWORD": "bulk-seed-password-1!", "DEMO_STAFF_PASSWORD": "bulk-seed-password-2!"}

    def test_fresh_seed_is_fully_verified_and_idempotent(self):
        with patch.dict(os.environ, self.ENV):
            call_command("seed_demo", stdout=StringIO())
        manager = get_user_model().objects.get(email=self.ENV["DEMO_MANAGER_EMAIL"])
        links = list(InventoryProduct.objects.filter(inventory__business__name="Tory Demo"))
        self.assertEqual(len(links), 15)
        for link in links:
            result = recommendation(user_id=manager.pk, inventory_id=link.inventory_id, product_id=link.product_id)
            self.assertIsNotNone(result.reorder_point, link.product.sku)
        now = timezone.now()
        self.assertEqual(inventory_dashboard(manager, at=now)["unreviewed_demand"], [])
        events = DemandCoverageEvent.objects.count()
        with patch.dict(os.environ, self.ENV):
            call_command("seed_demo", stdout=StringIO())
        self.assertEqual(DemandCoverageEvent.objects.count(), events)
        for inventory_id in {link.inventory_id for link in links}:
            result = verify_demand_days_for_inventory(user_id=manager.pk, inventory_id=inventory_id,
                                                      days=reviewable_days(now), at=now)
            self.assertEqual(result.verified, ())
        self.assertEqual(DemandCoverageEvent.objects.count(), events)
