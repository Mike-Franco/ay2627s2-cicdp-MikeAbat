"""TORY-69: one page container everywhere, and the reworked Import CSV, Verify demand, Categories,
Invitations and Products layouts."""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import Category, InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.demand import unreviewed_by_day
from receiving.models import DemandCoverageDay, DemandCoverageEvent, ObservationActivation
from receiving.services import SINGAPORE

STATIC = Path(settings.BASE_DIR, "static", "tory")
TEMPLATES = Path(settings.BASE_DIR, "templates")


class ContainerTests(SimpleTestCase):
    def test_no_page_uses_a_narrow_column(self):
        offenders = [str(path) for path in TEMPLATES.rglob("*.html") if "layout-narrow" in path.read_text("utf-8")]
        self.assertEqual(offenders, [])
        for name in ("app.css", "pages.css", "tokens.css"):
            self.assertNotIn("880px", (STATIC / name).read_text("utf-8"), name)

    def test_one_container_and_field_limits(self):
        app = (STATIC / "app.css").read_text("utf-8")
        self.assertIn(".content{width:100%;max-width:var(--page-max);margin-inline:auto;padding:20px var(--gutter) 40px}", app)
        self.assertIn(".ph-inner{max-width:calc(var(--page-max) - 2 * var(--gutter));margin-inline:auto}", app)
        self.assertIn("--page-max:1600px;--gutter:32px", app)
        self.assertIn(".workspace-main{--gutter:16px}", app)
        self.assertIn(":not([type=file]){max-width:560px}", app)  # every text input and select in a card
        self.assertIn(".content textarea,.content textarea.form-control{max-width:720px}", app)
        self.assertIn("max-width:75ch", app)
        pages = (STATIC / "pages.css").read_text("utf-8")
        self.assertIn(".split{grid-template-columns:repeat(2,minmax(0,1fr))}", pages)
        self.assertIn(".split.split-aside{grid-template-columns:400px minmax(0,1fr)}", pages)
        self.assertIn(".product-filters{display:flex;flex-wrap:wrap;", pages)


class PageLayoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Width business")
        cls.manager = users.create_user(email="width-manager@example.test")
        role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Grocery")
        InventoryAssignment.objects.create(membership=role, inventory=cls.inventory)
        cls.product = Product.objects.create(business=cls.business, sku="GR-01", name="Oat Milk",
                                             base_unit_label="carton", expiry_tracking_required=False)
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)
        Category.objects.create(business=cls.business, name="Dairy", colour="#306db0")
        Category.objects.create(business=cls.business, name="Pantry")

    def setUp(self):
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.today = timezone.now().astimezone(SINGAPORE).date()

    def get(self, name, *args):
        response = self.client.get(reverse(name, args=args))
        self.assertEqual(response.status_code, 200)
        return response

    def test_every_signed_in_page_uses_the_same_container(self):
        pages = [("home", ()), ("inventory-list", ()), ("product-catalogue", ()), ("account", ()), ("help", ()),
                 ("inventory-products", (self.inventory.pk,)), ("import-stock-csv", (self.inventory.pk,)),
                 ("bulk-verify-demand", (self.inventory.pk,)), ("category-list", (self.business.pk,)),
                 ("manager-staff", (self.business.pk,)), ("staff-invitations", (self.business.pk,)),
                 ("product-edit", (self.inventory.pk, self.product.pk)),
                 ("reorder-settings", (self.inventory.pk, self.product.pk)),
                 ("inventory-rename", (self.inventory.pk,))]
        for name, args in pages:
            with self.subTest(page=name):
                response = self.get(name, *args)
                self.assertContains(response, '<main id="main-content" class="workspace-main">')
                self.assertContains(response, '<header class="ph"><div class="ph-inner">')

    def test_import_csv_has_an_upload_card_and_a_format_card(self):
        response = self.get("import-stock-csv", self.inventory.pk)
        self.assertContains(response, '<div class="split">')
        self.assertContains(response, "Upload to Grocery")
        self.assertContains(response, 'class="drop" data-file-drop')
        self.assertContains(response, 'aria-label="CSV file"')
        self.assertContains(response, ">Choose file</span>", html=False)
        self.assertContains(response, ">Cancel</a>", html=False)
        self.assertContains(response, '<ul class="rules">')
        self.assertContains(response, "1,000 rows and 256 KB")
        self.assertContains(response, "All or nothing")
        self.assertContains(response, "Download template")
        self.assertNotContains(response, "Selected inventory")

    def activate(self):
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=self.today - timedelta(days=10),
            origin_xid="1", actual_committed_at=timezone.now(), state="active")

    def test_verify_demand_pills_and_button(self):
        self.activate()
        response = self.get("bulk-verify-demand", self.inventory.pk)
        self.assertContains(response, '<p class="ph-sub">Confirm that every stock issue')
        self.assertEqual(response.context["unverified_days"], 7)
        self.assertContains(response, "7 unverified")
        self.assertContains(response, ">Verify 7 unverified days</button>", html=False)
        self.assertEqual(response.content.decode().count(">Unverified</span>"), 7)
        self.assertContains(response, ">Verify this date</button>", html=False)
        self.assertNotContains(response, "Back to products")
        self.assertNotContains(response, "Verify all unverified days in the last 7")

        for offset in range(7, 0, -1):
            coverage = DemandCoverageDay.objects.create(inventory_product=self.link,
                                                        day=self.today - timedelta(days=offset))
            DemandCoverageEvent.objects.create(coverage_day=coverage, actor=self.manager, action="verified",
                                               reason="", recorded_at=timezone.now(), verified_total_units=0)
        self.assertEqual(set(unreviewed_by_day(self.inventory.pk).values()), {0})
        response = self.get("bulk-verify-demand", self.inventory.pk)
        self.assertContains(response, '<button class="btn btn-primary" type="submit" disabled>All 7 days verified</button>',
                            html=True)
        self.assertEqual(response.content.decode().count(">Verified</span>"), 7)

    def test_categories_table_swatches_and_pager(self):
        response = self.get("category-list", self.business.pk)
        self.assertContains(response, '<circle cx="5" cy="5" r="5" fill="#306db0"/>', html=False)
        self.assertContains(response, "#306DB0")
        self.assertContains(response, '<span class="muted">No colour</span>', html=True)
        self.assertContains(response, "Showing <strong>1–2</strong> of 2 categories")
        self.assertContains(response, 'class="btn btn-sm" href=')

    def test_invitations_put_the_form_beside_the_table(self):
        response = self.get("staff-invitations", self.business.pk)
        body = response.content.decode()
        self.assertIn('<div class="split split-aside">', body)
        self.assertLess(body.index("invite-title"), body.index("invitations-title"))

    def test_products_filters_tips_and_no_placeholders(self):
        response = self.get("inventory-products", self.inventory.pk)
        self.assertNotContains(response, "product-symbol")
        self.assertNotContains(response, "Physical is recorded stock")
        for column in ("Physical", "Quarantined", "Available"):
            self.assertContains(response, f'aria-label="What {column} means"')
        self.assertEqual(response.content.decode().count('class="product-filter-field"'), 4)
