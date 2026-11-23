"""TORY-68: UI fixes from review - forecast numbers, row actions, reorder pills, invitations, tables."""

from datetime import datetime, time, timedelta
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffInvitation
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from catalogue.templatetags.tory_format import expires_relative, two_dp, units, whole_units
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import DemandCoverageDay, DemandCoverageEvent, ObservationActivation
from receiving.services import SINGAPORE, issue_stock, receive_manual

STATIC = Path(settings.BASE_DIR, "static", "tory")


class FormatTests(SimpleTestCase):
    def test_fractional_reorder_point_rounds_up_instead_of_a_dash(self):
        # Regression: str(Fraction(71, 7)) is "71/7", which Decimal rejects, so the page showed "—".
        self.assertEqual(whole_units(Fraction(71, 7)), 11)
        self.assertEqual(units(Fraction(71, 7)), 11)
        self.assertEqual(whole_units(Fraction(14, 1)), 14)
        self.assertEqual(whole_units(5), 5)
        self.assertEqual(whole_units("2.1"), 3)
        self.assertIsNone(whole_units(None))
        self.assertEqual(two_dp(Fraction(71, 7)), "10.14")

    def test_relative_expiry(self):
        now = timezone.now()
        self.assertEqual(expires_relative(now + timedelta(minutes=70), now), "in 1 h")
        self.assertEqual(expires_relative(now + timedelta(minutes=5), now), "in 5 min")
        self.assertEqual(expires_relative(now + timedelta(days=6, minutes=1), now), "in 6 days")
        self.assertEqual(expires_relative(now - timedelta(seconds=1), now), "Expired")

    def test_table_headers_and_layout_tokens(self):
        tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
        self.assertIn("--th-bg:#F3F3F6", tokens)
        self.assertEqual(tokens.count("--th-bg:#1B1B20"), 2)  # explicit dark theme and OS dark preference
        self.assertIn("table thead th{background:var(--th-bg);color:var(--text);font-size:12px;font-weight:600;"
                      "border-bottom:1px solid var(--line2)}", tokens)
        app = (STATIC / "app.css").read_text(encoding="utf-8")
        self.assertNotIn("max-width:1240px", app)
        self.assertIn(".content{width:100%;max-width:var(--page-max);margin-inline:auto;", app)
        self.assertIn("--page-max:1600px;--gutter:32px", app)
        self.assertIn(".workspace-main.layout-narrow{--page-max:880px}", app)
        pages = (STATIC / "pages.css").read_text(encoding="utf-8")
        self.assertIn(".product-tabs::-webkit-scrollbar{display:none}", pages)
        self.assertIn("scrollbar-width:none", pages)
        self.assertIn(".row-actions{display:flex;flex-wrap:nowrap;align-items:center;gap:6px}", pages)

    def test_menu_script_supports_the_keyboard(self):
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        for key in ("'Escape'", "'ArrowDown'", "'ArrowUp'", "'Home'", "'End'"):
            self.assertIn(key, script)


class Tory68PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Polish business")
        cls.manager = users.create_user(email="polish-manager@example.test")
        cls.staff = users.create_user(email="polish-staff@example.test")
        cls.manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Grocery")
        for role in (cls.manager_role, staff_role):
            InventoryAssignment.objects.create(membership=role, inventory=cls.inventory)
        # Lead time 1 and no safety stock: reorder point = 71/7 = 10.14..., shown as 11.
        cls.product = Product.objects.create(
            business=cls.business, sku="GR-01", name="Oat Milk", base_unit_label="carton",
            expiry_tracking_required=False, lead_time_days=1, safety_stock_units=0)
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)
        cls.other = Product.objects.create(
            business=cls.business, sku="GR-02", name="Rice", base_unit_label="bag",
            expiry_tracking_required=False, lead_time_days=3, safety_stock_units=5)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.other)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def setUp(self):
        self.login(self.manager)
        self.today = timezone.now().astimezone(SINGAPORE).date()

    def seventy_one_units_over_a_verified_week(self):
        receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                       request_token=uuid4(), quantity_units=80, expiry_date=None)
        ObservationActivation.objects.create(
            environment=settings.DJANGO_ENV, first_observed_date=self.today - timedelta(days=10),
            origin_xid="1", actual_committed_at=timezone.now(), state="active")
        for offset, units_issued in zip(range(7, 0, -1), (10, 10, 10, 10, 10, 10, 11), strict=True):
            day = self.today - timedelta(days=offset)
            with patch("receiving.services.timezone.now", return_value=datetime.combine(day, time(12), SINGAPORE)):
                issue_stock(user_id=self.staff.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                            quantity_units=units_issued)
            coverage = DemandCoverageDay.objects.create(inventory_product=self.link, day=day)
            DemandCoverageEvent.objects.create(coverage_day=coverage, actor=self.manager, action="verified",
                                               reason="", recorded_at=timezone.now(),
                                               verified_total_units=units_issued)

    def get(self, name, *args, **params):
        with patch("receiving.demand.tracking_enabled", return_value=True):
            return self.client.get(reverse(name, args=args), params)

    def test_forecast_shows_the_rounded_reorder_point_and_an_explanation_that_matches(self):
        self.seventy_one_units_over_a_verified_week()
        response = self.get("demand-forecast", self.inventory.pk, self.product.pk)
        self.assertEqual(response.status_code, 200)
        reorder, calc, info = response.context["reorder"], response.context["calc"], response.context["info"]
        self.assertEqual(reorder.reorder_point, Fraction(71, 7))
        self.assertEqual(info["reorder_point"], 11)
        self.assertContains(response, '<div class="k">Reorder point</div><div class="v">11</div>', html=True)
        self.assertContains(response, "71 units issued over the last 7 complete Asia/Singapore dates ÷ 7 = "
                                      "<strong>10.14</strong>")
        self.assertContains(response, "10.14 × 1 + 0 = 10.14, rounded up to "
                                      '<strong data-calc="reorder-point">11</strong>')
        # Suggested order = ceil(71/7 × (14 + 1) + 0 − 9) = ceil(152.14 − 9) = 144
        self.assertEqual(calc["suggested"], 144)
        self.assertContains(response, "ceil(10.14 × 15 + 0 − 9) = ceil(152.14 − 9) = "
                                      '<strong data-calc="suggested">144</strong>')
        self.assertContains(response, '<div class="k">Suggested order</div><div class="v">144</div>', html=True)
        self.assertContains(response, "<details class=\"calc\">")

        overview = self.get("product-stock", self.inventory.pk, self.product.pk).context["info"]
        self.assertEqual((overview["reorder_point"], overview["suggested"], overview["average"]),
                         (info["reorder_point"], calc["suggested"], info["average"]))
        dashboard = self.get("home")
        row = next(row for row in dashboard.context["actions"]["rows"] if row["link"].pk == self.link.pk)
        self.assertEqual(row["position"].reorder.suggested_units, calc["suggested"])
        self.assertContains(dashboard, '<span class="list-mobile-label" aria-hidden="true">Reorder point</span>11',
                            html=False)

    def test_every_product_tab_shares_one_header(self):
        self.seventy_one_units_over_a_verified_week()
        pages = [("product-stock", {}), ("product-stock", {"tab": "batches"}), ("stock-history", {}),
                 ("demand-forecast", {})]
        for name, params in pages:
            with self.subTest(page=name, **params):
                response = self.get(name, self.inventory.pk, self.product.pk, **params)
                self.assertContains(response, '<span class="ph-sku">GR-01</span>', html=False)
                self.assertContains(response, '<span class="pill amber">Low stock</span>', html=False)
                for label in (">Receive<", ">Issue<", ">Adjust<", "Edit reorder settings", "Download history CSV",
                              'class="danger" href'):
                    self.assertContains(response, label)
                self.assertNotContains(response, "product-meta")
                self.assertNotContains(response, "GR-01</span> · carton")

    def test_forecast_layout_has_four_numbers_dates_and_a_verify_card(self):
        self.seventy_one_units_over_a_verified_week()
        response = self.get("demand-forecast", self.inventory.pk, self.product.pk)
        for label in ("Avg daily demand", "Reorder point", "Suggested order", "Days of supply"):
            self.assertContains(response, f'<div class="k">{label}</div>', html=False)
        self.assertContains(response, 'class="kv kv-flush"')
        self.assertContains(response, '<ol class="days7"', html=False)
        self.assertEqual(response.content.decode().count('<span class="status-pill success">Verified</span>'), 7)
        self.assertContains(response, 'class="fc-layout has-side"')
        self.assertContains(response, 'class="panel verify-card"')

    def test_products_list_rows_and_no_forecast_notice(self):
        response = self.get("inventory-products", self.inventory.pk)
        body = response.content.decode()
        self.assertEqual(response.context["no_forecast_count"], 2)
        self.assertContains(response, "2 products have no forecast yet — <a href=\"%s\">Verify demand</a>"
                            % reverse("bulk-verify-demand", args=[self.inventory.pk]), html=False)
        self.assertEqual(body.count('<span class="status-pill neutral">No forecast</span>'), 3)  # notice + 2 rows
        self.assertContains(response, "Each of the last 7 dates needs Manager verification")
        # The old sentence pill is gone; the Reorder filter option keeps that name.
        self.assertNotContains(response, 'status-pill neutral">Reorder point unavailable')
        self.assertEqual(body.count('<div class="row-actions">'), 2)
        self.assertContains(response, 'aria-label="More actions for Oat Milk" aria-haspopup="menu"')
        for label in (">History<", ">Forecast<", ">Adjust<", ">Dispose<", 'class="danger" href'):
            self.assertContains(response, label)
        self.assertNotContains(response, "actions-full")

        self.login(self.staff)
        response = self.get("inventory-products", self.inventory.pk)
        self.assertContains(response, "2 products have no forecast yet")
        self.assertNotContains(response, "Verify demand</a>")
        for label in (">Adjust<", ">Dispose<", ">Deactivate<"):
            self.assertNotContains(response, label)

    def test_form_pages_use_the_narrow_column(self):
        for name, args in (("product-edit", (self.inventory.pk, self.product.pk)),
                           ("reorder-settings", (self.inventory.pk, self.product.pk)),
                           ("inventory-rename", (self.inventory.pk,)), ("account", ()),
                           ("staff-invitations", (self.business.pk,))):
            with self.subTest(page=name):
                self.assertContains(self.get(name, *args), 'class="workspace-main layout-narrow"')
        self.assertContains(self.get("inventory-products", self.inventory.pk), 'class="workspace-main"')

    def test_invitations_page(self):
        now = timezone.now()
        statuses = {"pending@example.test": ("pending", now + timedelta(minutes=70)),
                    "accepted@example.test": ("redeemed", now + timedelta(days=2)),
                    "expired@example.test": ("pending", now - timedelta(hours=1)),
                    "revoked@example.test": ("revoked", now + timedelta(days=2))}
        for email, (status, expires) in statuses.items():
            invitation = StaffInvitation.objects.create(
                target_email=email, business=self.business, manager_membership=self.manager_role, invited_by=self.manager,
                status=status,
                token_digest=email.ljust(64, "0")[:64], issued_at=now - timedelta(days=1), expires_at=expires)
            invitation.inventory_links.create(inventory=self.inventory)
        response = self.get("staff-invitations", self.business.pk)
        self.assertEqual(response.status_code, 200)
        crumbs = response.content.decode().split('class="crumbs"')[1].split("</nav>")[0]
        self.assertIn(">Dashboard</a>", crumbs)
        self.assertIn('>Team</a>', crumbs)
        self.assertIn('aria-current="page">Invitations<', crumbs)
        self.assertContains(response, "Invite someone")
        self.assertContains(response, "Inventories they can use")
        self.assertContains(response, 'class="prow"')
        self.assertContains(response, "data-select-all")
        self.assertContains(response, "Managers see every inventory.")
        self.assertNotContains(response, "form-check")
        for pill in ('status-pill info">Pending', 'status-pill success">Accepted', 'status-pill neutral">Expired',
                     'status-pill danger">Revoked'):
            self.assertContains(response, pill)
        self.assertContains(response, ">in 1 h</time>", html=False)
        self.assertContains(response, ">Expired</time>", html=False)
        self.assertContains(response, ">Resend</button>", html=False)
        self.assertContains(response, 'class="btn-text danger"')
        self.assertNotContains(response, " result")
        self.assertContains(response, "data-autosubmit")
        self.assertContains(response, "Showing <strong>1–4</strong> of 4")
