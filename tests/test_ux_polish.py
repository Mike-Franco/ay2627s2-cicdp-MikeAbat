from datetime import UTC, date, datetime
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.template import engines
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from django.views import defaults

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from catalogue.templatetags.tory_format import sgdate
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.services import issue_stock, receive_manual


class DateFilterTests(SimpleTestCase):
    def test_dates_and_datetimes_use_one_singapore_format(self):
        self.assertEqual(sgdate(date(2026, 11, 20)), "20 Nov 2026")
        # 16:30 UTC on 20 Nov is 00:30 on 21 Nov in Singapore.
        self.assertEqual(sgdate(datetime(2026, 11, 20, 16, 30, tzinfo=UTC)), "21 Nov 2026, 00:30")
        self.assertEqual(sgdate(datetime(2026, 11, 20, 12, 0)), "20 Nov 2026, 12:00")
        self.assertEqual(sgdate(date(2026, 1, 5)), "5 Jan 2026")

    def test_iso_strings_empty_and_unknown_values(self):
        self.assertEqual(sgdate("2026-11-20"), "20 Nov 2026")
        self.assertEqual(sgdate("2026-11-20T04:00:00+00:00"), "20 Nov 2026, 12:00")
        self.assertEqual(sgdate(None), "")
        self.assertEqual(sgdate(""), "")
        self.assertEqual(sgdate("not a date"), "not a date")

    def test_filter_is_available_to_templates(self):
        template = engines["django"].from_string("{% load tory_format %}{{ value|sgdate|default:'Undated' }}")
        self.assertEqual(template.render({"value": date(2026, 11, 20)}), "20 Nov 2026")
        self.assertEqual(template.render({"value": None}), "Undated")

    def test_templates_use_no_other_date_format(self):
        from pathlib import Path

        from django.conf import settings
        offenders = [str(path) for path in Path(settings.BASE_DIR, "templates").rglob("*.html")
                     if "|date:" in path.read_text(encoding="utf-8")]
        self.assertEqual(offenders, [])


class ErrorPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(email="errors@example.test")

    def test_404_uses_tory_shell_with_link_home(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, 'class="brand"', status_code=404)
        self.assertContains(response, 'href="/"', status_code=404)
        self.assertNotContains(response, "The requested resource was not found", status_code=404)

    def test_404_keeps_the_workspace_shell_when_signed_in(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        response = self.client.get("/no-such-page/")
        self.assertContains(response, 'id="workspace-sidebar"', status_code=404)

    def test_403_page(self):
        request = RequestFactory().get("/")
        request.user = self.user
        response = defaults.permission_denied(request, PermissionDenied())
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Access denied", response.content)
        self.assertIn(b'href="/"', response.content)

    def test_500_page_needs_no_database_or_context_processors(self):
        request = RequestFactory().get("/")
        with self.assertNumQueries(0):
            response = defaults.server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Something went wrong", response.content)
        self.assertIn(b'href="/"', response.content)
        self.assertIn(b"tory/app.css", response.content)
        self.assertNotIn(b"workspace-sidebar", response.content)


class PolishedPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Polish business")
        cls.manager = users.create_user(email="polish-manager@example.test")
        cls.staff = users.create_user(email="polish-staff@example.test")
        cls.manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Polish shelf")
        cls.private = Inventory.objects.create(business=cls.business, name="Private shelf")
        InventoryAssignment.objects.create(membership=cls.manager_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.staff_role, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="P-1", name="Paper bags",
                                             base_unit_label="bag", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def stock(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                       request_token=uuid4(), quantity_units=5, expiry_date=None)
        issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                    quantity_units=1)

    def test_dashboard_tiles_and_activity_quantity(self):
        self.stock()
        self.login(self.manager)
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'class="stat-tile ', count=6)
        self.assertContains(response, "Unverified demand days")
        self.assertContains(response, "Issued</td>")
        self.assertContains(response, "1 bag</td>")
        self.assertContains(response, "Received</td>")
        self.assertContains(response, "5 bag</td>")
        self.assertContains(response, f'href="{reverse("product-stock", args=[self.inventory.pk, self.product.pk])}">Paper bags</a>')
        self.login(self.staff)
        self.assertContains(self.client.get(reverse("home")), 'class="stat-tile ', count=6)

    def test_issue_form_shows_available_and_plain_labels(self):
        self.stock()
        self.login(self.staff)
        response = self.client.get(reverse("issue-stock", args=[self.inventory.pk, self.product.pk]))
        self.assertContains(response, "Available: <strong>4 bag</strong>", html=False)
        self.assertContains(response, "Quantity (bag)</label>")
        self.assertNotContains(response, "Quantity units:")

    def test_product_form_labels_and_help_text(self):
        self.login(self.manager)
        response = self.client.get(reverse("product-create", args=[self.inventory.pk]))
        for label in ("SKU", "Lead time (days)", "Safety stock (units)", "Base unit", "Expiry policy"):
            self.assertContains(response, f">{label}</label>")
        self.assertNotContains(response, ":</label>")
        self.assertContains(response, "The single item you count")
        self.assertContains(response, "expired stock is quarantined automatically")

    def test_staff_table_shows_email_once_with_inventories(self):
        self.login(self.manager)
        response = self.client.get(reverse("manager-staff", args=[self.business.pk]))
        self.assertContains(response, self.staff.email, count=1)
        self.assertContains(response, "<th scope=\"col\">Inventories</th>", html=True)
        self.assertContains(response, '<span class="inventory-badge">Polish shelf</span>', html=True)

    def test_staff_inventory_names_never_name_inventories_outside_the_viewer(self):
        from catalogue.templatetags.tory_cards import staff_inventory_names

        InventoryAssignment.objects.create(membership=self.staff_role, inventory=self.private)
        request = RequestFactory().get("/")
        request.user = self.manager
        with self.assertNumQueries(1):
            names = staff_inventory_names({"request": request}, [self.staff], self.business.pk)
        self.assertEqual(dict(names), {self.staff.pk: ["Polish shelf"]})

    def test_inventory_cards_show_counts(self):
        self.login(self.manager)
        response = self.client.get(reverse("inventory-list"))
        self.assertContains(response, 'class="inventory-card"', count=1)
        self.assertContains(response, "<strong>1</strong>product", html=False)
        self.assertContains(response, "<strong>0</strong>at or below reorder point", html=False)

    def test_sidebar_team_group_is_manager_only(self):
        self.login(self.manager)
        self.assertContains(self.client.get(reverse("inventory-list")), ">TEAM</p>")
        self.login(self.staff)
        self.assertNotContains(self.client.get(reverse("inventory-list")), ">TEAM</p>")

    def test_single_page_hides_pagination(self):
        self.stock()
        self.login(self.manager)
        response = self.client.get(reverse("stock-history", args=[self.inventory.pk, self.product.pk]))
        self.assertNotContains(response, "Page 1 of 1")
        self.assertNotContains(response, ">Previous<")

    def test_forecast_summary_cards(self):
        self.login(self.manager)
        response = self.client.get(reverse("demand-forecast", args=[self.inventory.pk, self.product.pk]))
        for label in ("Average daily demand", "Reorder point", "Suggested quantity"):
            self.assertContains(response, f'<span class="stat-label">{label}</span>', html=False)

    def test_products_table_has_mobile_card_markup(self):
        self.login(self.manager)
        response = self.client.get(reverse("inventory-products", args=[self.inventory.pk]))
        self.assertContains(response, 'class="products-table product-cards"')
        self.assertContains(response, '<summary class="btn btn-sm btn-outline-secondary">More</summary>', html=False)
