from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.csv_import import import_stock_csv
from receiving.models import ReceiptAuditEvent, StockOut
from receiving.services import receive_manual


class CsvImportTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Template business")
        cls.manager = users.create_user(email="template-manager@example.test")
        cls.staff = users.create_user(email="template-staff@example.test")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Template shelf")
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=staff_role, inventory=cls.inventory)

        def product(sku, **fields):
            created = Product.objects.create(business=cls.business, sku=sku, name=f"Item {sku}",
                                             base_unit_label="each", **fields)
            InventoryProduct.objects.create(inventory=cls.inventory, product=created)
            return created

        product("=CMD", expiry_tracking_required=False)        # unsafe in a spreadsheet: never an example
        product("A-TRACKED", expiry_tracking_required=True)    # CSV cannot receive expiry-tracked stock
        cls.plain = product("B-PLAIN", expiry_tracking_required=False)
        cls.stocked = product("C-STOCKED", expiry_tracking_required=True)
        product("D-RETIRED", expiry_tracking_required=False, is_active=False)

        other = Business.objects.create(name="Other template business")
        cls.outsider = users.create_user(email="template-outsider@example.test")
        outsider_role = BusinessMembership.objects.create(business=other, user=cls.outsider, role="manager")
        InventoryAssignment.objects.create(membership=outsider_role,
                                           inventory=Inventory.objects.create(business=other, name="Elsewhere"))

    def setUp(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.stocked.pk,
                       request_token=uuid4(), quantity_units=5,
                       expiry_date=timezone.localdate() + timezone.timedelta(days=30))
        self.url = reverse("import-stock-csv-template", args=[self.inventory.pk])

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def test_manager_downloads_template_from_real_skus(self):
        self.login(self.manager)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(f'filename="tory-import-template-{self.inventory.pk}.csv"', response["Content-Disposition"])
        # B-PLAIN is the first receivable SKU; C-STOCKED is the stocked one to issue from.
        self.assertEqual(response.content.decode(), "sku,change\nB-PLAIN,10\nC-STOCKED,-1\n")

    def test_downloaded_template_imports_unchanged(self):
        self.login(self.manager)
        raw = self.client.get(self.url).content
        record = import_stock_csv(user_id=self.manager.pk, inventory_id=self.inventory.pk, raw_bytes=raw)
        self.assertIsNotNone(record.pk)
        self.assertTrue(ReceiptAuditEvent.objects.filter(product=self.plain, quantity_change_units=10).exists())
        self.assertTrue(StockOut.objects.filter(import_record=record).exists())

    def test_import_page_links_template_and_shows_examples(self):
        self.login(self.manager)
        response = self.client.get(reverse("import-stock-csv", args=[self.inventory.pk]))
        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, "Download template")
        self.assertContains(response, "<td><code>B-PLAIN</code></td><td><code>10</code></td>", html=True)
        self.assertContains(response, "<td><code>C-STOCKED</code></td><td><code>-1</code></td>", html=True)
        self.assertNotContains(response, "=CMD")

    def test_staff_other_business_and_anonymous_are_denied(self):
        for user in (self.staff, self.outsider):
            self.login(user)
            self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_falls_back_to_placeholders_without_products(self):
        empty = Inventory.objects.create(business=self.business, name="Empty template shelf")
        InventoryAssignment.objects.create(
            membership=BusinessMembership.objects.get(user=self.manager), inventory=empty)
        self.login(self.manager)
        response = self.client.get(reverse("import-stock-csv-template", args=[empty.pk]))
        self.assertEqual(response.content.decode(), "sku,change\nSKU-1,10\nSKU-2,-1\n")
