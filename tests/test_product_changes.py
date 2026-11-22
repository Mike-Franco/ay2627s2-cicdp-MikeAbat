from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product, ProductChangeAuditEvent
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.services import receive_manual


class ProductChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        business = Business.objects.create(name="Product business")
        outside = Business.objects.create(name="Other business")
        cls.shelf = Inventory.objects.create(business=business, name="First shelf")
        cls.second = Inventory.objects.create(business=business, name="Second shelf")
        cls.private = Inventory.objects.create(business=business, name="Private shelf")
        cls.foreign = Inventory.objects.create(business=outside, name="Foreign shelf")
        for role, shelves, label in (
            ("manager", (cls.shelf, cls.second), "manager"),
            ("staff", (cls.shelf,), "staff"),
            ("manager", (cls.foreign,), "outsider"),
        ):
            user = get_user_model().objects.create_user(email=f"product-{label}@example.test")
            setattr(cls, label, user)
            member = BusinessMembership.objects.create(business=shelves[0].business, user=user, role=role)
            for shelf in shelves:
                InventoryAssignment.objects.create(membership=member, inventory=shelf)
        cls.product = Product.objects.create(
            business=business, sku="ORIGINAL", name="Original", base_unit_label="each", expiry_tracking_required=False,
        )
        InventoryProduct.objects.create(inventory=cls.shelf, product=cls.product)
        InventoryProduct.objects.create(inventory=cls.second, product=cls.product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def setUp(self):
        self.create_url = reverse("product-create", args=[self.shelf.pk])
        self.edit_url = reverse("product-edit", args=[self.shelf.pk, self.product.pk])
        self.payload = dict(sku="NEW", name="New product", base_unit_label="bottle",
                            expiry_tracking_required="no", lead_time_days="7", safety_stock_units="3",
                            inventories=[self.shelf.pk, self.second.pk])

    def test_create_links_audits_and_can_receive_immediately(self):
        self.login(self.manager)
        self.assertContains(self.client.get(reverse("product-catalogue")), self.create_url)
        self.assertContains(self.client.get(reverse("inventory-products", args=[self.shelf.pk])), self.create_url)
        response = self.client.post(self.create_url, self.payload)
        product = Product.objects.get(sku="NEW")
        self.assertRedirects(response, reverse("product-stock", args=[self.shelf.pk, product.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(set(product.inventory_links.values_list("inventory_id", flat=True)),
                         {self.shelf.pk, self.second.pk})
        audit = ProductChangeAuditEvent.objects.get(product=product)
        self.assertEqual((audit.actor, audit.action, audit.before), (self.manager, "create", None))
        self.assertEqual(audit.after["base_unit_label"], "bottle")
        self.assertFalse(audit.after["expiry_tracking_required"])
        batch, _ = receive_manual(user_id=self.manager.pk, inventory_id=self.second.pk, product_id=product.pk,
                                  request_token=uuid4(), quantity_units=2, expiry_date=None)
        self.assertEqual((batch.quantity_units, batch.unit_label_snapshot), (2, "bottle"))

    def test_edit_audits_changed_settings_and_keeps_sku(self):
        self.login(self.manager)
        receive_manual(user_id=self.manager.pk, inventory_id=self.shelf.pk, product_id=self.product.pk,
                       request_token=uuid4(), quantity_units=1, expiry_date=None)
        self.assertTrue(self.client.get(self.edit_url).context["form"].fields["sku"].disabled)
        self.assertEqual(self.client.post(self.edit_url, self.payload).status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual((self.product.name, self.product.sku, self.product.lead_time_days),
                         ("New product", "ORIGINAL", 7))
        audit = ProductChangeAuditEvent.objects.get(product=self.product)
        self.assertEqual((audit.action, audit.before["name"], audit.after["name"]), ("edit", "Original", "New product"))
        self.assertEqual(self.client.post(self.edit_url, self.payload).status_code, 302)
        self.assertEqual(ProductChangeAuditEvent.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductChangeAuditEvent.objects.filter(pk=audit.pk).update(after={})

    def test_staff_other_business_and_partial_manager_are_denied(self):
        for user in (self.staff, self.outsider):
            self.login(user)
            for url in (self.create_url, self.edit_url):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, self.payload).status_code, 404)
            self.assertNotContains(self.client.get(reverse("product-catalogue")), self.create_url)
        self.login(self.manager)
        for shelf in (self.private, self.foreign):
            self.assertEqual(self.client.get(reverse("product-create", args=[shelf.pk])).status_code, 404)
        InventoryAssignment.objects.filter(inventory=self.second).update(is_active=False)
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(self.client.post(self.edit_url, self.payload).status_code, 404)
        self.assertFalse(ProductChangeAuditEvent.objects.exists())

    def test_inline_validation_for_duplicate_and_invalid_fields(self):
        self.login(self.manager)
        response = self.client.post(self.create_url, self.payload | {
            "sku": " original ", "base_unit_label": " ", "expiry_tracking_required": "",
            "lead_time_days": "366", "safety_stock_units": "-1", "inventories": [self.foreign.pk],
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.context["form"].errors),
                         {"sku", "base_unit_label", "expiry_tracking_required", "lead_time_days",
                          "safety_stock_units", "inventories"})
        self.assertContains(response, "A product with this SKU already exists", status_code=400)
        self.assertEqual(Product.objects.count(), 1)
        self.assertFalse(ProductChangeAuditEvent.objects.exists())

    def test_csrf_and_audit_failure_roll_back_links_and_product(self):
        self.client = Client(enforce_csrf_checks=True)
        self.login(self.manager)
        page = self.client.get(self.create_url)
        self.assertContains(page, "csrfmiddlewaretoken")
        self.assertEqual(self.client.post(self.create_url, self.payload).status_code, 403)
        with patch("catalogue.product_changes.ProductChangeAuditEvent.objects.create",
                   side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesMessage(RuntimeError, "audit unavailable"):
                self.client.post(self.create_url, self.payload, HTTP_X_CSRFTOKEN=page.cookies["csrftoken"].value)
        self.assertFalse(Product.objects.filter(sku="NEW").exists())
        self.assertEqual(InventoryProduct.objects.count(), 2)
        self.assertFalse(ProductChangeAuditEvent.objects.exists())
