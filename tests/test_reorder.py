from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from fractions import Fraction
from threading import Event
from time import sleep
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.forms import ReorderSettingsForm
from catalogue.models import InventoryProduct, Product
from catalogue.reorder import recommendation, save_shared_settings
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import DemandCoverageDay, DemandCoverageEvent, ObservationActivation
from receiving.services import ReceiptRejected, issue_stock, receive_manual


SINGAPORE = ZoneInfo("Asia/Singapore")


class ReorderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Reorder business")
        cls.other_business = Business.objects.create(name="Outside business")
        cls.manager = get_user_model().objects.create_user(email="reorder-manager@example.test", password="pass")
        cls.partial_manager = get_user_model().objects.create_user(email="reorder-partial@example.test", password="pass")
        cls.staff = get_user_model().objects.create_user(email="reorder-staff@example.test", password="pass")
        cls.unassigned = get_user_model().objects.create_user(email="reorder-unassigned@example.test", password="pass")
        cls.outsider = get_user_model().objects.create_user(email="reorder-outsider@example.test", password="pass")
        cls.first = Inventory.objects.create(business=cls.business, name="First")
        cls.second = Inventory.objects.create(business=cls.business, name="Second")
        outside = Inventory.objects.create(business=cls.other_business, name="Outside")
        for user, role, inventories, business in (
            (cls.manager, "manager", (cls.first, cls.second), cls.business),
            (cls.partial_manager, "manager", (cls.first,), cls.business),
            (cls.staff, "staff", (cls.first,), cls.business),
            (cls.unassigned, "manager", (), cls.business),
            (cls.outsider, "manager", (outside,), cls.other_business),
        ):
            membership = BusinessMembership.objects.create(business=business, user=user, role=role)
            for inventory in inventories:
                InventoryAssignment.objects.create(membership=membership, inventory=inventory)
        cls.product = Product.objects.create(business=cls.business, sku="R", name="Reorder item",
                                             base_unit_label="each", expiry_tracking_required=False)
        cls.link = InventoryProduct.objects.create(inventory=cls.first, product=cls.product)
        InventoryProduct.objects.create(inventory=cls.second, product=cls.product)

    def setUp(self):
        self.today = timezone.now().astimezone(SINGAPORE).date()
        ObservationActivation.objects.create(environment=settings.DJANGO_ENV,
                                             first_observed_date=self.today - timedelta(days=9),
                                             origin_xid="1", actual_committed_at=timezone.now(), state="active")

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def cover(self, *, start_offset=7, end_offset=1, first_units=0):
        for offset in range(start_offset, end_offset - 1, -1):
            day = self.today - timedelta(days=offset)
            coverage = DemandCoverageDay.objects.create(inventory_product=self.link, day=day)
            DemandCoverageEvent.objects.create(coverage_day=coverage, actor=self.manager,
                                               action="verified", reason="", recorded_at=timezone.now(),
                                               verified_total_units=first_units if offset == start_offset else 0)

    def test_shared_settings_permissions_and_clear_to_unset(self):
        url = reverse("reorder-settings", args=[self.first.pk, self.product.pk])
        for user in (self.partial_manager, self.staff, self.unassigned, self.outsider):
            self.login(user)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {"lead_time_days": "7", "safety_stock_units": "0"}).status_code, 404)
        with self.assertRaises(ReceiptRejected):
            save_shared_settings(user_id=self.partial_manager.pk, inventory_id=self.first.pk,
                                 product_id=self.product.pk, lead_time_days=7, safety_stock_units=0)
        self.second.is_active = False
        self.second.save(update_fields=["is_active"])
        self.login(self.partial_manager)
        self.assertEqual(self.client.post(url, {"lead_time_days": "1", "safety_stock_units": "0"}).status_code, 302)
        self.second.is_active = True
        self.second.save(update_fields=["is_active"])
        self.assertEqual(self.client.post(url, {"lead_time_days": "7", "safety_stock_units": "0"}).status_code, 404)
        self.login(self.manager)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"lead_time_days": "365", "safety_stock_units": "0"}).status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual((self.product.lead_time_days, self.product.safety_stock_units), (365, 0))
        self.assertEqual(self.client.post(url, {"lead_time_days": "", "safety_stock_units": ""}).status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual((self.product.lead_time_days, self.product.safety_stock_units), (None, None))

    def test_setting_bounds_and_database_guard(self):
        for lead, safety in (("1", "0"), ("365", "2147483647"), ("", "")):
            self.assertTrue(ReorderSettingsForm({"lead_time_days": lead,
                                                 "safety_stock_units": safety}, instance=self.product).is_valid())
        for lead, safety in (("0", "0"), ("366", "0"), ("1.5", "0"),
                             ("1", "-1"), ("1", "2147483648"), ("1", "1.5")):
            self.assertFalse(ReorderSettingsForm({"lead_time_days": lead,
                                                  "safety_stock_units": safety}, instance=self.product).is_valid())
        with self.assertRaises(ReceiptRejected):
            save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                                 product_id=self.product.pk, lead_time_days=366, safety_stock_units=0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE catalogue_product SET lead_time_days=366 WHERE id=%s", [self.product.pk])

    def test_unavailable_inputs_and_staff_read(self):
        result = recommendation(user_id=self.staff.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        self.assertFalse(result.forecast.available)
        self.assertEqual(result.missing_settings, ("lead time", "safety stock"))
        self.assertIsNone(result.reorder_point)
        self.login(self.staff)
        url = reverse("demand-forecast", args=[self.first.pk, self.product.pk])
        self.assertContains(self.client.get(url), "set lead time, safety stock")
        self.assertNotContains(self.client.get(url), "Edit reorder settings")
        save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                             product_id=self.product.pk, lead_time_days=7, safety_stock_units=0)
        result = recommendation(user_id=self.staff.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        self.assertIsNone(result.reorder_point)
        self.assertEqual(result.missing_settings, ())
        self.cover()
        save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                             product_id=self.product.pk, lead_time_days=7, safety_stock_units=None)
        result = recommendation(user_id=self.staff.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        self.assertTrue(result.forecast.available)
        self.assertEqual(result.missing_settings, ("safety stock",))
        self.assertIsNone(result.suggested_units)
        save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                             product_id=self.product.pk, lead_time_days=None, safety_stock_units=0)
        result = recommendation(user_id=self.staff.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        self.assertEqual(result.missing_settings, ("lead time",))
        self.assertIsNone(result.reorder_point)

    def test_inventory_products_shows_existing_reorder_state_and_zero_balances(self):
        url = reverse("inventory-products", args=[self.first.pk])
        self.login(self.staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Physical")
        self.assertContains(response, "Quarantined")
        self.assertContains(response, "Available")
        self.assertContains(response, "Reorder point unavailable")
        self.assertContains(response, "Every date needs explicit Manager verification.")
        self.assertContains(response, "Set lead time, safety stock.")
        self.assertContains(response, '<td class="numeric available">0<span class="unit">each</span></td>', html=True)
        self.assertContains(response, reverse("product-stock", args=[self.first.pk, self.product.pk]))
        self.assertNotContains(response, "Import stock CSV")
        self.assertNotContains(response, "Adjust count")

        self.cover()
        save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                             product_id=self.product.pk, lead_time_days=1, safety_stock_units=0)
        response = self.client.get(url)
        self.assertContains(response, "At or below reorder point")
        self.assertEqual(response.context["product_links"][0].display_available_units, 0)
        receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        response = self.client.get(url)
        self.assertContains(response, "Above reorder point")
        self.assertEqual(response.context["product_links"][0].display_available_units, 1)
        self.assertContains(response, '<td class="numeric available">1<span class="unit">each</span></td>', html=True)
        self.login(self.manager)
        self.assertContains(self.client.get(url), "Import CSV")

    def test_inventory_products_shows_expired_stock_as_physical_and_quarantined(self):
        expiry = self.today + timedelta(days=1)
        receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=5, expiry_date=expiry)
        self.login(self.staff)
        at_expiry = datetime.combine(expiry, time.min, SINGAPORE)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = at_expiry.timestamp()
        session.set_expiry(at_expiry + timedelta(hours=1))
        session.save()
        with patch("catalogue.views.timezone.now", return_value=at_expiry), patch(
            "accounts.sessions.timezone.now", return_value=at_expiry
        ):
            response = self.client.get(reverse("inventory-products", args=[self.first.pk]))
        self.assertEqual(response.status_code, 200, response.get('Location'))
        link = response.context["product_links"][0]
        self.assertEqual((link.display_physical_units, link.display_quarantine_units,
                          link.display_available_units), (5, 5, 0))
        self.assertContains(response, "Reorder point unavailable")

    def test_exact_fraction_and_threshold_equality(self):
        save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                             product_id=self.product.pk, lead_time_days=7, safety_stock_units=0)
        receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=3, expiry_date=None)
        action_at = datetime.combine(self.today - timedelta(days=7), time(12), SINGAPORE)
        with patch("receiving.services.timezone", SimpleNamespace(now=lambda: action_at,
                                                                   localdate=timezone.localdate)):
            issue_stock(user_id=self.staff.pk, inventory_id=self.first.pk,
                        product_id=self.product.pk, quantity_units=3)
        self.cover(first_units=3)
        result = recommendation(user_id=self.staff.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        self.assertEqual(result.forecast.average, Fraction(3, 7))
        self.assertEqual(result.forecast.displayed_average, "0.43")
        self.assertEqual(result.reorder_point, 3)
        self.assertTrue(result.alert)
        self.assertEqual(result.suggested_units, 3)
        save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                             product_id=self.product.pk, lead_time_days=7, safety_stock_units=8)
        receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=11, expiry_date=None)
        result = recommendation(user_id=self.manager.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        self.assertEqual((result.reorder_point, result.available_units), (11, 11))
        self.assertTrue(result.alert)
        self.assertEqual(result.suggested_units, 0)
        receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=1, expiry_date=None)
        result = recommendation(user_id=self.manager.pk, inventory_id=self.first.pk, product_id=self.product.pk)
        self.assertFalse(result.alert)
        self.assertEqual(result.suggested_units, 0)
        self.login(self.staff)
        response = self.client.get(reverse("demand-forecast", args=[self.first.pk, self.product.pk]))
        self.assertContains(response, "No reorder alert")
        self.assertNotContains(response, "Edit reorder settings")

    def test_expiry_boundary_excludes_pending_quarantine(self):
        save_shared_settings(user_id=self.manager.pk, inventory_id=self.first.pk,
                             product_id=self.product.pk, lead_time_days=1, safety_stock_units=0)
        expiry = self.today + timedelta(days=1)
        receive_manual(user_id=self.manager.pk, inventory_id=self.first.pk,
                       product_id=self.product.pk, request_token=uuid.uuid4(),
                       quantity_units=5, expiry_date=expiry)
        self.cover(start_offset=7, end_offset=0)
        before = datetime.combine(expiry, time.min, SINGAPORE) - timedelta(microseconds=1)
        after = datetime.combine(expiry, time.min, SINGAPORE)
        prior = recommendation(user_id=self.manager.pk, inventory_id=self.first.pk,
                               product_id=self.product.pk, at=before)
        current = recommendation(user_id=self.manager.pk, inventory_id=self.first.pk,
                                 product_id=self.product.pk, at=after)
        self.assertEqual((prior.available_units, prior.quarantined_units), (5, 0))
        self.assertEqual((current.available_units, current.quarantined_units), (0, 5))
        self.assertEqual((current.reorder_point, current.suggested_units), (0, 0))


class ReorderConcurrencyTests(TransactionTestCase):
    def test_recommendation_waits_for_receipt_and_reads_committed_balance(self):
        business = Business.objects.create(name="Reorder race")
        manager = get_user_model().objects.create_user(email="reorder-race@example.test", password="pass")
        membership = BusinessMembership.objects.create(business=business, user=manager, role="manager")
        inventory = Inventory.objects.create(business=business, name="Race shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=inventory)
        product = Product.objects.create(business=business, sku="RACE", name="Race item",
                                         base_unit_label="each", expiry_tracking_required=False,
                                         lead_time_days=1, safety_stock_units=0)
        link = InventoryProduct.objects.create(inventory=inventory, product=product)
        today = timezone.localdate()
        ObservationActivation.objects.create(environment=settings.DJANGO_ENV,
                                             first_observed_date=today - timedelta(days=8),
                                             origin_xid="1", actual_committed_at=timezone.now(), state="active")
        for offset in range(7, 0, -1):
            coverage = DemandCoverageDay.objects.create(inventory_product=link,
                                                        day=today - timedelta(days=offset))
            DemandCoverageEvent.objects.create(coverage_day=coverage, actor=manager,
                                               action="verified", reason="", recorded_at=timezone.now(),
                                               verified_total_units=0)
        receipt_ready = Event()
        release_receipt = Event()
        reader_started = Event()

        def writer():
            close_old_connections()
            try:
                with transaction.atomic():
                    receive_manual(user_id=manager.pk, inventory_id=inventory.pk,
                                   product_id=product.pk, request_token=uuid.uuid4(),
                                   quantity_units=5, expiry_date=None)
                    receipt_ready.set()
                    if not release_receipt.wait(10):
                        raise TimeoutError("Reader did not start")
            finally:
                close_old_connections()

        from catalogue.reorder import _lock_authorized_scope as real_lock

        def reader_lock(*args, **kwargs):
            reader_started.set()
            return real_lock(*args, **kwargs)

        def reader():
            close_old_connections()
            try:
                return recommendation(user_id=manager.pk, inventory_id=inventory.pk, product_id=product.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer_future = pool.submit(writer)
            self.assertTrue(receipt_ready.wait(10))
            with patch("catalogue.reorder._lock_authorized_scope", side_effect=reader_lock):
                reader_future = pool.submit(reader)
                self.assertTrue(reader_started.wait(10))
                sleep(0.2)
                self.assertFalse(reader_future.done())
                release_receipt.set()
                writer_future.result(timeout=20)
                result = reader_future.result(timeout=20)
        self.assertTrue(result.forecast.available)
        self.assertEqual(result.available_units, 5)
        self.assertEqual(result.suggested_units, 0)
