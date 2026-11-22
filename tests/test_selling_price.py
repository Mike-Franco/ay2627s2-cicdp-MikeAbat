from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product, ProductChangeAuditEvent
from catalogue.templatetags.tory_format import sgd
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.services import receive_manual


class SellingPriceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Price business")
        cls.manager = users.create_user(email="price-manager@example.test")
        cls.staff = users.create_user(email="price-staff@example.test")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.shop = Inventory.objects.create(business=cls.business, name="Shop")
        cls.kiosk = Inventory.objects.create(business=cls.business, name="Kiosk")
        for inventory in (cls.shop, cls.kiosk):
            InventoryAssignment.objects.create(membership=manager_role, inventory=inventory)
        InventoryAssignment.objects.create(membership=staff_role, inventory=cls.shop)
        cls.product = Product.objects.create(business=cls.business, sku="TEA", name="Black tea", base_unit_label="box",
                                             expiry_tracking_required=False)
        cls.unpriced = Product.objects.create(business=cls.business, sku="MUG", name="Mug", base_unit_label="each",
                                              expiry_tracking_required=False)
        for inventory in (cls.shop, cls.kiosk):
            InventoryProduct.objects.create(inventory=inventory, product=cls.product)
        InventoryProduct.objects.create(inventory=cls.shop, product=cls.unpriced)
        other = Business.objects.create(name="Other price business")
        cls.outsider = users.create_user(email="price-outsider@example.test")
        outsider_role = BusinessMembership.objects.create(business=other, user=cls.outsider, role="manager")
        InventoryAssignment.objects.create(membership=outsider_role,
                                           inventory=Inventory.objects.create(business=other, name="Elsewhere"))

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def url(self, inventory=None):
        return reverse("selling-price", args=[(inventory or self.shop).pk, self.product.pk])

    def price(self, inventory):
        return InventoryProduct.objects.get(inventory=inventory, product=self.product).selling_price

    def test_manager_sets_price_per_inventory_with_audit(self):
        self.login(self.manager)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        response = self.client.post(self.url(), {"selling_price": "4.50"})
        self.assertRedirects(response, reverse("product-stock", args=[self.shop.pk, self.product.pk]),
                             fetch_redirect_response=False)
        self.client.post(self.url(self.kiosk), {"selling_price": "5.25"})
        self.assertEqual((self.price(self.shop), self.price(self.kiosk)), (Decimal("4.50"), Decimal("5.25")))
        event = ProductChangeAuditEvent.objects.get(inventory=self.shop)
        self.assertEqual((event.actor, event.action, event.product), (self.manager, "edit", self.product))
        self.assertEqual((event.before, event.after), ({"selling_price": None}, {"selling_price": "4.50"}))

    def test_unchanged_price_writes_no_audit_and_blank_clears(self):
        self.login(self.manager)
        self.client.post(self.url(), {"selling_price": "4.50"})
        self.client.post(self.url(), {"selling_price": "4.5"})
        self.assertEqual(ProductChangeAuditEvent.objects.count(), 1)
        self.client.post(self.url(), {"selling_price": ""})
        self.assertIsNone(self.price(self.shop))
        self.assertEqual(ProductChangeAuditEvent.objects.latest("pk").after, {"selling_price": None})

    def test_rejects_negative_and_too_precise_prices(self):
        self.login(self.manager)
        for value in ("-1", "1.005", "abc"):
            with self.subTest(value=value):
                self.assertEqual(self.client.post(self.url(), {"selling_price": value}).status_code, 400)
        self.assertIsNone(self.price(self.shop))
        self.assertFalse(ProductChangeAuditEvent.objects.exists())

    def test_staff_can_view_but_not_edit(self):
        InventoryProduct.objects.filter(inventory=self.shop, product=self.product).update(selling_price=Decimal("4.50"))
        self.login(self.staff)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(self.client.post(self.url(), {"selling_price": "1"}).status_code, 404)
        self.assertEqual(self.price(self.shop), Decimal("4.50"))
        stock = self.client.get(reverse("product-stock", args=[self.shop.pk, self.product.pk]))
        self.assertContains(stock, "S$4.50")
        self.assertNotContains(stock, self.url())
        products = self.client.get(reverse("inventory-products", args=[self.shop.pk]))
        self.assertContains(products, "S$4.50")

    def test_other_business_and_unassigned_inventory_get_404(self):
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.login(self.staff)
        self.assertEqual(self.client.get(self.url(self.kiosk)).status_code, 404)

    def test_manager_sees_edit_link_on_stock_page(self):
        self.login(self.manager)
        stock = self.client.get(reverse("product-stock", args=[self.shop.pk, self.product.pk]))
        self.assertContains(stock, f'href="{self.url()}"')
        self.assertContains(stock, "—")

    def test_insights_stock_value_uses_available_units_and_lists_unpriced(self):
        InventoryProduct.objects.filter(inventory=self.shop, product=self.product).update(selling_price=Decimal("2.50"))
        InventoryProduct.objects.filter(inventory=self.kiosk, product=self.product).update(selling_price=Decimal("99"))
        receive_manual(user_id=self.manager.pk, inventory_id=self.shop.pk, product_id=self.product.pk,
                       request_token=uuid4(), quantity_units=4, expiry_date=None)
        self.login(self.manager)
        response = self.client.get(reverse("inventory-insights", args=[self.shop.pk]))
        self.assertEqual(response.context["stock_value"], Decimal("10.00"))
        self.assertContains(response, "S$10.00")
        self.assertContains(response, "across 1 priced product.")
        self.assertContains(response, "no selling price set: MUG.")

    def test_sgd_filter(self):
        self.assertEqual(sgd(Decimal("1234.5")), "S$1,234.50")
        self.assertEqual(sgd(None), "—")
        self.assertEqual(sgd("0"), "S$0.00")
