from datetime import datetime, time, timedelta
from unittest.mock import patch
import uuid
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import DemandCoverageDay, DemandCoverageEvent, ObservationActivation, ReceiptAuditEvent
from receiving.services import receive_manual


class InventoryProductFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Product filter business")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Filter shelf")
        cls.private_inventory = Inventory.objects.create(business=cls.business, name="Private shelf")
        cls.empty_inventory = Inventory.objects.create(business=cls.business, name="Empty shelf")
        other_business = Business.objects.create(name="Other filter business")
        cls.other_inventory = Inventory.objects.create(business=other_business, name="Other shelf")
        for name, role in (("manager", "manager"), ("staff", "staff"), ("unassigned", "staff")):
            user = get_user_model().objects.create_user(
                email=f"filter-{name}@example.test", password="test-only-password"
            )
            setattr(cls, name, user)
            membership = BusinessMembership.objects.create(business=cls.business, user=user, role=role)
            if name != "unassigned":
                for inventory in (cls.inventory, cls.empty_inventory):
                    InventoryAssignment.objects.create(membership=membership, inventory=inventory)

        cls.attention = Product.objects.create(
            business=cls.business, sku="A-001", name="Green Tea", base_unit_label="each",
            expiry_tracking_required=False, lead_time_days=1, safety_stock_units=0,
        )
        cls.above = Product.objects.create(
            business=cls.business, sku="B-002", name="Black Tea", base_unit_label="each",
            expiry_tracking_required=False, lead_time_days=1, safety_stock_units=0,
        )
        cls.no_coverage = Product.objects.create(
            business=cls.business, sku="C-003", name="Coffee", base_unit_label="each",
            expiry_tracking_required=False, lead_time_days=1, safety_stock_units=0,
        )
        cls.no_settings = Product.objects.create(business=cls.business, sku="D-004", name="Milk")
        cls.inactive = Product.objects.create(
            business=cls.business, sku="E-005", name="Retired Tea", is_active=False,
        )
        cls.literal = Product.objects.create(business=cls.business, sku="F_%literal", name="100% Tea")
        cls.products = (cls.attention, cls.above, cls.no_coverage, cls.no_settings, cls.inactive, cls.literal)
        links = {product.pk: InventoryProduct.objects.create(inventory=cls.inventory, product=product)
                 for product in cls.products}
        today = timezone.now().astimezone(ZoneInfo("Asia/Singapore")).date()
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=today - timedelta(days=9),
            origin_xid="1", actual_committed_at=timezone.now(), state="active",
        )
        for product in (cls.attention, cls.above, cls.no_settings):
            for offset in range(7, 0, -1):
                coverage = DemandCoverageDay.objects.create(
                    inventory_product=links[product.pk], day=today - timedelta(days=offset),
                )
                DemandCoverageEvent.objects.create(
                    coverage_day=coverage, actor=cls.manager, action="verified", reason="",
                    recorded_at=timezone.now(), verified_total_units=0,
                )
        receive_manual(
            user_id=cls.manager.pk, inventory_id=cls.inventory.pk, product_id=cls.above.pk,
            request_token=uuid.uuid4(), quantity_units=2, expiry_date=None,
        )
        for inventory, business, sku, name in (
            (cls.private_inventory, cls.business, "PRIVATE", "Private tea"),
            (cls.other_inventory, other_business, "A-001", "Other business tea"),
        ):
            product = Product.objects.create(business=business, sku=sku, name=name)
            InventoryProduct.objects.create(inventory=inventory, product=product)

    def setUp(self):
        self.url = reverse("inventory-products", args=[self.inventory.pk])
        self.login(self.staff)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def product_ids(self, response):
        return [link.product_id for link in response.context["product_links"]]

    def test_default_list_keeps_order_and_exposes_accessible_get_filters(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product_ids(response), [product.pk for product in self.products])
        self.assertEqual(response.context["total_product_count"], 6)
        self.assertContains(response, 'method="get"')
        self.assertContains(response, '<label for="id_q">Search products</label>', html=True)
        self.assertContains(response, '<label for="id_reorder">Reorder status</label>', html=True)
        self.assertContains(response, 'name="q"')
        self.assertContains(response, 'name="reorder"')

    def test_search_matches_trimmed_case_insensitive_name_or_sku(self):
        for query in ("  gReEn tEa  ", "a-00"):
            with self.subTest(query=query):
                response = self.client.get(self.url, {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.product_ids(response), [self.attention.pk])
                self.assertContains(response, "1 of 6 products")
                self.assertContains(response, "Clear filters")

    def test_search_treats_sql_wildcard_characters_as_literals(self):
        for query in ("%", "_", "f_%"):
            with self.subTest(query=query):
                self.assertEqual(self.product_ids(self.client.get(self.url, {"q": query})), [self.literal.pk])

    def test_status_filters_use_real_recommendation_and_unavailable_inputs(self):
        expected = {
            "attention": [self.attention.pk],
            "above": [self.above.pk],
            "unavailable": [self.no_coverage.pk, self.no_settings.pk, self.inactive.pk, self.literal.pk],
        }
        for status, products in expected.items():
            with self.subTest(status=status):
                response = self.client.get(self.url, {"reorder": status})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.product_ids(response), products)
                self.assertContains(response, f'value="{status}" selected')

    def test_search_and_reorder_status_are_combined(self):
        response = self.client.get(self.url, {"q": "tea", "reorder": "above"})
        self.assertEqual(self.product_ids(response), [self.above.pk])
        self.assertContains(response, "Above reorder point")
        response = self.client.get(self.url, {"q": "tea", "reorder": "unavailable"})
        self.assertEqual(self.product_ids(response), [self.inactive.pk, self.literal.pk])

    def test_expired_stock_remains_in_attention_filter_before_quarantine_audit(self):
        at = timezone.now()
        today = at.astimezone(ZoneInfo("Asia/Singapore")).date()
        expiry = today + timedelta(days=1)
        receive_manual(
            user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.attention.pk,
            request_token=uuid.uuid4(), quantity_units=4, expiry_date=expiry,
        )
        # Synthetic coverage includes the date that is complete at the tested
        # future midnight, matching the existing reorder boundary fixtures.
        coverage = DemandCoverageDay.objects.create(
            inventory_product=InventoryProduct.objects.get(inventory=self.inventory, product=self.attention),
            day=today,
        )
        DemandCoverageEvent.objects.create(
            coverage_day=coverage, actor=self.manager, action="verified", reason="",
            recorded_at=at, verified_total_units=0,
        )
        at_expiry = datetime.combine(expiry, time.min, ZoneInfo("Asia/Singapore"))
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = at_expiry.timestamp()
        session.set_expiry(at_expiry + timedelta(hours=1))
        session.save()
        with patch("catalogue.views.timezone.now", return_value=at_expiry), patch(
            "accounts.sessions.timezone.now", return_value=at_expiry,
        ):
            response = self.client.get(self.url, {"reorder": "attention"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product_ids(response), [self.attention.pk])
        link = response.context["product_links"][0]
        self.assertEqual((link.display_physical_units, link.display_quarantine_units,
                          link.display_available_units), (4, 4, 0))

    def test_no_match_does_not_claim_inventory_has_no_products(self):
        response = self.client.get(self.url, {"q": "missing product"})
        self.assertEqual(self.product_ids(response), [])
        self.assertContains(response, "0 of 6 products")
        self.assertContains(response, "No products match your filters.")
        self.assertNotContains(response, "No products are linked")

    def test_empty_inventory_retains_existing_empty_state(self):
        response = self.client.get(reverse("inventory-products", args=[self.empty_inventory.pk]))
        self.assertContains(response, "No products are linked to this inventory.")
        self.assertNotContains(response, "No products match")

    def test_invalid_filter_or_oversize_search_is_rejected_without_results(self):
        for params, field in (({"reorder": "unknown"}, "reorder"), ({"q": "x" * 201}, "q")):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.context["filter_form"].errors)
                self.assertEqual(self.product_ids(response), [])
                self.assertContains(response, 'role="alert"', status_code=400)
                self.assertNotContains(response, "No products match", status_code=400)

    def test_search_text_is_escaped_when_redisplayed(self):
        query = '<img src=x onerror="alert(1)">'
        response = self.client.get(self.url, {"q": query})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<img src=x")
        self.assertContains(response, "&lt;img src=x")

    def test_search_never_reveals_products_outside_selected_inventory(self):
        for query in ("PRIVATE", "Other business tea"):
            with self.subTest(query=query):
                response = self.client.get(self.url, {"q": query})
                self.assertEqual(self.product_ids(response), [])
                self.assertEqual(response.context["total_product_count"], 6)

    def test_filters_do_not_bypass_assignment_business_or_auth_checks(self):
        for inventory in (self.private_inventory, self.other_inventory):
            for params in ({"q": "tea", "reorder": "attention"}, {"reorder": "invalid"}):
                with self.subTest(inventory=inventory.pk, params=params):
                    response = self.client.get(reverse("inventory-products", args=[inventory.pk]), params)
                    self.assertEqual(response.status_code, 404)
        self.login(self.unassigned)
        self.assertEqual(self.client.get(self.url, {"q": "tea"}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"q": "tea"}).status_code, 302)

    def test_manager_and_staff_keep_same_results_and_existing_action_permissions(self):
        for user, can_adjust in ((self.staff, False), (self.manager, True)):
            with self.subTest(user=user.pk):
                self.login(user)
                response = self.client.get(self.url, {"q": "black", "reorder": "above"})
                self.assertEqual(self.product_ids(response), [self.above.pk])
                self.assertEqual(response.context["can_adjust_stock"], can_adjust)
                self.assertContains(response, reverse("receive-batch", args=[self.inventory.pk, self.above.pk]))
                self.assertContains(response, reverse("issue-stock", args=[self.inventory.pk, self.above.pk]))
                adjust_url = reverse("adjust-stock", args=[self.inventory.pk, self.above.pk])
                if can_adjust:
                    self.assertContains(response, adjust_url)
                    self.assertContains(response, "Import CSV")
                else:
                    self.assertNotContains(response, adjust_url)
                    self.assertNotContains(response, "Import CSV")

    def test_search_and_filters_leave_stock_and_receipt_history_unchanged(self):
        before = list(InventoryProduct.objects.order_by("pk").values_list("pk", "physical_quantity_units"))
        receipt_count = ReceiptAuditEvent.objects.count()
        for params in ({"q": "tea"}, {"reorder": "attention"}, {"reorder": "unavailable"}):
            self.assertEqual(self.client.get(self.url, params).status_code, 200)
        self.assertEqual(
            list(InventoryProduct.objects.order_by("pk").values_list("pk", "physical_quantity_units")), before,
        )
        self.assertEqual(ReceiptAuditEvent.objects.count(), receipt_count)
