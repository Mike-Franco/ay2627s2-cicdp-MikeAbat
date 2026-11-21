from uuid import uuid4

from django.apps import apps
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from catalogue.models import InventoryProduct, Product, ProductLifecycleAuditEvent
from config.ops_admin import ops_admin_site
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import ReceiptAuditEvent
from receiving.services import receive_manual


class OpsAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.password = "test-ops-admin-passphrase"
        cls.superuser = User.objects.create_superuser(email="ops@example.test", password=cls.password)
        business = Business.objects.create(name="Ops business")
        cls.inventory = Inventory.objects.create(business=business, name="Ops pharmacy")
        cls.members = []
        for role in (BusinessMembership.Role.MANAGER, BusinessMembership.Role.STAFF):
            # Exercise the superuser gate with Django staff accounts.
            user = User.objects.create_user(email=f"{role}@ops.example.test", password=cls.password, is_staff=True)
            membership = BusinessMembership.objects.create(user=user, business=business, role=role)
            InventoryAssignment.objects.create(membership=membership, inventory=cls.inventory)
            cls.members.append(user)
        product = Product.objects.create(business=business, sku="OPS", name="Ops item", base_unit_label="each",
                                         expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=product)
        batch, _ = receive_manual(user_id=cls.members[0].pk, inventory_id=cls.inventory.pk, product_id=product.pk,
                                  request_token=uuid4(), quantity_units=12, expiry_date=None)
        cls.audit = batch.audit_event

    def test_manager_and_staff_cannot_access_or_sign_into_ops_admin(self):
        index = reverse("admin:index")
        login = reverse("admin:login")
        self.assertEqual(index, "/ops-admin/")
        self.assertRedirects(self.client.get(index), f"{login}?next={index}")
        for user in self.members:
            with self.subTest(email=user.email):
                self.client.force_login(user)
                self.assertRedirects(self.client.get(index), f"{login}?next={index}")
                self.client.logout()
                response = self.client.post(login, {"username": user.email, "password": self.password, "next": index})
                form = response.context["form"]
                self.assertFormError(form, None, form.get_invalid_login_error().messages)
                self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(login, {"username": self.superuser.email, "password": self.password, "next": index})
        self.assertRedirects(response, index)

    def test_superuser_can_search_inventory_and_view_but_cannot_edit_audit(self):
        self.client.force_login(self.superuser)
        inventories = self.client.get(reverse("admin:inventory_access_inventory_changelist"), {"q": "pharmacy"})
        self.assertContains(inventories, self.inventory.name)

        request = RequestFactory().get("/ops-admin/")
        request.user = self.superuser
        protected_models = (
            *apps.get_app_config("receiving").get_models(), ProductLifecycleAuditEvent, LogEntry, Product, InventoryProduct,
        )
        for model in protected_models:
            with self.subTest(model=model.__name__):
                model_admin = ops_admin_site.get_model_admin(model)
                self.assertTrue(model_admin.has_view_permission(request))
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))
                self.assertEqual(model_admin.get_actions(request), {})

        change = reverse("admin:receiving_receiptauditevent_change", args=(self.audit.pk,))
        delete = reverse("admin:receiving_receiptauditevent_delete", args=(self.audit.pk,))
        add = reverse("admin:receiving_receiptauditevent_add")
        response = self.client.get(change)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["original"], self.audit)
        self.assertEqual(self.client.post(change, {"quantity_after_units": 99}).status_code, 403)
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertEqual(self.client.post(add, {"quantity_after_units": 99}).status_code, 403)
        self.audit.refresh_from_db()
        self.assertEqual(self.audit.quantity_after_units, 12)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)
