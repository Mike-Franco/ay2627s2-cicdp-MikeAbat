"""TORY-66: product page, suggested order, supplier field and the optional CSV column."""

from datetime import datetime, time, timedelta
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.forms import ProductForm
from catalogue.models import InventoryProduct, Product, ProductChangeAuditEvent
from catalogue.reorder import ORDER_COVER_DAYS, recommendation_from_evidence, suggested_order
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.csv_import import CsvImportRejected, import_stock_csv, parse_csv, parse_csv_rows
from receiving.models import DemandCoverageDay, DemandCoverageEvent, ObservationActivation
from receiving.services import SINGAPORE, issue_stock, receive_manual


class SuggestedOrderTests(SimpleTestCase):
    def test_formula_covers_fourteen_days_after_the_lead_time(self):
        self.assertEqual(ORDER_COVER_DAYS, 14)
        # 1.6/day × (14 + 2) + 0 − 4 = 21.6 → 22
        self.assertEqual(suggested_order(Fraction(8, 5), 2, 0, 4), 22)
        self.assertEqual(suggested_order(Fraction(1, 3), 1, 2, 0), 7)  # 5 + 2 = 7 exactly
        self.assertEqual(suggested_order(Fraction(1, 7), 7, 0, 0), 3)  # 3 exactly, no rounding up

    def test_already_above_target_is_zero_never_negative(self):
        self.assertEqual(suggested_order(Fraction(1), 2, 5, 21), 0)
        self.assertEqual(suggested_order(Fraction(1), 2, 5, 500), 0)
        self.assertEqual(suggested_order(Fraction(0), 3, 0, 0), 0)

    def test_missing_inputs_give_none(self):
        self.assertIsNone(suggested_order(None, 2, 1, 0))      # no forecast
        self.assertIsNone(suggested_order(Fraction(1), None, 1, 0))  # no lead time
        self.assertIsNone(suggested_order(Fraction(1), 2, None, 0))  # no safety stock

    def test_reorder_result_carries_it_or_explains_why_not(self):
        forecast = SimpleNamespace(available=True, average=Fraction(2))
        product = SimpleNamespace(lead_time_days=3, safety_stock_units=4)
        result = recommendation_from_evidence(product, 10, forecast, 0)
        self.assertEqual((result.reorder_point, result.suggested_units), (10, 28))  # 2×17 + 4 − 10
        unavailable = SimpleNamespace(available=False, average=None)
        self.assertIsNone(recommendation_from_evidence(product, 10, unavailable, 0).suggested_units)
        no_lead = SimpleNamespace(lead_time_days=None, safety_stock_units=4)
        result = recommendation_from_evidence(no_lead, 10, forecast, 0)
        self.assertEqual((result.suggested_units, result.missing_settings), (None, ("lead time",)))


class SupplierCsvColumnTests(SimpleTestCase):
    def test_parser_accepts_the_optional_column(self):
        self.assertEqual(parse_csv(b"sku,change\nP,+1\n"), [(2, "P", 1)])
        rows, suppliers = parse_csv_rows(b"sku,change,supplier_name\nP,+1, Oatside SG \nQ,-2,\n")
        self.assertEqual(rows, [(2, "P", 1), (3, "Q", -2)])
        self.assertEqual(suppliers, {2: "Oatside SG"})
        for raw in (b"sku,change,supplier_name\nP,+1\n", b"sku,change\nP,+1,Oatside\n",
                    b"sku,change,supplier\nP,+1,x\n", b"sku,change,supplier_name\nP,+1,\"a\nb\"\n",
                    b"sku,change,supplier_name\nP,+1," + b"x" * 121 + b"\n"):
            with self.subTest(raw=raw[:40]), self.assertRaises(CsvImportRejected):
                parse_csv_rows(raw)


class ProductPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Page business")
        cls.manager = users.create_user(email="page-manager@example.test")
        cls.staff = users.create_user(email="page-staff@example.test")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Grocery")
        cls.pharmacy = Inventory.objects.create(business=cls.business, name="Pharmacy")
        for role in (manager_role, staff_role):
            InventoryAssignment.objects.create(membership=role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.pharmacy)
        cls.product = Product.objects.create(
            business=cls.business, sku="GR-01", name="Oat Milk", base_unit_label="carton",
            expiry_tracking_required=False, lead_time_days=2, safety_stock_units=0, supplier_name="Oatside SG")
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product, selling_price="4.20")
        InventoryProduct.objects.create(inventory=cls.pharmacy, product=cls.product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def setUp(self):
        self.login(self.manager)
        self.url = reverse("product-stock", args=[self.inventory.pk, self.product.pk])
        self.today = timezone.now().astimezone(SINGAPORE).date()

    def receive(self, units, expiry=None):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                       request_token=uuid4(), quantity_units=units, expiry_date=expiry)

    def verified_week(self, daily_units):
        """Issue `daily_units` on each of the last seven complete days and verify them."""
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=self.today - timedelta(days=10),
            origin_xid="1", actual_committed_at=timezone.now(), state="active")
        for offset in range(7, 0, -1):
            day = self.today - timedelta(days=offset)
            if daily_units:
                with patch("receiving.services.timezone.now",
                           return_value=datetime.combine(day, time(12), SINGAPORE)):
                    issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                                quantity_units=daily_units)
            coverage = DemandCoverageDay.objects.create(inventory_product=self.link, day=day)
            DemandCoverageEvent.objects.create(coverage_day=coverage, actor=self.manager, action="verified",
                                               reason="", recorded_at=timezone.now(), verified_total_units=daily_units)

    def test_overview_strip_outlook_and_callout(self):
        self.receive(30)
        self.verified_week(2)  # 30 − 14 = 16 on hand, 2 a day
        with patch("receiving.demand.tracking_enabled", return_value=True):
            response = self.client.get(self.url)
        info = response.context["info"]
        self.assertEqual((info["available"], info["average"], info["reorder_point"]), (16, "2.00", 4))
        self.assertEqual(info["suggested"], 2 * (14 + 2) + 0 - 16)
        self.assertEqual(info["run_out"], self.today + timedelta(days=8))
        self.assertEqual(info["value"], "S$67.20")
        self.assertContains(response, "covers 14 days + lead time")
        self.assertContains(response, "Order 16 cartons today. Lead time is 2 days, so stock arrives")
        self.assertEqual(len(response.context["projection"]), 8)
        self.assertEqual(response.context["projection"][-1]["stock"], 2.0)
        self.assertContains(response, "Oatside SG · 2-day lead")
        self.assertContains(response, "<dt>Also in</dt><dd>Pharmacy</dd>", html=True)
        self.assertContains(response, 'id="outlook-data"')

    def test_missing_inputs_show_a_dash_and_the_reason(self):
        Product.objects.filter(pk=self.product.pk).update(lead_time_days=None)
        self.receive(5)
        response = self.client.get(self.url)
        self.assertIsNone(response.context["info"]["suggested"])
        self.assertIsNone(response.context["callout"])
        self.assertEqual(response.context["projection"], [])
        self.assertContains(response, '<div class="k">Suggested order</div><div class="v">—</div>')

    def test_header_actions_follow_permissions(self):
        response = self.client.get(self.url)
        for label in (">Receive<", ">Issue<", ">Adjust<", "Edit product", "Selling price", "Deactivate product"):
            self.assertContains(response, label)
        self.login(self.staff)
        response = self.client.get(self.url)
        self.assertContains(response, ">Receive<")
        self.assertContains(response, ">Issue<")
        for label in (">Adjust<", "Edit product", "Deactivate product", "More actions"):
            self.assertNotContains(response, label)
        self.assertContains(response, "Open in Activity log")  # TORY-67: Staff can read their movements

    def test_tabs_batches_and_recent_history(self):
        self.receive(4, expiry=self.today + timedelta(days=3))
        self.receive(6)
        issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                    quantity_units=4)  # uses up the expiring batch first (FEFO)
        response = self.client.get(self.url)
        self.assertContains(response, ">Batches (1)</a>")
        self.assertEqual([row["batch"].receipt_sequence for row in response.context["batches"]], [2])
        all_batches = self.client.get(self.url, {"tab": "batches"})
        self.assertEqual([(row["batch"].receipt_sequence, row["status"]) for row in all_batches.context["batches"]],
                         [(1, "Used up"), (2, "Available")])
        self.assertContains(all_batches, '<a href="%s?tab=batches" aria-current="page">' % self.url)
        recent = response.context["recent"]
        self.assertEqual([(row["action"], row["change"]) for row in recent], [("Issued", -4), ("Received", 6),
                                                                              ("Received", 4)])
        self.assertContains(response, "Showing <strong>3</strong> of 3")
        self.assertContains(response, f"?inventory={self.inventory.pk}&amp;q=GR-01")
        self.assertContains(response, "−4")


class SupplierFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Supplier business")
        cls.manager = get_user_model().objects.create_user(email="supplier@example.test")
        role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Shelf")
        InventoryAssignment.objects.create(membership=role, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="S-1", name="Soap", base_unit_label="bar",
                                             expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def test_form_field_is_optional_and_capped(self):
        form = ProductForm(instance=self.product)
        self.assertIn("supplier_name", form.fields)
        self.assertFalse(form.fields["supplier_name"].required)
        self.assertEqual(form.fields["supplier_name"].max_length, 120)
        self.assertEqual(Product._meta.get_field("supplier_name").default, "")

    def test_edit_form_saves_and_audits_the_supplier(self):
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        response = self.client.post(reverse("product-edit", args=[self.inventory.pk, self.product.pk]), {
            "name": "Soap", "base_unit_label": "bar", "expiry_tracking_required": "no",
            "supplier_name": "Clean Co", "lead_time_days": "3", "safety_stock_units": "1", "category": "",
        })
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.supplier_name, "Clean Co")
        self.assertEqual(ProductChangeAuditEvent.objects.get(action="edit").after["supplier_name"], "Clean Co")

    def test_csv_import_with_and_without_the_column(self):
        import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk, raw_bytes=b"sku,change\nS-1,+5\n")
        self.product.refresh_from_db()
        self.assertEqual(self.product.supplier_name, "")
        self.assertFalse(ProductChangeAuditEvent.objects.exists())
        import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                         raw_bytes=b"sku,change,supplier_name\nS-1,+1,Old Co\nS-1,+2,Clean Co\n")
        self.product.refresh_from_db()
        self.assertEqual(self.product.supplier_name, "Clean Co")  # the last non-blank value wins
        audit = ProductChangeAuditEvent.objects.get()
        self.assertEqual((audit.before["supplier_name"], audit.after["supplier_name"]), ("", "Clean Co"))
        # A blank cell leaves the supplier alone and writes no audit row.
        import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                         raw_bytes=b"sku,change,supplier_name\nS-1,-1,\n")
        self.product.refresh_from_db()
        self.assertEqual(self.product.supplier_name, "Clean Co")
        self.assertEqual(ProductChangeAuditEvent.objects.count(), 1)
        self.assertEqual(InventoryProduct.objects.get(product=self.product).physical_quantity_units, 7)
