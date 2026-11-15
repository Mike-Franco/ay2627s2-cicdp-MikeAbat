from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from catalogue.models import InventoryProduct, Product


class CatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business_a = Business.objects.create(name="Catalogue A")
        cls.business_b = Business.objects.create(name="Catalogue B")
        cls.manager_a = get_user_model().objects.create_user(
            email="catalogue-manager-a@example.test", password="test-only-password"
        )
        cls.manager_b = get_user_model().objects.create_user(
            email="catalogue-manager-b@example.test", password="test-only-password"
        )
        cls.staff_a = get_user_model().objects.create_user(
            email="catalogue-staff-a@example.test", password="test-only-password"
        )
        cls.unassigned_staff = get_user_model().objects.create_user(
            email="catalogue-unassigned@example.test", password="test-only-password"
        )
        cls.membership_a = BusinessMembership.objects.create(
            business=cls.business_a, user=cls.manager_a, role=BusinessMembership.Role.MANAGER
        )
        cls.membership_b = BusinessMembership.objects.create(
            business=cls.business_b, user=cls.manager_b, role=BusinessMembership.Role.MANAGER
        )
        cls.staff_membership_a = BusinessMembership.objects.create(
            business=cls.business_a, user=cls.staff_a, role=BusinessMembership.Role.STAFF
        )
        cls.inventory_a = Inventory.objects.create(business=cls.business_a, name="Catalogue shelf A")
        cls.inventory_b = Inventory.objects.create(business=cls.business_b, name="Catalogue shelf B")
        InventoryAssignment.objects.create(membership=cls.membership_a, inventory=cls.inventory_a)
        InventoryAssignment.objects.create(membership=cls.membership_b, inventory=cls.inventory_b)
        InventoryAssignment.objects.create(membership=cls.staff_membership_a, inventory=cls.inventory_a)
        cls.product_a = Product.objects.create(
            business=cls.business_a, sku="Tea-01", name="Tea", lead_time_days=1, safety_stock_units=0
        )
        cls.product_b = Product.objects.create(
            business=cls.business_b, sku="Tea-01", name="Other business tea"
        )
        InventoryProduct.objects.create(inventory=cls.inventory_a, product=cls.product_a)
        InventoryProduct.objects.create(inventory=cls.inventory_b, product=cls.product_b)

    def authenticate(self, user):
        self.client.force_login(user)
        session = self.client.session
        now = timezone.now().timestamp()
        session[CREATED_KEY] = now
        session[ACTIVE_KEY] = now
        session.save()

    def test_database_rejects_case_insensitive_duplicate_sku_in_same_business(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO catalogue_product (business_id, sku, name, lead_time_days, safety_stock_units) "
                    "VALUES (%s, %s, %s, NULL, NULL)",
                    [self.business_a.pk, " tea-01 ", "Duplicate"],
                )

    def test_same_case_insensitive_sku_is_allowed_in_different_businesses(self):
        self.assertNotEqual(self.product_a.business_id, self.product_b.business_id)
        self.assertEqual(self.product_a.sku.lower(), self.product_b.sku.lower())

    def test_product_sku_and_owner_are_immutable_and_delete_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE catalogue_product SET sku = %s WHERE id = %s", ["TEA-02", self.product_a.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE catalogue_product SET business_id = %s WHERE id = %s",
                    [self.business_b.pk, self.product_a.pk],
                )
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM catalogue_product WHERE id = %s", [self.product_a.pk])

    def test_database_rejects_cross_business_inventory_product_link(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO catalogue_inventoryproduct (inventory_id, product_id, selling_price) "
                    "VALUES (%s, %s, NULL)",
                    [self.inventory_b.pk, self.product_a.pk],
                )

    def test_database_rejects_cross_business_link_update_and_parent_move(self):
        link = InventoryProduct.objects.get(inventory=self.inventory_a, product=self.product_a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE catalogue_inventoryproduct SET product_id = %s WHERE id = %s",
                    [self.product_b.pk, link.pk],
                )

        spare_inventory = Inventory.objects.create(business=self.business_a, name="Unassigned linked shelf")
        InventoryProduct.objects.create(inventory=spare_inventory, product=self.product_a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE inventory_access_inventory SET business_id = %s WHERE id = %s",
                    [self.business_b.pk, spare_inventory.pk],
                )

    def test_inventory_product_model_rejects_cross_business_link(self):
        link = InventoryProduct(inventory=self.inventory_b, product=self.product_a)
        with self.assertRaises(ValidationError):
            link.save()

    def test_product_lead_time_and_safety_stock_boundaries(self):
        self.assertEqual(self.product_a.lead_time_days, 1)
        self.assertEqual(self.product_a.safety_stock_units, 0)
        invalid_lead_time = Product(business=self.business_a, sku="Tea-02", name="Invalid", lead_time_days=0)
        with self.assertRaises(ValidationError):
            invalid_lead_time.full_clean()
        invalid_safety_stock = Product(
            business=self.business_a, sku="Tea-03", name="Invalid", safety_stock_units=-1
        )
        with self.assertRaises(ValidationError):
            invalid_safety_stock.full_clean()
        Product.objects.create(business=self.business_a, sku="Tea-04", name="Unset settings")

    def test_catalogue_reads_are_limited_to_authorized_inventory_links(self):
        self.authenticate(self.manager_a)
        response = self.client.get(reverse("product-catalogue"))
        self.assertContains(response, "Tea-01 — Tea")
        self.assertNotContains(response, "Other business tea")
        response = self.client.get(reverse("inventory-products", args=[self.inventory_b.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Other business tea", status_code=404)

    def test_staff_and_unassigned_user_product_reads_are_scoped(self):
        self.authenticate(self.staff_a)
        self.assertContains(self.client.get(reverse("product-catalogue")), "Tea-01 — Tea")
        self.assertEqual(
            self.client.get(reverse("inventory-products", args=[self.inventory_b.pk])).status_code,
            404,
        )
        self.client.logout()
        self.authenticate(self.unassigned_staff)
        response = self.client.get(reverse("product-catalogue"))
        self.assertContains(response, "No products are linked")
        self.assertNotContains(response, "Tea-01")

    def test_inventory_product_view_requires_auth_and_scoped_assignment(self):
        response = self.client.get(reverse("inventory-products", args=[self.inventory_a.pk]))
        self.assertEqual(response.status_code, 302)
        self.authenticate(self.manager_a)
        with patch("accounts.sessions.timezone.now", return_value=timezone.now() + timedelta(hours=9)):
            response = self.client.get(reverse("inventory-products", args=[self.inventory_a.pk]))
        self.assertEqual(response.status_code, 302)

    def test_product_stock_page_uses_scoped_link_and_role_actions(self):
        url = reverse("product-stock", args=[self.inventory_a.pk, self.product_a.pk])
        self.authenticate(self.staff_a)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["link"].display_available_units, 0)
        self.assertContains(response, f'href="{url}" aria-current="page"')
        self.assertContains(response, f'href="{reverse("receive-batch", args=[self.inventory_a.pk, self.product_a.pk])}"')
        self.assertContains(response, "Stock history")
        self.assertContains(response, "Demand forecast")
        self.assertNotContains(response, "Adjust batch count")
        self.assertNotContains(response, f'href="{reverse("adjust-stock", args=[self.inventory_a.pk, self.product_a.pk])}"')
        self.assertEqual(self.client.get(reverse("product-stock", args=[self.inventory_b.pk, self.product_b.pk])).status_code, 404)
        self.authenticate(self.manager_a)
        response = self.client.get(url)
        self.assertContains(response, "Adjust batch count")
        self.assertContains(response, f'href="{reverse("adjust-stock", args=[self.inventory_a.pk, self.product_a.pk])}"')

    def test_transaction_forms_keep_post_and_csrf_in_assigned_scope(self):
        product_args = [self.inventory_a.pk, self.product_a.pk]
        self.authenticate(self.staff_a)
        for route in ("receive-batch", "issue-stock"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route, args=product_args))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<form method="post"')
                self.assertContains(response, 'name="csrfmiddlewaretoken"')
        for route in ("adjust-stock", "dispose-stock"):
            self.assertEqual(self.client.get(reverse(route, args=product_args)).status_code, 404)
        self.assertEqual(self.client.get(reverse("import-stock-csv", args=[self.inventory_a.pk])).status_code, 404)

        self.authenticate(self.manager_a)
        for route, args in (("adjust-stock", product_args), ("import-stock-csv", [self.inventory_a.pk])):
            with self.subTest(route=route):
                response = self.client.get(reverse(route, args=args))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<form method="post"')
                self.assertContains(response, 'name="csrfmiddlewaretoken"')
