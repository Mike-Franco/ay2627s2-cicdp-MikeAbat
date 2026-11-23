"""Demo polish: seeded prices and names, whole units and 1-decimal days of supply,
inventory deactivation confirm step, one-line activity log rows, mobile activity preview."""

import os
import uuid
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import Category, InventoryProduct, Product, ProductChangeAuditEvent
from catalogue.templatetags.tory_format import days, one_decimal, units, whole_units
from inventory_access.models import (
    Business, BusinessMembership, Inventory, InventoryAssignment, InventoryChangeAuditEvent,
)
from receiving.management.commands.seed_demo import DEMO_CATEGORIES, DEMO_PRICES, DEMO_PROFILES
from receiving.models import DemandAuditEvent, ReceivingBatch
from receiving.services import receive_manual


class FormatFilterTests(SimpleTestCase):
    def test_units_round_up_to_whole_units(self):
        self.assertEqual(units(Decimal("12.29")), 13)
        self.assertEqual(units(Decimal("11.00")), 11)
        self.assertEqual(units(0), 0)
        self.assertEqual(units(None), "—")
        self.assertIsNone(whole_units(None))

    def test_days_show_one_decimal_place(self):
        self.assertEqual(days(Decimal("3.4567")), "3.5")
        self.assertEqual(days(Decimal("8")), "8.0")
        self.assertEqual(days(Decimal("0.04")), "0.0")
        self.assertEqual(days(None), "—")
        self.assertEqual(one_decimal(Decimal("2.25")), "2.3")


class SeedDemoPolishTests(TestCase):
    env = {
        "DEMO_MANAGER_EMAIL": "polish-manager@example.test",
        "DEMO_STAFF_EMAIL": "polish-staff@example.test",
        "DEMO_MANAGER_PASSWORD": "polish-env-password-1!",
        "DEMO_STAFF_PASSWORD": "polish-env-password-2!",
    }

    def seed(self):
        output = StringIO()
        with patch.dict(os.environ, self.env):
            call_command("seed_demo", stdout=output)
        return output.getvalue()

    def test_seed_sets_prices_for_every_product_and_demo_profiles(self):
        self.seed()
        links = InventoryProduct.objects.filter(inventory__business__name="Tory Demo").select_related("product")
        self.assertEqual(links.count(), len(DEMO_PRICES))
        for link in links:
            self.assertEqual(link.selling_price, Decimal(DEMO_PRICES[link.product.sku]))
        users = get_user_model().objects
        manager = users.get(email=self.env["DEMO_MANAGER_EMAIL"])
        staff = users.get(email=self.env["DEMO_STAFF_EMAIL"])
        self.assertEqual((manager.display_name, manager.job_title), DEMO_PROFILES["manager"][:2])
        self.assertEqual((staff.display_name, staff.job_title), DEMO_PROFILES["staff"][:2])
        self.assertEqual(manager.display_label, "Mia Tan")

    def test_rerun_fills_blank_prices_names_and_ordering_settings_without_touching_stock(self):
        self.seed()
        users = get_user_model().objects
        manager = users.get(email=self.env["DEMO_MANAGER_EMAIL"])
        staff = users.get(email=self.env["DEMO_STAFF_EMAIL"])
        # Simulate a demo seeded before this change, plus one name the user edited.
        InventoryProduct.objects.filter(inventory__business__name="Tory Demo").update(selling_price=None)
        products = Product.objects.filter(business__name="Tory Demo")
        products.update(lead_time_days=None, safety_stock_units=None, supplier_name="")
        products.filter(sku="GR-01").update(lead_time_days=2, safety_stock_units=0, supplier_name="Custom Supplier")
        users.filter(pk=manager.pk).update(display_name="", job_title="")
        users.filter(pk=staff.pk).update(display_name="Ravi K.", job_title="")
        counts = (ReceivingBatch.objects.count(), DemandAuditEvent.objects.count(), Product.objects.count())

        output = self.seed()

        self.assertIn("already seeded", output)
        self.assertIn("Backfilled 2 demo profile(s), 15 selling price(s) and 0 product categories.", output)
        self.assertIn("Backfilled ordering settings for 14 demo product(s).", output)
        self.assertNotIn("password", output)
        self.assertFalse(InventoryProduct.objects.filter(selling_price__isnull=True).exists())
        self.assertFalse(products.filter(lead_time_days__isnull=True).exists())
        self.assertFalse(products.filter(safety_stock_units__isnull=True).exists())
        self.assertFalse(products.filter(supplier_name="").exists())
        oat_milk = products.get(sku="GR-01")
        self.assertEqual((oat_milk.lead_time_days, oat_milk.safety_stock_units, oat_milk.supplier_name),
                         (2, 0, "Custom Supplier"))
        manager.refresh_from_db()
        staff.refresh_from_db()
        self.assertEqual(manager.display_name, "Mia Tan")
        self.assertEqual(staff.display_name, "Ravi K.")
        self.assertEqual(staff.job_title, "Stock Assistant")
        self.assertEqual(
            (ReceivingBatch.objects.count(), DemandAuditEvent.objects.count(), Product.objects.count()), counts,
        )
        self.assertNotIn("Backfilled", self.seed())

    def test_rerun_backfills_categories_only_for_uncategorised_products(self):
        self.seed()
        business = Business.objects.get(name="Tory Demo")
        products = Product.objects.filter(business=business)
        # Simulate a v1.0.0 demo (no categories), except one product a Manager
        # already filed under their own category, reusing a demo name in another case.
        custom = Category.objects.create(business=business, name="Shelf stable")
        products.exclude(sku="GR-02").update(category=None)
        products.filter(sku="GR-02").update(category=custom)
        Category.objects.filter(business=business).exclude(pk=custom.pk).delete()
        Category.objects.create(business=business, name="pantry")
        audits = ProductChangeAuditEvent.objects.count()
        counts = (ReceivingBatch.objects.count(), DemandAuditEvent.objects.count())

        output = self.seed()

        self.assertIn("and 14 product categories.", output)
        self.assertEqual(products.filter(category__isnull=True).count(), 0)
        self.assertEqual(products.get(sku="GR-02").category, custom)
        self.assertEqual(products.get(sku="GR-03").category.name, "pantry")
        self.assertEqual(Category.objects.filter(business=business, name__iexact="pantry").count(), 1)
        self.assertSetEqual(
            {name.casefold() for name in Category.objects.filter(business=business).values_list("name", flat=True)},
            {name.casefold() for name in DEMO_CATEGORIES} | {"shelf stable"},
        )
        for name, skus in DEMO_CATEGORIES.items():
            for sku in skus:
                if sku != "GR-02":
                    self.assertEqual(products.get(sku=sku).category.name.casefold(), name.casefold())
        self.assertEqual(ProductChangeAuditEvent.objects.count(), audits + 14)
        self.assertEqual((ReceivingBatch.objects.count(), DemandAuditEvent.objects.count()), counts)
        self.assertNotIn("Backfilled", self.seed())


class PolishPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Polish business")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Front shelf")
        users = get_user_model().objects
        cls.manager = users.create_user(email="a-very-long-manager-address@polish.example.test",
                                        display_name="Mia Tan", job_title="Store Manager")
        cls.staff = users.create_user(email="polish-staff@example.test")
        manager = BusinessMembership.objects.create(user=cls.manager, business=cls.business,
                                                    role=BusinessMembership.Role.MANAGER)
        staff = BusinessMembership.objects.create(user=cls.staff, business=cls.business,
                                                  role=BusinessMembership.Role.STAFF)
        InventoryAssignment.objects.create(membership=manager, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=staff, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="POL-1", name="Bandages",
                                             base_unit_label="each", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def setUp(self):
        self.login(self.manager)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def receive(self, times):
        for _ in range(times):
            receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                           request_token=uuid.uuid4(), quantity_units=1, expiry_date=None)

    def test_inventory_list_has_no_direct_deactivate_button(self):
        response = self.client.get(reverse("inventory-list"))
        self.assertContains(response, reverse("inventory-rename", args=[self.inventory.pk]))
        self.assertNotContains(response, 'value="false"')
        self.assertNotContains(response, ">Deactivate<")

    def test_deactivation_goes_through_edit_page_and_confirm_step(self):
        status_url = reverse("inventory-status", args=[self.inventory.pk])
        self.assertContains(self.client.get(reverse("inventory-rename", args=[self.inventory.pk])), status_url)
        confirm = self.client.get(status_url)
        self.assertContains(confirm, "Deactivate Front shelf?")
        self.assertContains(confirm, 'name="is_active" value="false"')
        self.inventory.refresh_from_db()
        self.assertTrue(self.inventory.is_active)
        self.assertFalse(InventoryChangeAuditEvent.objects.exists())

        self.assertRedirects(self.client.post(status_url, {"is_active": "false", "confirm_name": "Front shelf"}),
                             reverse("inventory-list"))
        self.inventory.refresh_from_db()
        self.assertFalse(self.inventory.is_active)
        self.assertRedirects(self.client.get(status_url), reverse("inventory-list"))
        listing = self.client.get(reverse("inventory-list"))
        self.assertContains(listing, 'name="is_active" value="true"')
        self.assertContains(listing, "Reactivate")

    def test_staff_cannot_open_deactivation_confirm(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("inventory-status", args=[self.inventory.pk])).status_code, 404)

    def test_activity_log_rows_show_display_name_without_email(self):
        self.receive(1)
        response = self.client.get(reverse("activity-log", args=[self.business.pk]))
        self.assertContains(response, '<span class="user-ref-name">Mia Tan</span>', html=False)
        self.assertContains(response, '<span class="activity-role">Manager</span>', html=False)
        body = response.content.decode()
        row = body[body.index("<tbody>"):body.index("</tbody>")]
        # The email is only in the hover title, never as visible cell text.
        self.assertEqual(row.count(self.manager.email), 1)
        self.assertIn(f'title="Mia Tan ({self.manager.email})"', row)

    def test_dashboard_marks_recent_activity_for_five_row_mobile_preview(self):
        self.receive(7)
        response = self.client.get(reverse("home"))
        self.assertEqual(len(response.context["activities"]["rows"]), 7)
        self.assertContains(response, "responsive-list mobile-preview")
        self.assertContains(response, "View all recent activity")
        expanded = self.client.get(reverse("home"), {"panel": "activity"})
        self.assertNotContains(expanded, "mobile-preview")
        self.assertNotContains(expanded, "View all recent activity")

    def test_dashboard_has_no_mobile_view_all_for_five_rows(self):
        self.receive(5)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "View all recent activity")
