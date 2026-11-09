from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from fractions import Fraction
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.commit_times import tracking_enabled
from receiving.csv_import import CsvImportRejected, import_stock_csv
from receiving.demand import mark_demand_day_incomplete, seven_day_forecast, verify_demand_day
from receiving.models import (DemandAuditEvent, DemandCoverageDay, DemandCoverageEvent,
                              ObservationActivation, StockImport)
from receiving.services import ReceiptRejected, issue_stock, receive_manual


SINGAPORE = ZoneInfo("Asia/Singapore")


class DemandForecastTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Demand business")
        cls.manager = get_user_model().objects.create_user(email="demand-manager@example.test", password="test-password")
        cls.staff = get_user_model().objects.create_user(email="demand-staff@example.test", password="test-password")
        cls.outsider = get_user_model().objects.create_user(email="demand-outsider@example.test", password="test-password")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Demand shelf")
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=staff_role, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="D", name="Demand item",
                                             base_unit_label="each", expiry_tracking_required=False)
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def setUp(self):
        self.now = timezone.now()
        self.today = self.now.astimezone(SINGAPORE).date()
        self.activation = ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=self.today - timedelta(days=7),
            origin_xid="1", actual_committed_at=self.now - timedelta(days=8), state="active",
        )

    def verify(self, day):
        with patch("receiving.demand.tracking_enabled", return_value=True):
            return verify_demand_day(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                     product_id=self.product.pk, day=day, at=self.now)

    def forecast(self):
        with patch("receiving.demand.tracking_enabled", return_value=True):
            return seven_day_forecast(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                      product_id=self.product.pk, at=self.now)

    def issue_on(self, day):
        action_at = datetime.combine(day, time(12), SINGAPORE)
        with patch("receiving.services.timezone", SimpleNamespace(
            now=lambda: action_at, localdate=timezone.localdate,
        )):
            return issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                               product_id=self.product.pk, quantity_units=1)

    def authenticate(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def test_verified_zero_and_exact_three_sevenths(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=3, expiry_date=None)
        dates = [self.today - timedelta(days=n) for n in range(7, 0, -1)]
        for index in (0, 2, 4):
            self.issue_on(dates[index])
        for day in dates:
            self.verify(day)
        result = self.forecast()
        self.assertTrue(result.available)
        self.assertEqual(result.average, Fraction(3, 7))
        self.assertEqual(result.displayed_average, "0.43")
        self.assertEqual(DemandAuditEvent.objects.count(), 3)
        self.assertEqual([event.verified_total_units for event in DemandCoverageEvent.objects.order_by("coverage_day__day")],
                         [1, 0, 1, 0, 1, 0, 0])

    def test_missing_incomplete_late_issue_and_tracking_off_suppress(self):
        dates = [self.today - timedelta(days=n) for n in range(7, 0, -1)]
        for day in dates[:-1]:
            self.verify(day)
        self.assertFalse(self.forecast().available)
        self.verify(dates[-1])
        self.assertEqual(self.forecast().average, Fraction(0, 1))
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        self.issue_on(dates[0])
        late = self.forecast()
        self.assertFalse(late.available)
        self.assertEqual(late.days[0][1], "invalidated")
        mark_demand_day_incomplete(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                   product_id=self.product.pk, day=dates[0], reason="  missing issue found  ")
        self.assertEqual(DemandCoverageEvent.objects.filter(coverage_day__day=dates[0]).count(), 2)
        self.assertFalse(self.forecast().available)
        with self.assertRaises(ReceiptRejected):
            self.verify(dates[0])
        self.assertFalse(seven_day_forecast(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                            product_id=self.product.pk, at=self.now).available)

    def test_partial_activation_day_and_roles(self):
        self.activation.first_observed_date = self.today - timedelta(days=6)
        self.activation.save(update_fields=["first_observed_date"])
        with self.assertRaises(ReceiptRejected):
            self.verify(self.today - timedelta(days=7))
        self.assertFalse(self.forecast().available)
        with self.assertRaises(ReceiptRejected):
            verify_demand_day(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                              product_id=self.product.pk, day=self.today - timedelta(days=1))
        with self.assertRaises(ReceiptRejected):
            mark_demand_day_incomplete(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                                       product_id=self.product.pk, day=self.today - timedelta(days=1), reason="gap")
        with self.assertRaises(ReceiptRejected):
            self.verify(self.today)

    def test_forecast_view_scope_and_manager_actions(self):
        url = reverse("demand-forecast", args=[self.inventory.pk, self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.authenticate(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.authenticate(self.staff)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"day": str(self.today - timedelta(days=1)),
                                                "action": "verify"}).status_code, 404)
        self.authenticate(self.manager)
        response = self.client.get(url)
        self.assertContains(response, "Forecast unavailable")
        self.assertContains(response, "Verify complete day")
        self.assertContains(response, "Mark verified day incomplete")
        with patch("receiving.demand.tracking_enabled", return_value=True):
            response = self.client.post(url, {"day": str(self.today - timedelta(days=1)),
                                              "action": "verify"})
        self.assertEqual(response.status_code, 302)
        with patch("receiving.demand.tracking_enabled", return_value=True):
            response = self.client.post(url, {"day": str(self.today - timedelta(days=1)),
                                              "action": "incomplete", "reason": "  found a gap  "})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DemandCoverageEvent.objects.latest("pk").reason, "found a gap")

    def test_inactive_observation_hides_controls_and_rejects_manager_posts(self):
        self.activation.delete()
        day = self.today - timedelta(days=1)
        url = reverse("demand-forecast", args=[self.inventory.pk, self.product.pk])
        self.authenticate(self.manager)
        response = self.client.get(url)
        self.assertContains(response, "Demand observation has not been activated")
        self.assertNotContains(response, "Verify complete day")
        self.assertNotContains(response, "Mark verified day incomplete")
        for action in ("verify", "incomplete"):
            response = self.client.post(url, {"day": str(day), "action": action, "reason": "gap"})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(DemandCoverageEvent.objects.count(), 0)

    def test_pending_observation_blocks_invalidation_of_prior_verification(self):
        day = self.today - timedelta(days=1)
        self.verify(day)
        self.activation.state = "pending"
        self.activation.save(update_fields=["state"])
        with self.assertRaises(ReceiptRejected):
            mark_demand_day_incomplete(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                       product_id=self.product.pk, day=day, reason="gap")
        url = reverse("demand-forecast", args=[self.inventory.pk, self.product.pk])
        self.authenticate(self.manager)
        self.assertNotContains(self.client.get(url), "Mark verified day incomplete")
        response = self.client.post(url, {"day": str(day), "action": "incomplete", "reason": "gap"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DemandCoverageEvent.objects.filter(coverage_day__day=day).count(), 1)

    def test_unresolved_csv_keeps_stock_and_duplicate_guard(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        raw = b"sku,change\nD,-1\n"
        with patch("receiving.csv_import.tracking_enabled", return_value=False):
            record = import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk, raw_bytes=raw)
        self.assertTrue(record.observation_eligible)
        self.assertEqual(record.commit_attribution, "unavailable")
        self.assertIsNone(record.actual_committed_at)
        self.assertEqual(self.link.receiving_batches.count(), 1)
        with self.assertRaises(CsvImportRejected):
            import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk, raw_bytes=raw)
        for day in (self.today - timedelta(days=n) for n in range(7, 0, -1)):
            with self.assertRaises(ReceiptRejected):
                self.verify(day)
        self.assertEqual(StockImport.objects.count(), 1)

    def test_csv_actual_commit_day_on_both_sides_of_singapore_midnight(self):
        self.now = datetime(2026, 11, 9, 12, tzinfo=SINGAPORE)
        self.today = self.now.date()
        self.activation.first_observed_date = date(2026, 11, 2)
        self.activation.save(update_fields=["first_observed_date"])
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=3, expiry_date=None)
        boundary = datetime(2026, 11, 8, 0, tzinfo=SINGAPORE)
        samples = (
            (b"sku,change\nD,-1\n", boundary - timedelta(microseconds=1), boundary),
            (b"sku,change\nD,-2\n", boundary, boundary - timedelta(microseconds=1)),
        )
        for raw, actual_commit, row_time in samples:
            with patch("receiving.services.timezone", SimpleNamespace(
                now=lambda: row_time, localdate=timezone.localdate,
            )):
                record = import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                          raw_bytes=raw)
            # Synthetic finalized timestamps isolate PostgreSQL day attribution;
            # Actual PostgreSQL commit-time capture has its own integration test.
            StockImport.objects.filter(pk=record.pk).update(
                committed_at=row_time, actual_committed_at=actual_commit,
                commit_attribution="resolved",
            )
        self.assertEqual(DemandAuditEvent.objects.count(), 2)
        self.assertEqual(self.verify(date(2026, 11, 7)).verified_total_units, 1)
        self.assertEqual(self.verify(date(2026, 11, 8)).verified_total_units, 2)


class ActualCommitTimeTests(TransactionTestCase):
    def setUp(self):
        if not tracking_enabled():
            self.skipTest("Local PostgreSQL track_commit_timestamp is off; CI enables it.")
        business = Business.objects.create(name="Commit time business")
        self.manager = get_user_model().objects.create_user(email="commit-time@example.test", password="test-password")
        membership = BusinessMembership.objects.create(business=business, user=self.manager, role="manager")
        self.inventory = Inventory.objects.create(business=business, name="Commit shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.product = Product.objects.create(business=business, sku="C", name="Commit item",
                                              base_unit_label="each", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=self.inventory, product=self.product)

    def test_finalization_uses_postgresql_commit_time_and_recovers_after_callback_failure(self):
        from django.core.management import call_command

        with patch("receiving.csv_import.finalize_stock_import", return_value=False):
            record = import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                      raw_bytes=b"sku,change\nC,+1\n")
        record.refresh_from_db()
        self.assertEqual(record.commit_attribution, "pending")
        self.assertIsNotNone(record.origin_xid)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_xact_commit_timestamp(%s::xid8::xid)", [record.origin_xid])
            actual = cursor.fetchone()[0]
        self.assertIsNotNone(actual)
        call_command("finalize_commit_times")
        record.refresh_from_db()
        self.assertEqual(record.actual_committed_at, actual)
        self.assertEqual(record.commit_attribution, "resolved")
        with self.assertRaises(CsvImportRejected):
            import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                             raw_bytes=b"sku,change\nC,+1\n")

    def test_future_environment_activation_finalizes_actual_commit_time(self):
        from django.core.management import call_command

        first_day = timezone.localdate() + timedelta(days=2)
        call_command("activate_demand_observation", str(first_day))
        activation = ObservationActivation.objects.get(environment=settings.DJANGO_ENV)
        self.assertEqual(activation.state, "active")
        self.assertEqual(activation.first_observed_date, first_day)
        self.assertIsNotNone(activation.actual_committed_at)
        self.assertLess(activation.actual_committed_at.astimezone(SINGAPORE).date(), first_day)

    def test_csv_issue_uses_actual_commit_day_not_mocked_row_time(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        before = timezone.now() - timedelta(days=1)
        with patch("receiving.services.timezone", SimpleNamespace(now=lambda: before,
                                                                   localdate=timezone.localdate)):
            record = import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                      raw_bytes=b"sku,change\nC,-1\n")
        record.refresh_from_db()
        self.assertEqual(record.commit_attribution, "resolved")
        self.assertEqual(record.actual_committed_at.astimezone(SINGAPORE).date(), timezone.localdate())
        self.assertEqual(DemandAuditEvent.objects.get(stock_out__import_record=record).occurred_at.date(),
                         before.date())


class ConcurrentCoverageTests(TransactionTestCase):
    def setUp(self):
        business = Business.objects.create(name="Concurrent demand")
        self.manager = get_user_model().objects.create_user(email="concurrent-demand@example.test", password="test-password")
        membership = BusinessMembership.objects.create(business=business, user=self.manager, role="manager")
        self.inventory = Inventory.objects.create(business=business, name="Demand race shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.product = Product.objects.create(business=business, sku="R", name="Race item",
                                              base_unit_label="each", expiry_tracking_required=False)
        self.link = InventoryProduct.objects.create(inventory=self.inventory, product=self.product)
        self.day = timezone.localdate() - timedelta(days=1)
        ObservationActivation.objects.create(environment=settings.DJANGO_ENV,
                                             first_observed_date=self.day - timedelta(days=1),
                                             origin_xid="1", actual_committed_at=timezone.now(), state="active")

    def race(self, action):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    with patch("receiving.demand.tracking_enabled", return_value=True):
                        if action == "verify":
                            verify_demand_day(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                              product_id=self.product.pk, day=self.day)
                        else:
                            mark_demand_day_incomplete(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                                       product_id=self.product.pk, day=self.day, reason="gap")
                    return "ok"
                except ReceiptRejected:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_competing_verification_and_invalidation_append_once(self):
        self.assertCountEqual(self.race("verify"), ["ok", "rejected"])
        self.assertEqual(DemandCoverageDay.objects.count(), 1)
        self.assertEqual(list(DemandCoverageEvent.objects.values_list("action", flat=True)), ["verified"])
        self.assertCountEqual(self.race("incomplete"), ["ok", "rejected"])
        self.assertEqual(list(DemandCoverageEvent.objects.order_by("pk").values_list("action", flat=True)),
                         ["verified", "incomplete"])
