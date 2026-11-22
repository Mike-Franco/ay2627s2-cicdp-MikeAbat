from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import Category, InventoryProduct, Product, ProductChangeAuditEvent
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


class CategoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Category business")
        cls.other = Business.objects.create(name="Outside")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Shelf")
        for role in ("manager", "staff"):
            user = get_user_model().objects.create_user(email=f"category-{role}@example.test")
            setattr(cls, role, user)
            membership = BusinessMembership.objects.create(business=cls.business, user=user, role=role)
            InventoryAssignment.objects.create(membership=membership, inventory=cls.inventory)
        cls.category = Category.objects.create(business=cls.business, name="Pantry")
        cls.foreign = Category.objects.create(business=cls.other, name="Pantry")
        cls.product = Product.objects.create(
            business=cls.business, category=cls.category, name="Rice", sku="RICE",
            base_unit_label="bag", expiry_tracking_required=False,
        )
        plain = Product.objects.create(business=cls.business, name="Plain salt", sku="SALT")
        for product in (cls.product, plain):
            InventoryProduct.objects.create(inventory=cls.inventory, product=product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[ACTIVE_KEY] = session[CREATED_KEY] = timezone.now().timestamp()
        session.save()

    def test_manager_crud_and_protected_delete(self):
        self.login(self.manager)
        listing = reverse("category-list", args=[self.business.pk])
        create = reverse("category-create", args=[self.business.pk])
        self.assertContains(self.client.get(reverse("product-catalogue")), listing)
        self.assertRedirects(self.client.post(create, {"name": "  Snacks  ", "colour": "#305A9F"}), listing)
        snacks = Category.objects.get(business=self.business, name="Snacks")
        duplicate = self.client.post(create, {"name": " snacks "})
        self.assertEqual(duplicate.status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Category.objects.bulk_create([Category(business=self.business, name=" SNACKS ")])
        edit = reverse("category-edit", args=[self.business.pk, snacks.pk])
        self.assertRedirects(self.client.post(edit, {"name": "Treats"}), listing)
        self.assertContains(self.client.get(listing), "Treats")
        self.assertRedirects(self.client.post(reverse("category-delete", args=[self.business.pk, snacks.pk])), listing)
        self.assertFalse(Category.objects.filter(pk=snacks.pk).exists())
        in_use = reverse("category-delete", args=[self.business.pk, self.category.pk])
        self.assertContains(self.client.post(in_use, follow=True), "before deleting")
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_scope_and_staff_filters(self):
        self.login(self.manager)
        self.assertEqual(self.client.get(reverse("category-list", args=[self.other.pk])).status_code, 404)
        self.assertEqual(self.client.post(
            reverse("category-delete", args=[self.business.pk, self.foreign.pk]),
        ).status_code, 404)
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("category-list", args=[self.business.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("category-create", args=[self.business.pk])).status_code, 404)
        for url in (reverse("product-catalogue"), reverse("inventory-products", args=[self.inventory.pk])):
            response = self.client.get(url, {"category": self.category.pk})
            self.assertContains(response, "Rice")
            self.assertNotContains(response, "Plain salt")
            self.assertEqual(self.client.get(url, {"category": self.foreign.pk}).status_code, 400)

    def test_product_category_edit_audits_ids_and_checks_business(self):
        self.login(self.manager)
        url = reverse("product-edit", args=[self.inventory.pk, self.product.pk])
        payload = {"name": self.product.name, "base_unit_label": "bag", "expiry_tracking_required": "no"}
        self.assertEqual(self.client.post(url, {**payload, "category": self.foreign.pk}).status_code, 400)
        self.assertEqual(self.client.post(url, {**payload, "category": ""}).status_code, 302)
        event = ProductChangeAuditEvent.objects.get(product=self.product)
        self.assertEqual(event.before["category"], self.category.pk)
        self.assertIsNone(event.after["category"])
