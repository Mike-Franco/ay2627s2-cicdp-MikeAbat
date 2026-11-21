import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import (
    Business,
    BusinessMembership,
    Inventory,
    InventoryAssignment,
    InventoryChangeAuditEvent,
)
from receiving.models import ReceiptAuditEvent, ReceivingBatch
from receiving.services import ReceiptRejected, receive_manual


class InventoryManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Inventory management business")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Main shelf")
        cls.other_business = Business.objects.create(name="Another business")
        cls.other_inventory = Inventory.objects.create(business=cls.other_business, name="Foreign shelf")
        user_model = get_user_model()
        cls.manager = user_model.objects.create_user(email="inventory-manager@example.test")
        cls.staff = user_model.objects.create_user(email="inventory-staff@example.test")
        cls.manager_membership = BusinessMembership.objects.create(
            user=cls.manager, business=cls.business, role=BusinessMembership.Role.MANAGER,
        )
        cls.staff_membership = BusinessMembership.objects.create(
            user=cls.staff, business=cls.business, role=BusinessMembership.Role.STAFF,
        )
        cls.foreign_membership = BusinessMembership.objects.create(
            user=cls.manager, business=cls.other_business, role=BusinessMembership.Role.MANAGER,
        )
        InventoryAssignment.objects.create(membership=cls.manager_membership, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.staff_membership, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.foreign_membership, inventory=cls.other_inventory)
        cls.product = Product.objects.create(
            business=cls.business, sku="SKU-1", name="Bandages", base_unit_label="each",
            expiry_tracking_required=False,
        )
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def setUp(self):
        self.login(self.manager)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def test_create_autoassigns_manager_and_records_audit_transactionally(self):
        response = self.client.post(reverse("inventory-create", args=[self.business.pk]), {"name": "  Cold storage  "})
        self.assertRedirects(response, reverse("inventory-list"))
        inventory = Inventory.objects.get(business=self.business, name="Cold storage")
        self.assertTrue(InventoryAssignment.objects.get(inventory=inventory, membership=self.manager_membership).is_active)
        event = InventoryChangeAuditEvent.objects.get(inventory=inventory)
        self.assertEqual((event.actor, event.action, event.before, event.after), (
            self.manager, "create", None, {"name": "Cold storage", "is_active": True},
        ))
        self.assertContains(self.client.get(reverse("inventory-list")), "Cold storage")

    def test_create_rejects_trimmed_case_insensitive_duplicate(self):
        response = self.client.post(
            reverse("inventory-create", args=[self.business.pk]), {"name": "  mAiN ShElF "},
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "already exists in this business", status_code=400)
        self.assertEqual(Inventory.objects.filter(business=self.business).count(), 1)

    def test_create_can_use_command_only_business_but_requires_assignment(self):
        response = self.client.post(reverse("inventory-create", args=[self.business.pk]), {"name": "Cold storage"})
        self.assertEqual(response.status_code, 302)
        inventory = Inventory.objects.get(business=self.business, name="Cold storage")
        self.assertTrue(InventoryAssignment.objects.filter(
            inventory=inventory, membership=self.manager_membership,
        ).exists())

    def test_rename_and_deactivate_reactivate_write_audits(self):
        self.client.post(reverse("inventory-rename", args=[self.inventory.pk]), {"name": "  Supply room  "})
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.name, "Supply room")
        self.assertEqual(InventoryChangeAuditEvent.objects.get(action="rename").after["name"], "Supply room")
        self.client.post(reverse("inventory-status", args=[self.inventory.pk]), {"is_active": "false"})
        self.inventory.refresh_from_db()
        self.assertFalse(self.inventory.is_active)
        self.assertEqual(self.client.get(reverse("inventory-products", args=[self.inventory.pk])).status_code, 404)
        self.assertTrue(InventoryChangeAuditEvent.objects.get(action="deactivate").before["is_active"])
        self.client.post(reverse("inventory-status", args=[self.inventory.pk]), {"is_active": "true"})
        self.inventory.refresh_from_db()
        self.assertTrue(self.inventory.is_active)
        self.assertTrue(InventoryChangeAuditEvent.objects.get(action="reactivate").after["is_active"])

    def test_deactivation_removes_new_inventory_from_switcher(self):
        response = self.client.post(reverse("inventory-status", args=[self.inventory.pk]), {"is_active": "false"})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse("inventory-list")), "Main shelf")

    def test_creating_manager_can_add_products_in_new_inventory(self):
        self.client.post(reverse("inventory-create", args=[self.business.pk]), {"name": "Cold storage"})
        inventory = Inventory.objects.get(business=self.business, name="Cold storage")
        self.assertEqual(self.client.get(reverse("product-create", args=[inventory.pk])).status_code, 200)

    def test_staff_and_foreign_business_are_denied(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("inventory-create", args=[self.business.pk])).status_code, 404)
        for route, args, data in (
            ("inventory-create", [self.business.pk], {"name": "A"}),
            ("inventory-rename", [self.inventory.pk], {"name": "A"}),
            ("inventory-status", [self.inventory.pk], {"is_active": "false"}),
        ):
            self.assertEqual(self.client.post(reverse(route, args=args), data).status_code, 404)
        self.login(self.manager)

    def test_deactivated_inventory_rejects_stock_writes_and_urls(self):
        receive_manual(
            user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
            request_token=uuid.uuid4(), quantity_units=2, expiry_date=None,
        )
        self.client.post(reverse("inventory-status", args=[self.inventory.pk]), {"is_active": "false"})
        with self.assertRaises(ReceiptRejected):
            receive_manual(
                user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                request_token=uuid.uuid4(), quantity_units=1, expiry_date=None,
            )
        from receiving.services import issue_stock
        with self.assertRaises(ReceiptRejected):
            issue_stock(
                user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=self.product.pk,
                quantity_units=1,
            )
        self.inventory.refresh_from_db()
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)
        self.assertEqual(ReceivingBatch.objects.count(), 1)
        self.assertEqual(self.client.get(
            reverse("receive-batch", args=[self.inventory.pk, self.product.pk]),
        ).status_code, 404)

    def test_csrf_and_get_cannot_change_inventory(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.manager)
        url = reverse("inventory-create", args=[self.business.pk])
        self.assertEqual(client.get(url).status_code, 302)
        self.assertEqual(client.post(url, {"name": "No token"}).status_code, 403)
        self.assertFalse(Inventory.objects.filter(business=self.business).exclude(pk=self.inventory.pk).exists())
