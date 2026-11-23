"""TORY-67: a read-only Activity log for Staff, limited to their inventories and stock movements."""

from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from catalogue.templatetags.tory_format import sgdayheading, sgrelative
from inventory_access.inventory_changes import create_inventory, set_staff_access, update_inventory
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.services import adjust_stock, issue_stock, receive_manual

SG = ZoneInfo("Asia/Singapore")


class RelativeTimeTests(SimpleTestCase):
    now = datetime(2026, 11, 23, 13, 13, tzinfo=SG)

    def test_relative_labels(self):
        for minutes_ago, expected in ((0, "just now"), (25, "25 min ago"), (125, "2 h ago"),
                                      (60 * 19, "Yesterday 18:13"), (60 * 24 * 3, "Fri 13:13")):
            with self.subTest(minutes_ago=minutes_ago):
                self.assertEqual(sgrelative(self.now - timedelta(minutes=minutes_ago), self.now), expected)
        self.assertEqual(sgrelative(self.now - timedelta(days=30), self.now), "24 Oct 2026, 13:13")
        self.assertEqual(sgdayheading(date(2026, 11, 23), self.now), "Today · Mon 23 Nov")
        self.assertEqual(sgdayheading(date(2026, 11, 22), self.now), "Yesterday · Sun 22 Nov")
        self.assertEqual(sgdayheading(date(2026, 11, 20), self.now), "Fri 20 Nov")


class StaffActivityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Staff log business")
        cls.manager = users.create_user(email="log-manager@example.test", display_name="Mia Tan")
        cls.staff = users.create_user(email="log-staff@example.test", display_name="Ravi Kumar")
        cls.colleague = users.create_user(email="log-colleague@example.test", display_name="Vault Keeper")
        cls.manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        colleague_role = BusinessMembership.objects.create(business=cls.business, user=cls.colleague, role="staff")
        cls.grocery = Inventory.objects.create(business=cls.business, name="Grocery")
        cls.vault = Inventory.objects.create(business=cls.business, name="Vault")
        for inventory in (cls.grocery, cls.vault):
            InventoryAssignment.objects.create(membership=cls.manager_role, inventory=inventory)
        InventoryAssignment.objects.create(membership=cls.staff_role, inventory=cls.grocery)
        InventoryAssignment.objects.create(membership=colleague_role, inventory=cls.vault)
        cls.milk = Product.objects.create(business=cls.business, sku="GR-01", name="Oat Milk", base_unit_label="carton",
                                          expiry_tracking_required=False)
        cls.gold = Product.objects.create(business=cls.business, sku="VA-01", name="Gold Bar", base_unit_label="bar",
                                          expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.grocery, product=cls.milk)
        InventoryProduct.objects.create(inventory=cls.vault, product=cls.gold)

    def setUp(self):
        self.url = reverse("activity-log", args=[self.business.pk])
        batch = receive_manual(user_id=self.manager.pk, inventory_id=self.grocery.pk, product_id=self.milk.pk,
                               request_token=uuid4(), quantity_units=10, expiry_date=None)[0]
        issue_stock(user_id=self.staff.pk, inventory_id=self.grocery.pk, product_id=self.milk.pk, quantity_units=3)
        adjust_stock(user_id=self.manager.pk, inventory_id=self.grocery.pk, product_id=self.milk.pk,
                     reason="recount", batch_counts=[{"batch_id": batch.pk, "counted_quantity_units": 6,
                                                      "manager_confirmed_identity": True}])
        receive_manual(user_id=self.manager.pk, inventory_id=self.vault.pk, product_id=self.gold.pk,
                       request_token=uuid4(), quantity_units=5, expiry_date=None)
        update_inventory(user=self.manager, inventory=self.grocery, name="Grocery store")  # a settings row
        set_staff_access(user=self.manager, inventory=self.vault, membership_ids=set())  # an access row
        create_inventory(user=self.manager, business_id=self.business.pk, name="Annex")

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def rows(self, **params):
        response = self.client.get(self.url, {"scope": "all", **params})
        self.assertEqual(response.status_code, 200)
        return response.context["rows"], response

    def test_staff_see_only_movements_in_their_assigned_inventories(self):
        self.login(self.staff)
        rows, response = self.rows()
        self.assertEqual(sorted(row["kind"] for row in rows), ["adjustment", "issue", "receipt"])
        self.assertTrue(all(row["inventory_id"] == self.grocery.pk for row in rows))
        self.assertNotContains(response, "Gold Bar")
        self.assertNotContains(response, "Renamed")
        self.assertNotContains(response, "access")
        self.assertNotContains(response, "Download CSV")
        self.assertContains(response, "Stock movements in the inventories you are assigned to.")

    def test_an_unassigned_inventory_never_leaks(self):
        self.login(self.staff)
        response = self.client.get(self.url, {"inventory": self.vault.pk})
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "Gold Bar", status_code=400)
        rows, _ = self.rows(q="VA-01")
        self.assertEqual(rows, [])
        self.assertEqual(self.client.get(self.url, {"action": "inventory"}).status_code, 400)  # not a Staff choice
        form = self.client.get(self.url).context["form"]
        self.assertEqual([label for _, label in form.fields["inventory"].choices], ["All inventories", "Grocery store"])

    def test_staff_cannot_filter_by_someone_outside_their_scope(self):
        self.login(self.staff)
        users = [pk for pk, _ in self.client.get(self.url).context["form"].fields["user"].choices if pk]
        self.assertCountEqual(users, [self.manager.pk, self.staff.pk])
        self.assertEqual(self.client.get(self.url, {"user": self.colleague.pk}).status_code, 400)
        rows, _ = self.rows(user=self.manager.pk)
        self.assertEqual(sorted(row["kind"] for row in rows), ["adjustment", "receipt"])

    def test_csv_export_is_forbidden_for_staff(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("activity-log-csv", args=[self.business.pk])).status_code, 403)
        self.login(self.manager)
        self.assertEqual(self.client.get(reverse("activity-log-csv", args=[self.business.pk])).status_code, 200)

    def test_a_manager_sees_everything(self):
        self.login(self.manager)
        rows, response = self.rows()
        kinds = {row["kind"] for row in rows}
        self.assertTrue({"receipt", "issue", "adjustment", "inventory", "access"} <= kinds)
        self.assertEqual({row["inventory_id"] for row in rows if row["kind"] == "receipt"},
                         {self.grocery.pk, self.vault.pk})
        self.assertContains(response, "Download CSV")

    def test_sidebar_and_restyled_rows(self):
        self.login(self.staff)
        sidebar = self.client.get(reverse("help")).content.decode()
        sidebar = sidebar[sidebar.index('id="workspace-sidebar"'):sidebar.index("</aside>")]
        self.assertIn(f'href="{self.url}"', sidebar)
        _, response = self.rows()
        self.assertContains(response, '<tr class="daysep"><th scope="rowgroup" colspan="8">Today · ')
        self.assertContains(response, '<span class="pill amber" title="Stock issued">Issued</span>', html=True)
        self.assertContains(response, '<span class="pill green" title="Stock received">Received</span>', html=True)
        self.assertContains(response, "−3")
        self.assertContains(response, "just now")
        self.assertContains(response, "Showing <strong>1–3</strong> of 3")

    def test_staff_without_assignments_see_nothing(self):
        InventoryAssignment.objects.filter(membership=self.staff_role).update(is_active=False)
        self.login(self.staff)
        rows, _ = self.rows()
        self.assertEqual(rows, [])
