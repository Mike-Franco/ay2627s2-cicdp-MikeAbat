from datetime import date, datetime, timedelta, timezone as utc_timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from catalogue.templatetags.tory_format import sgdate
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.insights import supply_series, traffic_series
from catalogue.metrics import DailyMovement
from catalogue.models import Category, InventoryProduct, Product
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


class WeeklyMovementTests(SimpleTestCase):
    def test_sunday_and_monday_use_different_singapore_weeks(self):
        at = datetime(2026, 11, 22, 16, 30, tzinfo=utc_timezone.utc)
        sunday, monday = date(2026, 11, 22), date(2026, 11, 23)
        movements = {
            1: {sunday: DailyMovement(received=3), monday: DailyMovement(issued=2)},
            2: {monday: DailyMovement(received=11)},
        }
        rows = traffic_series([1], movements, at=at)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[-2:], [
            {"week": "2026-11-16", "received": 3, "issued": 0},
            {"week": "2026-11-23", "received": 0, "issued": 2},
        ])
        self.assertEqual(traffic_series([], movements, at=at), [])


    def test_supply_ranking_limits_to_ten_and_orders_ties_by_link_id(self):
        positions = []
        for pk in range(13, 0, -1):
            product = SimpleNamespace(sku=f"SKU-{pk}", name=f"Item {pk}")
            link = SimpleNamespace(pk=pk, product=product)
            positions.append(SimpleNamespace(link=link, supply=None if pk == 13 else Decimal(pk // 2)))
        ranked = supply_series(positions)
        self.assertEqual([row["sku"] for row in ranked], [f"SKU-{pk}" for pk in range(1, 11)])
        self.assertEqual(ranked[0], {"sku": "SKU-1", "name": "Item 1", "days": 0.0})


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
        receive_manual(
            user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
            request_token=uuid4(), quantity_units=8, expiry_date=today + timedelta(days=1),
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

    def test_expiry_windows_start_tomorrow_and_cover_twenty_eight_days(self):
        today = timezone.now().astimezone(SINGAPORE).date()
        for days_ahead, units in ((1, 1), (7, 2), (8, 4), (28, 8), (29, 16)):
            receive_manual(
                user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                request_token=uuid4(), quantity_units=units, expiry_date=today + timedelta(days=days_ahead),
            )
        expiry = self.client.get(self.url).context["expiry_data_json"]
        self.assertEqual([row["units"] for row in expiry], [3, 4, 0, 8])
        first = today + timedelta(days=1)
        self.assertEqual(expiry[0]["week"], f"{sgdate(first)} – {sgdate(first + timedelta(days=6))}")

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
        self.assertEqual(response.context["reorder_data_json"][0]["reorder_point"], 1)
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
        self.assertContains(response, 'src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js" integrity="sha384-')
        self.assertContains(response, "tory/insights.js")
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

    def test_data_tables_are_collapsed_under_show_data(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<details class="chart-data"><summary>Show data</summary>', count=6)
        self.assertNotContains(response, "<details open")
        timestamp = response.context["as_of"].isoformat(timespec="seconds")
        self.assertContains(response, f'datetime="{timestamp}"', count=6)
        for label in ("What this shows", "How to read it", "What to do", "Data as of"):
            self.assertContains(response, label, count=6)

    def test_new_chart_shapes_product_category_and_value_controls(self):
        category = Category.objects.create(business=self.business, name="First aid")
        Product.objects.filter(pk=self.product.pk).update(category=category)
        InventoryProduct.objects.filter(pk=self.link.pk).update(selling_price="3.25")
        receive_manual(
            user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
            request_token=uuid4(), quantity_units=5, expiry_date=None,
        )
        issue_stock(
            user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk, quantity_units=2,
        )
        uncategorised = self.create_product("PLAIN", "Uncategorised product")
        InventoryProduct.objects.create(inventory=self.inventory, product=uncategorised)
        receive_manual(
            user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=uncategorised.pk,
            request_token=uuid4(), quantity_units=7, expiry_date=None,
        )
        response = self.client.get(self.url, {"product": self.product.pk, "category": category.pk, "value_by": "category"})
        self.assertEqual(response.status_code, 200)
        stock = response.context["stock_data_json"]
        self.assertEqual(len(stock), 30)
        self.assertEqual(set(stock[0]), {"day", "on_hand", "reorder_point", "safety_stock"})
        self.assertEqual(stock[-1]["on_hand"], 0)
        self.assertEqual(stock[-1]["safety_stock"], 1)
        self.assertIsNone(stock[-1]["reorder_point"])
        self.assertEqual(stock[-1]["day"], (timezone.now().astimezone(SINGAPORE).date() - timedelta(days=1)).isoformat())
        traffic = response.context["traffic_data_json"]
        self.assertEqual(len(traffic), 8)
        self.assertEqual((traffic[-1]["received"], traffic[-1]["issued"]), (5, 2))
        unfiltered = self.client.get(self.url).context
        self.assertEqual(unfiltered["traffic_data_json"][-1]["received"], 12)
        self.assertEqual(sum(Decimal(row["value"]) for row in unfiltered["value_data_json"]), Decimal("9.75"))
        self.assertEqual(response.context["supply_data_json"], [])
        values = response.context["value_data_json"]
        self.assertEqual(values[0]["label"], "First aid")
        self.assertEqual(float(values[0]["value"]), 9.75)
        for key in ("stock", "traffic", "supply", "value"):
            self.assertContains(response, f'id="{key}-data"')
        other = self.create_product("HIDDEN", "Unassigned item")
        InventoryProduct.objects.create(inventory=self.other_inventory, product=other)
        other_category = Category.objects.create(business=self.other_business, name="Outside")
        self.assertEqual(self.client.get(self.url, {"product": other.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {"category": other_category.pk}).status_code, 404)
