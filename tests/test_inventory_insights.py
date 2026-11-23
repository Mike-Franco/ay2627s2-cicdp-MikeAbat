"""Inventory Insights (TORY-64): KPIs with help tips, forecast accuracy, charts, paged tables, range and CSV."""

from datetime import date, datetime, timedelta, timezone as utc_timezone
from decimal import Decimal
from fractions import Fraction
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

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.insights import parse_range, ranking_rows, traffic_series
from catalogue.metrics import DailyMovement, forecast_accuracy, mape, wape
from catalogue.models import Category, InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import DemandCoverageDay, DemandCoverageEvent, ObservationActivation
from receiving.services import SINGAPORE, issue_stock, receive_manual


class ForecastAccuracyMathsTests(SimpleTestCase):
    def test_mape_averages_percentage_gaps_and_skips_zero_demand(self):
        value, used = mape([(10, 8), (10, 10), (Fraction(5, 2), 5), (3, 0)])
        # |10-8|/8 = 25%, 0%, |2.5-5|/5 = 50%; the zero-demand day is skipped.
        self.assertEqual(used, 3)
        self.assertEqual(value, Decimal(25))

    def test_wape_weights_by_total_demand(self):
        value, used = wape([(10, 8), (10, 10), (3, 0)])
        self.assertEqual(used, 3)
        self.assertAlmostEqual(float(value), 27.78, places=2)  # (2 + 0 + 3) / (8 + 10 + 0)
        self.assertEqual(wape([(1, 0), (2, 0)]), (None, 2))
        self.assertEqual(wape([]), (None, 0))
        self.assertEqual(mape([]), (None, 0))

    def test_accuracy_uses_mape_then_wape_then_reports_not_enough_data(self):
        self.assertEqual(forecast_accuracy([(4, 4), (4, 2), (4, 8), (4, 0)]),
                         {"value": Decimal(50), "method": "MAPE", "points": 3})
        # Only two non-zero days: MAPE needs three, so the weighted error is used over all four days.
        result = forecast_accuracy([(4, 4), (4, 8), (4, 0), (4, 0)])
        self.assertEqual((result["method"], result["points"]), ("WAPE", 4))
        self.assertEqual(result["value"], Decimal(100))  # (0 + 4 + 4 + 4) / (4 + 8 + 0 + 0)
        self.assertEqual(forecast_accuracy([(4, 4), (4, 2)]), {"value": None, "method": None, "points": 2})
        self.assertEqual(forecast_accuracy([(1, 0), (1, 0), (1, 0)])["value"], None)
        self.assertEqual(forecast_accuracy([])["points"], 0)


class RangeAndTableHelperTests(SimpleTestCase):
    def test_range_parameter_is_validated(self):
        for value, expected in (("7d", "7d"), ("90", "90d"), ("30D", "30d"), ("", "30d"), (None, "30d"),
                                ("365d", "30d"), ("-7d", "30d"), ("all", "30d")):
            with self.subTest(value=value):
                self.assertEqual(parse_range(value), expected)

    def test_weeks_follow_singapore_mondays_and_cover_the_range(self):
        at = datetime(2026, 11, 22, 16, 30, tzinfo=utc_timezone.utc)  # Monday 23 Nov 00:30 in Singapore
        sunday, monday = date(2026, 11, 22), date(2026, 11, 23)
        movements = {1: {sunday: DailyMovement(received=3), monday: DailyMovement(issued=2)},
                     2: {monday: DailyMovement(received=11)}}
        rows = traffic_series([1], movements, at=at, days=30)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[-2:], [{"week": "2026-11-16", "received": 3, "issued": 0},
                                     {"week": "2026-11-23", "received": 0, "issued": 2}])
        self.assertEqual(len(traffic_series([1], movements, at=at, days=7)), 2)
        self.assertEqual(len(traffic_series([1], movements, at=at, days=90)), 13)
        self.assertEqual(traffic_series([], movements, at=at), [])

    def test_ranking_orders_by_days_left_and_flags_under_lead_time(self):
        positions = []
        for pk, supply in ((1, Decimal("2.5")), (2, Decimal(40)), (3, None), (4, Decimal("14.3"))):
            product = SimpleNamespace(pk=pk, sku=f"S-{pk}", name=f"Item {pk}", lead_time_days=3)
            link = SimpleNamespace(pk=pk, product=product)
            reorder = SimpleNamespace(forecast=SimpleNamespace(displayed_average="1.60"))
            positions.append(SimpleNamespace(link=link, supply=supply, available=4, reorder=reorder))
        inventory = SimpleNamespace(pk=9)
        rows = ranking_rows(inventory, positions)
        self.assertEqual([row["sku"] for row in rows], ["S-1", "S-4", "S-2"])
        self.assertEqual([row["rank"] for row in rows], [1, 2, 3])
        self.assertEqual([row["urgent"] for row in rows], [True, False, False])
        self.assertEqual([row["cover"] for row in rows], [5, 45, 100])
        self.assertEqual([row["sku"] for row in ranking_rows(inventory, positions, most_first=True)],
                         ["S-2", "S-4", "S-1"])


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
        cls.manager_membership = BusinessMembership.objects.create(user=cls.manager, business=cls.business,
                                                                   role="manager")
        InventoryAssignment.objects.create(membership=cls.staff_membership, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.manager_membership, inventory=cls.inventory)
        cls.product = cls.create_product("A-1", "Gauze", 2, 1)
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    @classmethod
    def create_product(cls, sku, name, lead_time_days=None, safety_stock_units=None):
        return Product.objects.create(
            business=cls.business, sku=sku, name=name, base_unit_label="each",
            expiry_tracking_required=False, lead_time_days=lead_time_days, safety_stock_units=safety_stock_units,
        )

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def setUp(self):
        self.login(self.staff)
        self.url = reverse("inventory-insights", args=[self.inventory.pk])
        self.today = timezone.now().astimezone(SINGAPORE).date()

    def receive(self, units, expiry=None, product=None):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                       product_id=(product or self.product).pk, request_token=uuid4(), quantity_units=units,
                       expiry_date=expiry)

    def verify(self, days, units=0):
        for day in days:
            coverage, _ = DemandCoverageDay.objects.get_or_create(inventory_product=self.link, day=day)
            DemandCoverageEvent.objects.create(coverage_day=coverage, actor=self.manager, action="verified",
                                               reason="", recorded_at=timezone.now(), verified_total_units=units)

    def activate(self, days_back=20):
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=self.today - timedelta(days=days_back),
            origin_xid="1", actual_committed_at=timezone.now(), state="active",
        )

    def test_scopes_to_authorised_inventory_for_staff_and_manager(self):
        for user in (self.staff, self.manager):
            self.login(user)
            self.assertEqual(self.client.get(self.url).status_code, 200)
            for inventory in (self.other_inventory, self.foreign_inventory):
                self.assertEqual(self.client.get(reverse("inventory-insights", args=[inventory.pk])).status_code,
                                 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_every_kpi_and_chart_has_a_help_tip_with_the_mockup_wording(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertEqual(html.count('class="help-btn"'), 10)  # 4 KPIs, 4 charts, 2 tables
        self.assertContains(response, 'aria-label="What is forecast accuracy?" aria-describedby="tip-accuracy"')
        self.assertContains(response, "Average % gap between last week&#x27;s 7-day forecast and verified demand.")
        self.assertContains(response, "Days with zero demand are skipped")
        self.assertContains(response, "Available quantity × selling price, summed over every active product in "
                                      "Insights shelf.")
        self.assertContains(response, "Issue these first (FEFO).")
        for label in ("Stock value", "Turnover", "Median days of supply", "Forecast accuracy"):
            self.assertContains(response, f'<div class="k">{label} <span class="help">')

    def test_range_control_sets_the_period_and_falls_back_to_30_days(self):
        self.receive(5)
        issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                    quantity_units=2)
        for value, days in (("7d", 7), ("90d", 90), ("bogus", 30), (None, 30)):
            with self.subTest(range=value):
                response = self.client.get(self.url, {"range": value} if value else {})
                self.assertEqual(response.status_code, 200)
                history = response.context["demand_data_json"]
                self.assertEqual(len(history), days)
                self.assertEqual(history[0]["day"], (self.today - timedelta(days=days - 1)).isoformat())
                self.assertEqual(history[-1]["issued"], 2)
                self.assertEqual(response.context["kpis"][1]["note"], f"{days}-day")
        response = self.client.get(self.url, {"range": "7d"})
        self.assertContains(response, 'class="on" aria-current="true">7d</a>')

    def test_stock_chart_marks_products_below_their_reorder_point(self):
        self.receive(8, expiry=self.today + timedelta(days=1))
        gloves = self.create_product("A-2", "Gloves")
        InventoryProduct.objects.create(inventory=self.inventory, product=gloves)
        rows = self.client.get(self.url).context["stock_data_json"]
        self.assertEqual([(row["sku"], row["available"], row["reorder_point"], row["below"]) for row in rows],
                         [("A-1", 8, None, False), ("A-2", 0, None, False)])

    def test_value_breakdown_toggles_between_category_and_status(self):
        category = Category.objects.create(business=self.business, name="First aid")
        Product.objects.filter(pk=self.product.pk).update(category=category)
        InventoryProduct.objects.filter(pk=self.link.pk).update(selling_price="3.25")
        self.receive(3)
        response = self.client.get(self.url)
        self.assertEqual(response.context["value_data_json"],
                         [{"label": "First aid", "value": "9.7500", "share": 100}])
        self.assertContains(response, "S$9.75")
        status = self.client.get(self.url, {"value_by": "status"}).context["value_data_json"]
        self.assertEqual(status[0]["label"], "Healthy")
        self.assertEqual(self.client.get(self.url, {"value_by": "nonsense"}).context["grouping"], "category")

    def test_demand_history_flags_unverified_days_and_forecasts_seven_days(self):
        self.activate()
        week = [self.today - timedelta(days=offset) for offset in range(7, 0, -1)]
        self.verify(week, units=0)
        with patch("receiving.demand.tracking_enabled", return_value=True):
            response = self.client.get(self.url, {"range": "30d"})
        history = response.context["demand_data_json"]
        verified = [row["day"] for row in history if row["verified"]]
        self.assertEqual(verified, [day.isoformat() for day in week])
        self.assertFalse(history[-1]["verified"])  # today is not complete yet
        forecast = response.context["forecast_data_json"]
        self.assertEqual([row["day"] for row in forecast],
                         [(self.today + timedelta(days=offset)).isoformat() for offset in range(1, 8)])
        self.assertTrue(all(row["forecast"] == "0.00" for row in forecast))

    def test_forecast_accuracy_compares_last_weeks_forecast_with_verified_days(self):
        self.activate(days_back=30)
        self.receive(100)
        earlier = [self.today - timedelta(days=offset) for offset in range(14, 7, -1)]
        recent = [self.today - timedelta(days=offset) for offset in range(7, 0, -1)]
        # Last week's forecast was 2/day (14 units over the seven days before it).
        with patch("receiving.services.timezone.now",
                   return_value=datetime.combine(earlier[0], datetime.min.time(), SINGAPORE) + timedelta(hours=10)):
            issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                        quantity_units=14)
        self.verify(earlier[:1], units=14)
        self.verify(earlier[1:], units=0)
        # Since then, 4 units on each of the first three recent days, then nothing.
        for day in recent[:3]:
            with patch("receiving.services.timezone.now",
                       return_value=datetime.combine(day, datetime.min.time(), SINGAPORE) + timedelta(hours=10)):
                issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                            quantity_units=4)
        self.verify(recent[:3], units=4)
        self.verify(recent[3:5], units=0)  # recent[5:] stay unverified and are not counted
        with patch("receiving.demand.tracking_enabled", return_value=True):
            response = self.client.get(self.url)
        accuracy = response.context["kpis"][3]
        self.assertEqual(accuracy["value"], "50%")  # |2 - 4| / 4 on three non-zero days
        self.assertEqual(accuracy["note"], "MAPE error, last 7 days")

    def test_forecast_accuracy_without_verified_data(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["kpis"][3]["value"], "—")
        self.assertContains(response, "Not enough verified data")

    def test_ranking_and_expiry_tables_page_with_their_defaults(self):
        InventoryProduct.objects.filter(pk=self.link.pk).update(selling_price="2.00")
        for days_ahead, units in ((1, 1), (7, 2), (8, 4), (28, 8), (29, 16)):
            self.receive(units, expiry=self.today + timedelta(days=days_ahead))
        response = self.client.get(self.url)
        rows = response.context["expiring_page"].object_list
        self.assertEqual([(row["week"], row["units"]) for row in rows],
                         [("This week", 1), ("This week", 2), ("Next week", 4), ("In 4 weeks", 8)])
        self.assertEqual(rows[0]["value"], Decimal("2.00"))
        self.assertEqual(response.context["expiring_page"].per_page, 10)
        self.assertEqual(response.context["ranking_page"].per_page, 5)
        self.assertEqual(self.client.get(self.url, {"supply_per_page": "30"}).context["ranking_page"].per_page, 25)
        self.assertEqual(self.client.get(self.url, {"expiry_per_page": "3"}).context["expiring_page"].per_page, 10)
        page = self.client.get(self.url, {"expiry_per_page": "10", "expiry_page": "9"}).context["expiring_page"]
        self.assertEqual(page.number, 1)

    def test_export_csv_has_both_tables(self):
        InventoryProduct.objects.filter(pk=self.link.pk).update(selling_price="1.50")
        self.receive(4, expiry=self.today + timedelta(days=3))
        response = self.client.get(self.url, {"export": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(f'filename="tory-insights-{self.inventory.pk}-', response["Content-Disposition"])
        body = b"".join(response.streaming_content).decode()
        self.assertIn("Table,SKU,Product,Units", body)
        self.assertIn("Expiring stock by week,A-1,Gauze,4,,,This week", body)
        self.assertIn(",6.00", body)
        self.assertContains(self.client.get(self.url), 'href="?export=csv"')

    def test_empty_inventory_has_clear_empty_states(self):
        empty = Inventory.objects.create(business=self.business, name="Empty shelf")
        InventoryAssignment.objects.create(membership=self.staff_membership, inventory=empty)
        response = self.client.get(reverse("inventory-insights", args=[empty.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No active products are linked")
        self.assertContains(response, "No eligible stock expires")
        self.assertContains(response, "No active products have a verified, non-zero demand rate")
        self.assertEqual(response.context["demand_data_json"], [])

    def test_charts_load_from_json_and_query_count_does_not_grow_with_products(self):
        response = self.client.get(self.url)
        for key in ("stock", "traffic", "value", "demand", "forecast"):
            self.assertContains(response, f'id="{key}-data"')
        self.assertContains(response, 'src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js" '
                                      'integrity="sha384-')
        self.assertContains(response, '<details class="chart-data"><summary>Show data</summary>', count=4)

        def query_count():
            with CaptureQueriesContext(connection) as captured:
                self.assertEqual(self.client.get(self.url).status_code, 200)
            return len(captured)

        initial = query_count()
        products = [self.create_product(f"SKU-{i}", f"Product {i}") for i in range(12)]
        InventoryProduct.objects.bulk_create([InventoryProduct(inventory=self.inventory, product=product)
                                              for product in products])
        self.assertEqual(query_count(), initial)
