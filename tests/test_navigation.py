"""TORY-52: sidebar navigation and breadcrumbs for Managers and Staff."""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


class NavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Nav business")
        cls.manager = users.create_user(email="nav-manager@example.test")
        cls.staff = users.create_user(email="nav-staff@example.test")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Front shelf")
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=staff_role, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="NAV-1", name="Gauze",
                                             base_unit_label="pack", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def sidebar(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        return html[html.index('id="workspace-sidebar"'):html.index("</aside>")]

    def group(self, sidebar):
        match = re.search(r'<details class="nav-group".*?</details>', sidebar, re.S)
        return match.group(0) if match else ""

    def crumb(self, url):
        html = self.client.get(url).content.decode()
        return re.search(r'<nav class="workspace-crumb".*?</nav>', html, re.S).group(0)

    def protected_pages(self):
        inv, prod = self.inventory.pk, self.product.pk
        return [
            reverse("inventory-list"), reverse("product-catalogue"), reverse("account"),
            reverse("inventory-products", args=[inv]), reverse("inventory-insights", args=[inv]),
            reverse("product-stock", args=[inv, prod]), reverse("stock-history", args=[inv, prod]),
        ]

    def test_dashboard_link_and_logo_reach_dashboard_for_every_role(self):
        home = reverse("home")
        for user in (self.manager, self.staff):
            self.login(user)
            for url in self.protected_pages():
                with self.subTest(user=user.email, url=url):
                    sidebar = self.sidebar(url)
                    self.assertIn(f'<a class="brand" href="{home}"', sidebar)
                    self.assertRegex(sidebar, rf'<a class="sidebar-link [^"]*" href="{home}" ?>.*Dashboard</a>')

    def test_dashboard_link_is_current_on_the_dashboard(self):
        self.login(self.staff)
        sidebar = self.sidebar(reverse("home"))
        self.assertRegex(sidebar, r'class="sidebar-link active" href="/" aria-current="page">.*Dashboard</a>')

    def test_insights_only_appears_inside_the_selected_inventory_group(self):
        insights = reverse("inventory-insights", args=[self.inventory.pk])
        for user in (self.manager, self.staff):
            self.login(user)
            for url in (reverse("home"), reverse("inventory-list"), reverse("product-catalogue")):
                with self.subTest(user=user.email, url=url):
                    sidebar = self.sidebar(url)
                    self.assertNotIn("Insights", sidebar)
                    self.assertEqual(self.group(sidebar), "")
            sidebar = self.sidebar(reverse("inventory-products", args=[self.inventory.pk]))
            group = self.group(sidebar)
            self.assertIn("Front shelf", group)
            self.assertIn(f'href="{insights}"', group)
            self.assertEqual(sidebar.count(f'href="{insights}"'), 1)

    def test_manager_group_has_all_inventory_pages(self):
        self.login(self.manager)
        group = self.group(self.sidebar(reverse("inventory-insights", args=[self.inventory.pk])))
        labels = re.findall(r">([A-Za-z ]+)</a>", group)
        self.assertEqual(labels, ["Products", "Insights", "Import CSV", "Verify demand"])
        self.assertIn('class="sidebar-link active" href="/inventories/%d/insights/" aria-current="page"'
                      % self.inventory.pk, group)
        self.assertIn(reverse("import-stock-csv", args=[self.inventory.pk]), group)
        self.assertIn(reverse("bulk-verify-demand", args=[self.inventory.pk]), group)

    def test_staff_group_hides_manager_only_pages(self):
        self.login(self.staff)
        sidebar = self.sidebar(reverse("inventory-products", args=[self.inventory.pk]))
        labels = re.findall(r">([A-Za-z ]+)</a>", self.group(sidebar))
        self.assertEqual(labels, ["Products", "Insights"])
        self.assertNotIn("Import CSV", sidebar)
        self.assertNotIn("Verify demand", sidebar)
        self.assertNotIn(">TEAM</p>", sidebar)

    def test_all_inventories_link_for_every_role(self):
        for user in (self.manager, self.staff):
            self.login(user)
            self.assertIn(f'href="{reverse("inventory-list")}"', self.sidebar(reverse("home")))

    def test_breadcrumbs_start_with_dashboard(self):
        for user in (self.manager, self.staff):
            self.login(user)
            for url in self.protected_pages():
                with self.subTest(user=user.email, url=url):
                    crumb = self.crumb(url)
                    first = re.search(r"<(a|span)[^>]*>([^<]*)<", crumb)
                    self.assertEqual(first.group(2), "Dashboard")
                    self.assertIn(f'<a href="{reverse("home")}">Dashboard</a>', crumb)

    def test_inventory_pages_show_the_inventory_in_the_breadcrumb(self):
        self.login(self.staff)
        crumb = self.crumb(reverse("stock-history", args=[self.inventory.pk, self.product.pk]))
        self.assertIn(f'<a href="{reverse("inventory-products", args=[self.inventory.pk])}">Front shelf</a>', crumb)
        self.assertIn('aria-current="page">NAV-1 · History<', crumb)

    def test_dashboard_breadcrumb_is_the_current_page(self):
        self.login(self.manager)
        crumb = self.crumb(reverse("home"))
        self.assertIn('<span aria-current="page">Dashboard</span>', crumb)
        self.assertNotIn("<a ", crumb)
