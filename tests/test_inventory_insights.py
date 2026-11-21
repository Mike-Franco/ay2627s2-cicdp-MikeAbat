from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import (
    Business,
    BusinessMembership,
    Inventory,
    InventoryAssignment,
)
from receiving.models import (
    DemandCoverageDay,
    DemandCoverageEvent,
    ObservationActivation,
)
from receiving.services import SINGAPORE, issue_stock, receive_manual


class InventoryInsightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Insights business")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Insights shelf")
        cls.other_inventory = Inventory.objects.create(business=cls.business, name="Private shelf")
        cls.other_business = Business.objects.create(name="Insights foreign business")
        cls.foreign_inventory = Inventory.objects.create(business=cls.other_business, name="Foreign shelf")
        cls.staff = get_user_model().objects.create_user(email="insights-staff@example.test")
        cls.manager = get_user_model().objects.create_user(email="insights-manager@example.test")
        cls.staff_membership = BusinessMembership.objects.create(user=cls.staff, business=cls.business, role="staff")
        cls.manager_membership = BusinessMembership.objects.create(user=cls.manager, business=cls.business, role="manager")
        InventoryAssignment.objects.create(membership=cls.staff_membership, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.manager_membership, inventory=cls.inventory)
        cls.product = cls.create_product("A-1", "Gauze", 2, 1)
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    @classmethod
    def create_product(cls, sku, name, lead_time_days=None, safety_stock_units=None):
        return Product.objects.create(
            business=cls.business, sku=sku, name=name, base_unit_label="each",
            expiry_tracking_required=False, lead_time_days=lead_time_days,
            safety_stock_units=safety_stock_units,
        )

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def setUp(self):
        self.login(self.staff)
        self.url = reverse("inventory-insights", args=[self.inventory.pk])

    def test_scopes_to_authorised_inventory_for_staff_and_manager(self):
        for user in (self.staff, self.manager):
            self.login(user)
            self.assertEqual(self.client.get(self.url).status_code, 200)
        for inventory in (self.other_inventory, self.foreign_inventory):
            self.assertEqual(self.client.get(reverse("inventory-insights", args=[inventory.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_demand_json_has_thirty_singapore_dates_and_includes_now_boundary(self):
        receive_manual(
            user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
            request_token=uuid4(), quantity_units=5, expiry_date=None,
        )
        issue_stock(
            user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk, quantity_units=2,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.context["demand_data_json"]
        today = timezone.now().astimezone(SINGAPORE).date()
        self.assertEqual(len(data), 30)
        self.assertEqual(data[0]["day"], (today - timedelta(days=29)).isoformat())
        self.assertEqual(data[-1]["day"], today.isoformat())
        self.assertEqual(data[-1]["issued"], 2)
        self.assertTrue(all(set(row) == {"day", "issued", "verified_average"} for row in data))
        self.assertContains(response, 'id="demand-data"')

    def test_stock_data_excludes_current_quarantine_and_serializes_all_eligible_skus(self):
        today = timezone.now().astimezone(SINGAPORE).date()
        first_week = today + timedelta(days=7 - today.weekday())
        receive_manual(
            user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
            request_token=uuid4(), quantity_units=8, expiry_date=first_week + timedelta(days=1),
        )
        product = self.create_product("A-2", "Gloves")
        InventoryProduct.objects.create(inventory=self.inventory, product=product)
        response = self.client.get(self.url)
        rows = response.context["reorder_data_json"]
        self.assertEqual([(row["sku"], row["available"], row["reorder_point"]) for row in rows],
                         [("A-1", 8, None), ("A-2", 0, None)])
        expiry = response.context["expiry_data_json"]
        self.assertEqual(len(expiry), 4)
        self.assertEqual([row["units"] for row in expiry], [8, 0, 0, 0])

    def test_reorder_point_reuses_verified_forecast(self):
        today = timezone.now().astimezone(SINGAPORE).date()
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=today - timedelta(days=8),
            origin_xid="1", actual_committed_at=timezone.now(), state="active",
        )
        for offset in range(7, 0, -1):
            coverage = DemandCoverageDay.objects.create(
                inventory_product=self.link, day=today - timedelta(days=offset),
            )
            DemandCoverageEvent.objects.create(
                coverage_day=coverage, actor=self.manager, action="verified",
                reason="", recorded_at=timezone.now(), verified_total_units=0,
            )
        with patch("receiving.demand.tracking_enabled", return_value=True):
            response = self.client.get(self.url)
        self.assertEqual(response.context["reorder_data_json"][0]["reorder_point"], "1")
        self.assertTrue(all(row["verified_average"] == "0.00"
                            for row in response.context["demand_data_json"]))

    def test_empty_inventory_has_clear_empty_states_and_json(self):
        empty = Inventory.objects.create(business=self.business, name="Empty shelf")
        InventoryAssignment.objects.create(membership=self.staff_membership, inventory=empty)
        response = self.client.get(reverse("inventory-insights", args=[empty.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No linked products or issue data")
        self.assertContains(response, "No products are linked")
        self.assertContains(response, "No eligible stock is recorded")
        self.assertEqual(response.context["demand_data_json"], [])

    def test_json_script_charts_and_query_count(self):
        response = self.client.get(self.url)
        self.assertContains(response, "demand-data")
        self.assertContains(response, "integrity=")
        self.assertContains(response, "crossorigin=")
        self.assertContains(response, "verified_average")
        self.assertNotContains(response, "cost")

        def query_count():
            with CaptureQueriesContext(connection) as captured:
                response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            return len(captured)

        initial = query_count()
        products = [
            self.create_product(f"SKU-{i}", f"Product {i}") for i in range(12)
        ]
        InventoryProduct.objects.bulk_create([
            InventoryProduct(inventory=self.inventory, product=product) for product in products
        ])
        self.assertEqual(query_count(), initial)
