"""TORY-63: Catalogue and Activity log follow the inventory selected in the sidebar."""

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from inventory_access.selection import SESSION_KEY
from receiving.services import receive_manual


class ScopedManageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Scope business")
        cls.manager = users.create_user(email="scope-manager@example.test")
        cls.staff = users.create_user(email="scope-staff@example.test")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.grocery = Inventory.objects.create(business=cls.business, name="Grocery")
        cls.pharmacy = Inventory.objects.create(business=cls.business, name="Pharmacy")
        cls.vault = Inventory.objects.create(business=cls.business, name="Vault")
        for inventory in (cls.grocery, cls.pharmacy, cls.vault):
            InventoryAssignment.objects.create(membership=manager_role, inventory=inventory)
        for inventory in (cls.grocery, cls.pharmacy):  # Staff are never assigned to the vault.
            InventoryAssignment.objects.create(membership=staff_role, inventory=inventory)
        cls.products = {}
        for inventory, sku, name in ((cls.grocery, "GR-01", "Oat Milk"), (cls.pharmacy, "PH-01", "Saline Spray"),
                                     (cls.vault, "VA-01", "Gold Bar")):
            product = Product.objects.create(business=cls.business, sku=sku, name=name, base_unit_label="each",
                                             expiry_tracking_required=False)
            InventoryProduct.objects.create(inventory=inventory, product=product)
            cls.products[sku] = (inventory, product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def select(self, inventory):
        """Open the inventory's products page, as the sidebar switcher does."""
        self.assertEqual(self.client.get(reverse("inventory-products", args=[inventory.pk])).status_code, 200)

    def skus(self, response):
        self.assertEqual(response.status_code, 200)
        return sorted(row.product.sku for row in response.context["product_links"])

    def test_opening_an_inventory_selects_it_for_the_session(self):
        self.login(self.manager)
        self.select(self.pharmacy)
        self.assertEqual(self.client.session[SESSION_KEY], self.pharmacy.pk)
        sidebar = self.client.get(reverse("help")).content.decode()
        sidebar = sidebar[sidebar.index('id="workspace-sidebar"'):sidebar.index("</aside>")]
        self.assertIn('<span class="switch-name">Pharmacy</span>', sidebar)
        self.assertIn(reverse("inventory-insights", args=[self.pharmacy.pk]), sidebar)

    def test_catalogue_defaults_to_the_current_inventory(self):
        self.login(self.manager)
        self.assertEqual(self.skus(self.client.get(reverse("product-catalogue"))), ["GR-01", "PH-01", "VA-01"])
        self.select(self.grocery)
        response = self.client.get(reverse("product-catalogue"))
        self.assertEqual(self.skus(response), ["GR-01"])
        self.assertContains(response, '<span class="scopechip">')
        self.assertContains(response, "products from your current inventory")
        self.assertContains(response, '<a href="?scope=all">Show all inventories (3)</a>', html=True)
        # The toolbar keeps the scope when it is submitted.
        self.assertContains(response, f'<option value="{self.grocery.pk}" selected>Grocery</option>', html=True)

    def test_scope_all_widens_and_an_explicit_filter_wins(self):
        self.login(self.manager)
        self.select(self.grocery)
        response = self.client.get(reverse("product-catalogue"), {"scope": "all"})
        self.assertEqual(self.skus(response), ["GR-01", "PH-01", "VA-01"])
        self.assertContains(response, "Show only Grocery")
        self.assertEqual(self.skus(self.client.get(reverse("product-catalogue"), {"inventory": ""})),
                         ["GR-01", "PH-01", "VA-01"])
        self.assertEqual(self.skus(self.client.get(reverse("product-catalogue"), {"inventory": self.pharmacy.pk})),
                         ["PH-01"])

    def test_staff_can_never_widen_past_their_assigned_inventories(self):
        self.login(self.staff)
        self.select(self.grocery)
        self.assertEqual(self.skus(self.client.get(reverse("product-catalogue"))), ["GR-01"])
        self.assertEqual(self.skus(self.client.get(reverse("product-catalogue"), {"scope": "all"})), ["GR-01", "PH-01"])
        response = self.client.get(reverse("product-catalogue"), {"scope": "all"})
        self.assertNotContains(response, "Gold Bar")
        self.assertEqual(self.client.get(reverse("product-catalogue"), {"inventory": self.vault.pk}).status_code, 400)
        # A remembered id the user can't see (e.g. after unassignment) is ignored.
        session = self.client.session
        session[SESSION_KEY] = self.vault.pk
        session.save()
        self.assertEqual(self.skus(self.client.get(reverse("product-catalogue"))), ["GR-01", "PH-01"])
        self.assertNotIn("Vault", self.client.get(reverse("product-catalogue")).content.decode())

    def test_activity_log_defaults_to_the_current_inventory(self):
        for sku in ("GR-01", "PH-01"):
            inventory, product = self.products[sku]
            receive_manual(user_id=self.manager.pk, inventory_id=inventory.pk, product_id=product.pk,
                           request_token=uuid4(), quantity_units=3, expiry_date=None)
        self.login(self.manager)
        url = reverse("activity-log", args=[self.business.pk])
        everything = self.client.get(url)
        self.assertEqual(everything.context["page"].paginator.count, 2)
        self.select(self.pharmacy)
        response = self.client.get(url)
        self.assertEqual([row["inventory"].name for row in response.context["rows"]], ["Pharmacy"])
        self.assertContains(response, "activity from your current inventory")
        self.assertContains(response, "Show all inventories (2)")
        self.assertEqual(self.client.get(url, {"scope": "all"}).context["page"].paginator.count, 2)
        self.assertEqual(self.client.get(url, {"inventory": ""}).context["page"].paginator.count, 2)
        csv = self.client.get(reverse("activity-log-csv", args=[self.business.pk]))
        self.assertEqual(b"".join(csv.streaming_content).decode().count("Pharmacy"), 1)
