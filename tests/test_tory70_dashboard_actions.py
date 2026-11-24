"""TORY-70: the dashboard Stock actions table fits its card, so Receive / Issue / ⋯ never clip.

The widths themselves were checked in a browser at 1280, 1440, 1920 and 390px; these tests pin the
markup and CSS that make it fit: nowrap actions, wrapping headers, and truncated secondary columns
that keep their full text in title.
"""

from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import Category, InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment

STATIC = Path(settings.BASE_DIR, "static", "tory")


class DashboardActionsCssTests(SimpleTestCase):
    def test_actions_stay_nowrap_and_secondary_columns_give_way(self):
        pages = (STATIC / "pages.css").read_text("utf-8")
        for rule in (
            ".cell-truncate{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;"
            "white-space:nowrap}",
            ".products-table.dash-actions-table thead th{white-space:normal;line-height:1.25}",
            ".products-table.dash-actions-table .actions{width:1%;white-space:nowrap}",
            ".dash-actions-table .cell-shrink .cell-truncate{max-width:6.5rem}",
            ".dash-actions-table .status-pill{max-width:8.5rem}",
            "line-clamp:2;max-width:7rem;margin-left:auto;white-space:normal;text-align:left}",
        ):
            self.assertIn(rule, pages)
        # The row actions themselves never wrap (TORY-68).
        self.assertIn(".row-actions{display:flex;flex-wrap:nowrap;align-items:center;gap:6px}", pages)


class DashboardActionsMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        business = Business.objects.create(name="Actions business")
        cls.manager = users.create_user(email="actions-manager@example.test")
        role = BusinessMembership.objects.create(business=business, user=cls.manager, role="manager")
        inventory = Inventory.objects.create(business=business, name="Grocery")
        InventoryAssignment.objects.create(membership=role, inventory=inventory)
        category = Category.objects.create(business=business, name="Dairy alternatives and plant milks")
        # No stock and no verified demand: an out-of-stock action row with a days-of-supply reason.
        product = Product.objects.create(business=business, sku="GR-01", name="Oat Milk", base_unit_label="carton",
                                         expiry_tracking_required=False, category=category)
        InventoryProduct.objects.create(inventory=inventory, product=product)

    def setUp(self):
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def test_stock_actions_row_uses_nowrap_actions_and_titled_truncation(self):
        with patch("receiving.demand.tracking_enabled", return_value=True):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        row = response.context["actions"]["rows"][0]
        self.assertContains(response, 'class="products-table responsive-list dash-actions-table"')
        self.assertContains(response, '<th scope="col" class="actions">Actions</th>', html=False)
        self.assertContains(response, '<td class="actions"><span class="list-mobile-label" aria-hidden="true">Actions'
                                      '</span><div class="row-actions">', html=False)
        for label in (">Receive<", ">Issue<", 'aria-label="More actions for Oat Milk"'):
            self.assertContains(response, label)
        self.assertContains(response, '<td class="nowrap"><span class="list-mobile-label" aria-hidden="true">SKU'
                                      '</span>GR-01</td>', html=False)
        self.assertContains(response, '<span class="cell-truncate" title="Dairy alternatives and plant milks">'
                                      'Dairy alternatives and plant milks</span>', html=False)
        self.assertContains(response, f'<span class="status-pill attention" title="{row["label"]}">'
                                      f'<span class="cell-truncate">{row["label"]}</span></span>', html=False)
        reason = row["position"].supply_reason
        self.assertTrue(reason)
        self.assertContains(response, f'<small class="cell-truncate" title="{reason}">{reason}</small>', html=False)
        # Bootstrap's d-block is !important and would undo the two-line clamp.
        self.assertNotContains(response, 'class="d-block cell-truncate"')
