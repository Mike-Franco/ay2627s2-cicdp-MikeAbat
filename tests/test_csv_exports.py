import csv
import io
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.services import issue_stock, receive_manual


class CsvExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        business = Business.objects.create(name="Export business")
        other = Business.objects.create(name="Another business")
        cls.shelf = Inventory.objects.create(business=business, name="Visible shelf")
        cls.hidden = Inventory.objects.create(business=business, name="Unassigned shelf")
        cls.foreign = Inventory.objects.create(business=other, name="Foreign shelf")
        cls.product = Product.objects.create(
            business=business, sku="=SUM(1,2)", name="+Product, with notation",
            base_unit_label="@each", expiry_tracking_required=False,
        )
        foreign_product = Product.objects.create(business=other, sku="OTHER", name="Foreign product")
        InventoryProduct.objects.create(inventory=cls.shelf, product=cls.product)
        InventoryProduct.objects.create(inventory=cls.hidden, product=cls.product)
        InventoryProduct.objects.create(inventory=cls.foreign, product=foreign_product)
        cls.other_product_id = foreign_product.pk
        for role, shelves, label in (
            ("manager", (cls.shelf, cls.hidden), "manager"),
            ("staff", (cls.shelf,), "staff"),
            ("manager", (cls.foreign,), "outsider"),
        ):
            user = get_user_model().objects.create_user(email=f"export-{label}@example.test")
            setattr(cls, label, user)
            member = BusinessMembership.objects.create(business=shelves[0].business, user=user, role=role)
            for shelf in shelves:
                InventoryAssignment.objects.create(membership=member, inventory=shelf)

    def setUp(self):
        self.stock_url = reverse("export-inventory-stock", args=[self.shelf.pk])
        self.history_url = reverse("export-stock-history", args=[self.shelf.pk, self.product.pk])

    def login(self, actor):
        self.client.force_login(actor)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def csv_rows(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        return list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode("utf-8"))))

    def receive(self, inventory, units, expiry=None):
        receive_manual(
            user_id=self.manager.pk, inventory_id=inventory.pk, product_id=self.product.pk,
            request_token=uuid4(), quantity_units=units, expiry_date=expiry,
        )

    def test_stock_export_uses_expiry_aware_balances_and_escapes_metadata(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.receive(self.shelf, 3, tomorrow)
        self.receive(self.shelf, 7)
        self.receive(self.hidden, 20)
        self.login(self.staff)
        extra = Product.objects.create(business=self.shelf.business, sku="ZZZ", name="-empty")
        InventoryProduct.objects.create(inventory=self.shelf, product=extra)
        with patch("catalogue.views.timezone.localdate", return_value=tomorrow):
            rows = self.csv_rows(self.client.get(self.stock_url))
        self.assertEqual(rows[1:], [
            ["'=SUM(1,2)", "'+Product, with notation", "'@each", "10", "3", "7"],
            ["ZZZ", "'-empty", "", "0", "0", "0"],
        ])

    def test_history_is_streamed_in_order_for_the_selected_link(self):
        self.receive(self.shelf, 10)
        self.receive(self.hidden, 50)
        issue_stock(user_id=self.staff.pk, inventory_id=self.shelf.pk,
                    product_id=self.product.pk, quantity_units=2)
        self.login(self.manager)
        rows = self.csv_rows(self.client.get(self.history_url))
        self.assertEqual([row[1:5] for row in rows[1:]], [
            ["issue", self.staff.email, "10", "8"],
            ["receipt", self.manager.email, "0", "10"],
        ])
        self.assertTrue(rows[1][0].endswith("+08:00"))

    def test_access_and_method_checks(self):
        for url in (self.stock_url, self.history_url):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.login(self.staff)
        for url in (
            reverse("export-inventory-stock", args=[self.hidden.pk]),
            reverse("export-stock-history", args=[self.hidden.pk, self.product.pk]),
            reverse("export-stock-history", args=[self.shelf.pk, self.other_product_id]),
        ):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.head(self.stock_url).status_code, 405)
        self.assertEqual(self.client.post(self.history_url).status_code, 405)
        self.assertEqual(len(self.csv_rows(self.client.get(self.history_url))), 1)
        self.login(self.outsider)
        for url in (self.stock_url, self.history_url):
            self.assertEqual(self.client.get(url).status_code, 404)
