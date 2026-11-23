"""TORY-62: v1.2 UI foundation — pagination component, page header breadcrumbs, logo and theme."""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import Context, Template, TemplateSyntaxError
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from catalogue.pagination import SMALL_PER_PAGE_CHOICES, clamp_per_page, paginate
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


class PaginateTests(SimpleTestCase):
    rows = list(range(142))

    def page(self, query="", **options):
        return paginate(RequestFactory().get("/list/" + query), self.rows, **options)

    def test_clamps_per_page_to_the_allowed_set(self):
        for value, expected in (("10", 10), ("50", 50), ("100", 100), ("30", 25), ("1000", 100),
                                ("1", 10), ("-5", 10), ("abc", 25), ("", 25), (None, 25)):
            with self.subTest(value=value):
                self.assertEqual(clamp_per_page(value, default=25), expected)
        self.assertEqual(clamp_per_page("7", default=5, choices=SMALL_PER_PAGE_CHOICES), 5)
        self.assertEqual(self.page("?per_page=9999").per_page, 100)
        self.assertEqual(len(self.page("?per_page=9999").object_list), 100)

    def test_rejects_a_default_outside_the_choices(self):
        with self.assertRaises(ValueError):
            self.page(default=7)

    def test_range_and_links_keep_other_query_parameters(self):
        page = self.page("?q=tea&sort=-name&page=2&per_page=25")
        self.assertEqual((page.start_index(), page.end_index(), page.paginator.count), (26, 50, 142))
        self.assertEqual(page.previous_url, "?q=tea&sort=-name&page=1")
        self.assertEqual(page.next_url, "?q=tea&sort=-name&page=3")
        self.assertEqual(page.keep, [("q", "tea"), ("sort", "-name")])
        current = [link for link in page.links if link.get("current")]
        self.assertEqual([link["number"] for link in current], [2])

    def test_non_default_size_is_carried_in_page_links(self):
        page = self.page("?per_page=50&page=2")
        self.assertEqual(page.next_url, "?per_page=50&page=3")

    def test_out_of_range_and_junk_pages_fall_back(self):
        self.assertEqual(self.page("?page=999").number, 6)
        self.assertEqual(self.page("?page=0").number, 6)
        self.assertEqual(self.page("?page=abc").number, 1)
        self.assertIsNone(self.page("?page=999").next_url)
        self.assertIsNone(self.page().previous_url)

    def test_long_ranges_are_elided(self):
        page = paginate(RequestFactory().get("/", {"page": "10", "per_page": "10"}), list(range(500)))
        numbers = [link.get("number", "…") for link in page.links]
        self.assertEqual(numbers, [1, "…", 9, 10, 11, "…", 50])

    def test_prefixed_tables_page_independently(self):
        request = RequestFactory().get("/", {"supply_page": "2", "page": "3", "supply_per_page": "5"})
        page = paginate(request, self.rows, prefix="supply_", default=5, choices=SMALL_PER_PAGE_CHOICES,
                        fragment="supply")
        self.assertEqual((page.number, page.per_page), (2, 5))
        self.assertEqual(page.next_url, "?supply_page=3&page=3#supply")  # the default size stays out of links
        self.assertEqual(page.keep, [("page", "3")])
        self.assertTrue(page.touched)

    def test_component_renders_range_size_select_and_current_page(self):
        request = RequestFactory().get("/", {"q": "tea", "page": "2"})
        html = Template('{% include "includes/pagination.html" %}').render(Context({"page": paginate(request, self.rows)}))
        self.assertIn("Showing <strong>26–50</strong> of 142", html)
        self.assertIn('<select class="sel sm" name="per_page">', html)
        self.assertIn('<option value="25" selected>25</option>', html)
        self.assertIn('<input type="hidden" name="q" value="tea">', html)
        self.assertNotIn('name="page"', html)
        self.assertIn('aria-current="page" aria-label="Page 2">2</a>', html)
        self.assertIn('rel="prev"', html)

    def test_component_hides_for_an_empty_table(self):
        html = Template('{% include "includes/pagination.html" %}').render(
            Context({"page": paginate(RequestFactory().get("/"), [])}))
        self.assertEqual(html.strip(), "")


class PageHeaderTagTests(SimpleTestCase):
    def test_actions_slot_and_explicit_breadcrumbs(self):
        html = Template(
            '{% page_header %}Catalogue{% header_actions %}<a class="btn" href="/new/">New</a>{% endpage_header %}'
        ).render(Context({"breadcrumbs": [("Dashboard", "/dashboard/"), ("Catalogue", None)]}))
        self.assertIn("<h1>Catalogue</h1>", html)
        self.assertIn('<div class="ph-actions"><a class="btn" href="/new/">New</a></div>', html)
        crumbs = re.search(r'<nav class="crumbs" aria-label="Breadcrumb">.*?</nav>', html, re.S).group(0)
        self.assertIn('<a href="/dashboard/">Dashboard</a>', crumbs)
        self.assertIn('<span aria-current="page">Catalogue</span>', crumbs)
        # The breadcrumb sits under the title row.
        self.assertLess(html.index("<h1>"), html.index('aria-label="Breadcrumb"'))

    def test_default_trail_uses_the_crumb_argument(self):
        html = Template('{% page_header crumb="Import CSV" %}Import stock CSV{% endpage_header %}').render(Context({}))
        self.assertIn('<a href="/dashboard/">Dashboard</a>', html)
        self.assertIn('<span aria-current="page">Import CSV</span>', html)
        self.assertNotIn("ph-actions", html)

    def test_rejects_unknown_arguments(self):
        with self.assertRaises(TemplateSyntaxError):
            Template("{% page_header title=x %}T{% endpage_header %}")


class ShellTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Shell business")
        cls.manager = users.create_user(email="shell-manager@example.test")
        membership = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Grocery")
        InventoryAssignment.objects.create(membership=membership, inventory=cls.inventory)
        product = Product.objects.create(business=cls.business, sku="GR-01", name="Oat Milk",
                                         base_unit_label="carton", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=product)

    def setUp(self):
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def crumbs(self, response):
        self.assertEqual(response.status_code, 200)
        return response.context["breadcrumbs"]

    def test_views_pass_breadcrumbs_in_context(self):
        home = reverse("home")
        self.assertEqual(self.crumbs(self.client.get(reverse("product-catalogue"))),
                         [("Dashboard", home), ("Catalogue", None)])
        self.assertEqual(self.crumbs(self.client.get(reverse("activity-log", args=[self.business.pk]))),
                         [("Dashboard", home), ("Shell business", None), ("Activity log", None)])
        self.assertEqual(self.crumbs(self.client.get(reverse("category-list", args=[self.business.pk]))),
                         [("Dashboard", home), ("Catalogue", reverse("product-catalogue")), ("Categories", None)])

    def test_every_authenticated_page_has_one_header_and_breadcrumb(self):
        for url in (reverse("home"), reverse("inventory-list"), reverse("product-catalogue"),
                    reverse("inventory-products", args=[self.inventory.pk]), reverse("help"), reverse("account")):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertEqual(html.count('<header class="ph">'), 1)
                self.assertEqual(html.count("<h1"), 1)
                self.assertEqual(html.count('aria-label="Breadcrumb"'), 1)

    def test_logo_favicon_and_theme_toggle(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('<svg class="logo-mark" viewBox="0 0 37.04 35.80"', html)
        self.assertIn('rel="icon" href="/static/tory/favicon.svg" type="image/svg+xml"', html)
        self.assertIn('href="/static/tory/favicon-32.png" sizes="32x32"', html)
        sidebar = html[html.index('id="workspace-sidebar"'):html.index("</aside>")]
        menu = sidebar[sidebar.index('class="profile-menu"'):]
        for choice in ("light", "dark", "system"):
            self.assertIn(f'data-set-theme="{choice}"', menu)

    def test_login_page_shows_the_logo(self):
        self.client.logout()
        html = self.client.get(reverse("login")).content.decode()
        card = html[html.index('class="auth-card"'):]
        self.assertIn('class="logo-mark"', html[html.index('class="auth-wrap"'):])
        self.assertIn("<h1>Sign in</h1>", card)
        self.assertIn('href="/static/tory/favicon.svg"', html)


class TokenTests(SimpleTestCase):
    def test_tokens_cover_light_dark_and_system_preference(self):
        css = Path(settings.BASE_DIR, "static/tory/tokens.css").read_text(encoding="utf-8")
        self.assertIn("--accent:#5B5BD6", css)
        self.assertIn('[data-theme="dark"]', css)
        self.assertIn("@media (prefers-color-scheme: dark)", css)
        self.assertIn("--mk-t:#8E8FF5;--mk-l:#5B5BD6;--mk-r:#B9BAFB", css)
        app = Path(settings.BASE_DIR, "static/tory/app.css").read_text(encoding="utf-8")
        self.assertNotRegex(app + css, r"word-spacing:(?!normal)")
        theme = Path(settings.BASE_DIR, "static/tory/theme.js").read_text(encoding="utf-8")
        self.assertEqual(theme.count("try {"), 2)
