from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.services import receive_manual


class ProductSortingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Sort business")
        cls.manager = get_user_model().objects.create_user(email="sort-manager@example.test")
        role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Sort shelf")
        InventoryAssignment.objects.create(membership=role, inventory=cls.inventory)
        # sku: (name, units received)
        cls.stock = {"S-1": ("charlie", 5), "S-2": ("Alpha", 9), "S-3": ("bravo", 5), "S-4": ("delta", 0)}
        for sku, (name, _) in cls.stock.items():
            product = Product.objects.create(business=cls.business, sku=sku, name=name, base_unit_label="each",
                                             expiry_tracking_required=False)
            InventoryProduct.objects.create(inventory=cls.inventory, product=product)

    def setUp(self):
        for sku, (_, units) in self.stock.items():
            if units:
                receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                               product_id=Product.objects.get(sku=sku).pk, request_token=uuid4(),
                               quantity_units=units, expiry_date=None)
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.url = reverse("inventory-products", args=[self.inventory.pk])

    def skus(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return [link.product.sku for link in response.context["product_links"]]

    def test_default_order_is_sku(self):
        self.assertEqual(self.skus(), ["S-1", "S-2", "S-3", "S-4"])

    def test_sort_by_name_case_insensitive_both_directions(self):
        self.assertEqual(self.skus(sort="name"), ["S-2", "S-3", "S-1", "S-4"])
        self.assertEqual(self.skus(sort="-name"), ["S-4", "S-1", "S-3", "S-2"])

    def test_sort_by_available_with_stable_ties(self):
        # S-1 and S-3 both have 5 available; ties stay in SKU order in both directions.
        self.assertEqual(self.skus(sort="available"), ["S-4", "S-1", "S-3", "S-2"])
        self.assertEqual(self.skus(sort="-available"), ["S-2", "S-1", "S-3", "S-4"])

    def test_sort_by_reorder_status(self):
        statuses = {"S-1": "above", "S-2": "unavailable", "S-3": "attention", "S-4": "above"}
        with patch("catalogue.views._reorder_status", side_effect=lambda link: statuses[link.product.sku]):
            self.assertEqual(self.skus(sort="status"), ["S-3", "S-1", "S-4", "S-2"])
            self.assertEqual(self.skus(sort="-status"), ["S-2", "S-1", "S-4", "S-3"])
            # Combined with the reorder filter.
            self.assertEqual(self.skus(sort="-name", reorder="above"), ["S-4", "S-1"])

    def test_sort_combines_with_search(self):
        self.assertEqual(self.skus(q="a", sort="-name"), ["S-4", "S-1", "S-3", "S-2"])
        self.assertEqual(self.skus(q="ha", sort="name"), ["S-2", "S-1"])

    def test_pagination_keeps_sort_and_never_overlaps(self):
        for index in range(30):
            product = Product.objects.create(business=self.business, sku=f"P-{index:02}", name="same name",
                                             base_unit_label="each", expiry_tracking_required=False)
            InventoryProduct.objects.create(inventory=self.inventory, product=product)
        first = self.client.get(self.url, {"sort": "name"})
        second = self.client.get(self.url, {"sort": "name", "page": 2})
        page_one = [link.product.sku for link in first.context["product_links"]]
        page_two = [link.product.sku for link in second.context["product_links"]]
        self.assertEqual(len(page_one) + len(page_two), 34)
        self.assertFalse(set(page_one) & set(page_two))
        self.assertContains(first, "?sort=name&amp;page=2")

    def test_headers_link_sorting_and_keep_filters(self):
        response = self.client.get(self.url, {"q": "a", "sort": "name", "page": 1})
        self.assertContains(response, 'aria-sort="ascending"', count=1)
        self.assertContains(response, 'href="?q=a&amp;sort=-name"')
        self.assertContains(response, 'href="?q=a&amp;sort=available"')
        self.assertContains(response, '<label for="id_sort">Sort by</label>', html=True)

    def test_unknown_sort_is_rejected(self):
        self.assertEqual(self.client.get(self.url, {"sort": "price"}).status_code, 400)

    def test_adjust_form_labels_counted_quantity(self):
        product = Product.objects.get(sku="S-1")
        response = self.client.get(reverse("adjust-stock", args=[self.inventory.pk, product.pk]))
        self.assertContains(response, '<label class="visually-hidden" for="id_batches-0-counted_quantity_units">'
                                      'Observed units for batch 1</label>', html=True)
