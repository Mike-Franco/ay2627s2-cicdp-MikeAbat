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

from accounts.dashboard import inventory_dashboard
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import DemandCoverageDay, DemandCoverageEvent, ObservationActivation
from receiving.services import SINGAPORE, issue_stock, receive_manual


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        business = Business.objects.create(name="Dashboard business")
        foreign = Business.objects.create(name="Outside business")
        cls.staff = get_user_model().objects.create_user(email="dashboard-staff@example.test")
        cls.manager = get_user_model().objects.create_user(email="dashboard-manager@example.test")
        cls.outsider = get_user_model().objects.create_user(email="dashboard-foreign@example.test")
        cls.inventory = Inventory.objects.create(business=business, name="Assigned shelf")
        hidden = Inventory.objects.create(business=business, name="Unassigned shelf")
        outside = Inventory.objects.create(business=foreign, name="Foreign shelf")
        for user, role, shelves in (
            (cls.staff, "staff", (cls.inventory,)),
            (cls.manager, "manager", (cls.inventory, hidden)),
            (cls.outsider, "manager", (outside,)),
        ):
            member = BusinessMembership.objects.create(user=user, role=role, business=shelves[0].business)
            for shelf in shelves:
                InventoryAssignment.objects.create(membership=member, inventory=shelf)
        cls.link = cls.create_link(cls.inventory, "D1", "Assigned item")
        cls.hidden_link = cls.create_link(hidden, "D2", "Unassigned item")
        cls.outside_link = cls.create_link(outside, "D3", "Foreign item")

    @staticmethod
    def create_link(shelf, sku, name):
        product = Product.objects.create(
            business=shelf.business, sku=sku, name=name, base_unit_label="each",
            expiry_tracking_required=False, lead_time_days=1, safety_stock_units=0,
        )
        return InventoryProduct.objects.create(inventory=shelf, product=product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def receive(self, actor, link, expires=None):
        return receive_manual(
            user_id=actor.pk, inventory_id=link.inventory_id, product_id=link.product_id,
            request_token=uuid4(), quantity_units=1, expiry_date=expires,
        )[0]

    def test_staff_and_manager_only_see_assigned_data(self):
        for actor, link in ((self.manager, self.link), (self.manager, self.hidden_link),
                            (self.outsider, self.outside_link)):
            self.receive(actor, link)
        for actor, expected, hidden in (
            (self.staff, "Assigned item", ("Unassigned item", "Foreign item")),
            (self.manager, "Unassigned item", ("Foreign item",)),
            (self.outsider, "Foreign item", ("Assigned item", "Unassigned item")),
        ):
            self.login(actor)
            response = self.client.get(reverse("home"))
            self.assertContains(response, expected)
            for name in hidden:
                self.assertNotContains(response, name)

    def test_expiry_boundaries_quarantine_and_latest_ten(self):
        now = timezone.now() + timedelta(days=1)
        today = now.astimezone(SINGAPORE).date()
        batches = [self.receive(self.manager, self.link, today + timedelta(days=day))
                   for day in (0, 1, 7, 8, 30, 31)]
        for _ in range(6):
            self.receive(self.manager, self.link)
        with patch("accounts.views.timezone.now", return_value=now):
            self.login(self.staff)
            response = self.client.get(reverse("home"))
        self.assertEqual([batch.pk for batch in response.context["expiring_week"]], [b.pk for b in batches[1:3]])
        self.assertEqual([batch.pk for batch in response.context["expiring_later"]], [b.pk for b in batches[3:5]])
        self.assertEqual(response.context["inventory_totals"], [(self.inventory, 1)])
        activity = response.context["recent_activity"]
        self.assertEqual(len(activity), 10)
        self.assertEqual([event["id"] for event in activity], sorted((event["id"] for event in activity), reverse=True))

    @patch("receiving.demand.tracking_enabled", return_value=True)
    def test_verified_threshold_and_query_count(self, tracking_enabled):
        now = timezone.now()
        today = now.astimezone(SINGAPORE).date()
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=today - timedelta(days=9),
            origin_xid="1", actual_committed_at=now, state="active",
        )

        def cover(link):
            for offset in range(7, 0, -1):
                day = DemandCoverageDay.objects.create(inventory_product=link, day=today - timedelta(days=offset))
                DemandCoverageEvent.objects.create(
                    coverage_day=day, actor=self.manager, action="verified", reason="",
                    recorded_at=now, verified_total_units=0,
                )

        cover(self.link)
        with CaptureQueriesContext(connection) as first:
            result = inventory_dashboard(self.staff, at=now)
        self.assertEqual([(link.pk, row.reorder_point) for link, row in result["low_stock"]], [(self.link.pk, 0)])
        other = self.create_link(self.inventory, "D4", "Sufficient stock")
        cover(other)
        self.receive(self.manager, other)
        self.create_link(self.inventory, "D5", "Unverified stock")
        with CaptureQueriesContext(connection) as later:
            result = inventory_dashboard(self.staff, at=now)
        self.assertEqual(len(first), len(later))
        self.assertEqual([link.pk for link, _ in result["low_stock"]], [self.link.pk])
        self.assertEqual(result["reorder_unavailable"], 1)
        self.receive(self.manager, self.link)
        issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk,
                    product_id=self.link.product_id, quantity_units=1)
        self.assertEqual(inventory_dashboard(self.staff, at=now)["recent_activity"][0]["movement"], "Issued")

    def test_empty_dashboard_and_login_required(self):
        url = reverse("home")
        self.assertEqual(self.client.get(url).status_code, 302)
        user = get_user_model().objects.create_user(email="unassigned-dashboard@example.test")
        self.login(user)
        self.assertContains(self.client.get(url), "No active inventories are assigned to you.")

    def test_dashboard_filter_urgency_and_query_budget(self):
        url = reverse("home")
        self.receive(self.manager, self.hidden_link)
        self.login(self.staff)
        self.assertEqual(self.client.get(url, {"inventory": self.hidden_link.inventory_id}).status_code, 404)
        self.assertEqual(self.client.get(url, {"inventory": self.outside_link.inventory_id}).status_code, 404)
        self.login(self.manager)
        params = {"inventory": self.inventory.pk, "panel": "actions"}
        with CaptureQueriesContext(connection) as first:
            response = self.client.get(url, params)
        self.assertContains(response, "Out of stock")
        self.assertNotContains(response, "Unassigned item")
        self.assertContains(response, "Turnover (30d)")
        for index in range(26):
            self.create_link(self.inventory, f"MORE-{index}", f"Additional item {index}")
        with CaptureQueriesContext(connection) as later:
            response = self.client.get(url, {**params, "page": 2})
        self.assertEqual(len(first), len(later))
        self.assertEqual(response.context["actions"]["page"].number, 2)
        self.assertContains(response, f"inventory={self.inventory.pk}&amp;panel=actions&amp;page=1")
        self.assertTrue(all(row["label"] == "Out of stock" for row in response.context["actions"]["rows"]))

    def test_unverified_kpi_and_role_action_when_review_window_is_partial(self):
        now = timezone.now()
        yesterday = now.astimezone(SINGAPORE).date() - timedelta(days=1)
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=yesterday,
            origin_xid="1", actual_committed_at=now, state="active",
        )
        extra = self.create_link(self.inventory, "EXTRA", "Extra item")
        for viewer in (self.staff, self.manager):
            self.login(viewer)
            response = self.client.get(reverse("home"), {"inventory": self.inventory.pk})
            kpi = next(card for card in response.context["kpi_cards"] if card["label"] == "Unverified demand days")
            self.assertEqual(kpi["value"], 2)
            self.assertEqual("scope=week" in response.content.decode(), viewer == self.manager)
        day = DemandCoverageDay.objects.create(inventory_product=extra, day=yesterday)
        DemandCoverageEvent.objects.create(
            coverage_day=day, actor=self.manager, action="verified", reason="",
            recorded_at=now, verified_total_units=0,
        )
        response = self.client.get(reverse("home"), {"inventory": self.inventory.pk})
        kpi = next(card for card in response.context["kpi_cards"] if card["label"] == "Unverified demand days")
        self.assertEqual(kpi["value"], 1)
