from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffInvitation, StaffInvitationInventory
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import Category, InventoryProduct, Product
from inventory_access.models import (
    Business,
    BusinessMembership,
    Inventory,
    InventoryAssignment,
)

from receiving.services import receive_manual


class ListPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Pagination business")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Main shelf")
        cls.hidden = Inventory.objects.create(business=cls.business, name="Private shelf")
        cls.other_business = Business.objects.create(name="Other business")
        cls.other_inventory = Inventory.objects.create(business=cls.other_business, name="Other shelf")
        user_model = get_user_model()
        cls.manager = user_model.objects.create_user(email="pagination-manager@example.test")
        cls.staff = user_model.objects.create_user(email="staff-000@example.test")
        cls.membership = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_membership = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        for membership in (cls.membership, staff_membership):
            InventoryAssignment.objects.create(inventory=cls.inventory, membership=membership)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def add_products(self, start, stop):
        products = Product.objects.bulk_create([
            Product(business=self.business, name="Green tea", sku=f"TEA-{number:03d}")
            for number in range(start, stop)
        ])
        InventoryProduct.objects.bulk_create([
            InventoryProduct(inventory=self.inventory, product=product) for product in products
        ])

    def add_staff(self, start, stop):
        user_model = get_user_model()
        users = user_model.objects.bulk_create([
            user_model(email=f"staff-{number:03d}@example.test") for number in range(start, stop)
        ])
        BusinessMembership.objects.bulk_create([
            BusinessMembership(business=self.business, user=user, role="staff") for user in users
        ])

    def add_invitations(self, start, stop):
        now = timezone.now()
        invitations = StaffInvitation.objects.bulk_create([
            StaffInvitation(
                target_email=f"invite-{number:03d}@example.test", business=self.business,
                manager_membership=self.membership, invited_by=self.manager, token_digest=f"{number:064x}",
                issued_at=now, expires_at=now + timedelta(days=1),
            ) for number in range(start, stop)
        ])
        StaffInvitationInventory.objects.bulk_create([
            StaffInvitationInventory(invitation=invitation, inventory=self.inventory)
            for invitation in invitations
        ])
        return invitations

    def test_product_search_and_reorder_filters_survive_page_links(self):
        self.add_products(0, 29)
        product = Product.objects.create(business=self.business, name="Coffee", sku="COFFEE")
        InventoryProduct.objects.create(inventory=self.inventory, product=product)
        self.login(self.staff)
        for url, filters in (
            (reverse("product-catalogue"), {"q": "Green tea"}),
            (reverse("inventory-products", args=[self.inventory.pk]), {"q": "Green tea", "reorder": "unavailable"}),
        ):
            with self.subTest(url=url):
                first = self.client.get(url, filters)
                self.assertEqual(len(first.context["product_links"]), 25)
                self.assertEqual(first.context["page"].paginator.count, 29)
                query = "&amp;reorder=unavailable" if "reorder" in filters else ""
                self.assertContains(first, f'href="?q=Green+tea{query}&amp;page=2"')
                second = self.client.get(url, {**filters, "page": 2})
                self.assertEqual(
                    [link.product.sku for link in second.context["product_links"]],
                    ["TEA-025", "TEA-026", "TEA-027", "TEA-028"],
                )
                self.assertContains(second, f'href="?q=Green+tea{query}&amp;page=1"')

    def test_staff_and_invitation_pages_use_stable_order_and_fall_back(self):
        self.add_staff(1, 27)
        self.add_invitations(0, 27)
        self.login(self.manager)
        for route, context, first_email, last_emails in (
            ("manager-staff", "staff_accounts", "staff-000@example.test", [
                "staff-025@example.test", "staff-026@example.test",
            ]),
            ("staff-invitations", "invitations", "invite-026@example.test", [
                "invite-001@example.test", "invite-000@example.test",
            ]),
        ):
            with self.subTest(route=route):
                url = reverse(route, args=[self.business.pk])
                first = self.client.get(url, {"page": "invalid"})
                self.assertEqual(first.context["page"].number, 1)
                self.assertEqual(len(first.context[context]), 25)
                self.assertContains(first, first_email)
                last = self.client.get(url, {"page": 9999})
                self.assertEqual(last.context["page"].number, 2)
                self.assertEqual(len(last.context[context]), 2)
                for email in last_emails:
                    self.assertContains(last, email)

    def test_pagination_does_not_change_scope(self):
        invitation = self.add_invitations(0, 1)[0]
        StaffInvitationInventory.objects.create(invitation=invitation, inventory=self.hidden)
        self.login(self.manager)
        response = self.client.get(reverse("staff-invitations", args=[self.business.pk]), {"page": 2})
        self.assertEqual(response.context["page"].paginator.count, 0)
        for user in (self.staff, self.manager):
            self.login(user)
            for inventory in (self.hidden, self.other_inventory):
                url = reverse("inventory-products", args=[inventory.pk])
                self.assertEqual(self.client.get(url, {"page": 2}).status_code, 404)
            for route in ("manager-staff", "staff-invitations"):
                url = reverse(route, args=[self.other_business.pk])
                self.assertEqual(self.client.get(url, {"page": 2}).status_code, 404)
                if user == self.staff:
                    url = reverse(route, args=[self.business.pk])
                    self.assertEqual(self.client.get(url, {"page": 2}).status_code, 404)

    def test_query_counts_are_constant_as_rows_grow(self):
        self.add_products(0, 2)
        self.add_invitations(0, 2)
        self.login(self.manager)
        pages = [
            (reverse("product-catalogue"), {}),
            (reverse("inventory-list"), {}),
            (reverse("inventory-products", args=[self.inventory.pk]), {}),
            (reverse("inventory-products", args=[self.inventory.pk]), {"reorder": "unavailable"}),
            (reverse("manager-staff", args=[self.business.pk]), {}),
            (reverse("staff-invitations", args=[self.business.pk]), {}),
        ]

        def counts():
            result = []
            for url, params in pages:
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)
                result.append(len(queries))
            return result

        counts()  # TORY-63: opening the products page selects the inventory, which scopes the catalogue
        initial = counts()
        self.add_products(2, 70)
        self.add_staff(1, 70)
        self.add_invitations(2, 70)
        self.assertEqual(counts(), initial)

    def test_catalogue_filters_and_sort_links(self):
        self.add_products(0, 28)
        category = Category.objects.create(business=self.business, name="Tea")
        Product.objects.filter(sku="TEA-000").update(category=category, is_active=False)
        self.login(self.staff)
        url = reverse("product-catalogue")
        filters = {"q": "Green tea", "inventory": self.inventory.pk, "status": "active", "tag": ["a", "b"]}
        response = self.client.get(url, {**filters, "page": 2})
        self.assertEqual(response.context["page"].paginator.count, 27)
        self.assertContains(response, 'sort=name')
        self.assertContains(response, 'tag=a&amp;tag=b')
        self.assertContains(response, 'page=1')
        for status, count in (("inactive", 1), ("out", 27), ("low", 0)):
            with self.subTest(status=status):
                response = self.client.get(url, {"status": status, "inventory": self.inventory.pk})
                self.assertEqual(response.context["page"].paginator.count, count)
        response = self.client.get(url, {"category": category.pk})
        self.assertEqual([row.product.sku for row in response.context["product_links"]], ["TEA-000"])
        for sort in ("sku", "name", "available", "category"):
            with self.subTest(sort=sort):
                ordered = self.client.get(url, {"sort": "-" + sort})
                self.assertContains(ordered, 'aria-sort="descending"')
        self.assertEqual(self.client.get(url, {"inventory": self.hidden.pk}).status_code, 400)

    def test_team_search_status_and_sorts(self):
        self.add_staff(1, 27)
        self.add_invitations(0, 27)
        self.login(self.manager)
        get_user_model().objects.filter(email="staff-005@example.test").update(is_active=False, first_name="Ada")
        StaffInvitation.objects.filter(target_email="invite-005@example.test").update(status="revoked")
        for route, params, sorts, email in (
            ("manager-staff", {"q": "Ada", "status": "inactive"},
             ("name", "email", "status", "last_login"), "staff-005@example.test"),
            ("staff-invitations", {"q": "005", "status": "revoked"},
             ("email", "status", "sent", "expires"), "invite-005@example.test"),
        ):
            with self.subTest(route=route):
                url = reverse(route, args=[self.business.pk])
                for sort in sorts:
                    response = self.client.get(url, {**params, "sort": "-" + sort, "page": 9})
                    self.assertEqual(response.context["page"].paginator.count, 1)
                    self.assertContains(response, email)
                    self.assertContains(response, 'aria-sort="descending"')
                page = self.client.get(url, {"q": email.split("-")[0], "sort": "-email"})
                self.assertContains(page, 'sort=-email&amp;page=2')

    def test_inventory_search_sort_and_scope(self):
        self.login(self.staff)
        url = reverse("inventory-list")
        for sort in ("name", "-low", "-value"):
            response = self.client.get(url, {"q": self.inventory.name, "sort": sort})
            self.assertEqual([inventory.pk for inventory in response.context["inventories"]], [self.inventory.pk])
            self.assertNotContains(response, self.hidden.name)
        self.assertEqual(self.client.get(url, {"q": self.hidden.name}).context["page"].paginator.count, 0)

    def test_inventory_count_and_retail_sort_use_available_stock(self):
        self.add_products(0, 2)
        second = Inventory.objects.create(business=self.business, name="A priced shelf")
        InventoryAssignment.objects.create(membership=self.membership, inventory=second)
        item = Product.objects.create(business=self.business, sku="PRICED", name="Priced", base_unit_label="bag",
                                      expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=second, product=item, selling_price="3.25")
        receive_manual(user_id=self.manager.pk, inventory_id=second.pk, product_id=item.pk, request_token=uuid4(),
                       quantity_units=4, expiry_date=None)
        self.login(self.manager)
        url = reverse("inventory-list")
        low = self.client.get(url, {"sort": "-low"}).context["inventories"]
        self.assertEqual([inventory.pk for inventory in low], [self.inventory.pk, second.pk])
        self.assertEqual(low[0].stock.out, 2)
        value = self.client.get(url, {"sort": "-value"})
        self.assertEqual([inventory.pk for inventory in value.context["inventories"]], [second.pk, self.inventory.pk])
        self.assertContains(value, "S$13.00")
