"""TORY-11 deactivation checks; intentionally unrun in this implementation pass."""

from concurrent.futures import ThreadPoolExecutor
from time import monotonic
import uuid

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.deactivation import StaffDeactivationRejected, deactivate_staff
from accounts.password_resets import PasswordResetError, redeem_password_reset, request_password_reset
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import ReceiptAuditEvent
from receiving.services import receive_manual


PASSWORD = "deactivation-test-password"


class StaffDeactivationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="A")
        self.other = Business.objects.create(name="B")
        self.inventory = Inventory.objects.create(business=self.business, name="Main")
        self.extra = Inventory.objects.create(business=self.business, name="Extra")
        self.manager = User.objects.create_user(email="manager@example.test", password=PASSWORD)
        self.staff = User.objects.create_user(email="staff@example.test", password=PASSWORD)
        self.manager_member = BusinessMembership.objects.create(
            user=self.manager, business=self.business, role="manager")
        self.staff_member = BusinessMembership.objects.create(
            user=self.staff, business=self.business, role="staff")
        InventoryAssignment.objects.create(membership=self.manager_member, inventory=self.inventory)
        self.staff_assignment = InventoryAssignment.objects.create(
            membership=self.staff_member, inventory=self.inventory)
        self.list_url = reverse("manager-staff", args=[self.business.pk])
        self.confirm_url = reverse("confirm-staff-deactivation", args=[self.business.pk, self.staff.pk])
        self.action_url = reverse("deactivate-staff", args=[self.business.pk, self.staff.pk])

    def sign_in(self, client, user):
        client.force_login(user)
        session = client.session
        session[CREATED_KEY] = timezone.now().timestamp()
        session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def test_authorized_deactivation_retains_identity_scope_and_attribution(self):
        product = Product.objects.create(
            business=self.business, sku="DEACT-1", name="Attributable item",
            base_unit_label="each", expiry_tracking_required=False,
        )
        InventoryProduct.objects.create(inventory=self.inventory, product=product)
        batch, _ = receive_manual(
            user_id=self.staff.pk, inventory_id=self.inventory.pk,
            product_id=product.pk, request_token=uuid.uuid4(),
            quantity_units=1, expiry_date=None,
        )
        audit_id = ReceiptAuditEvent.objects.get(batch=batch).pk
        self.sign_in(self.client, self.manager)
        self.assertContains(self.client.get(self.list_url), self.staff.email)
        self.assertContains(self.client.get(self.confirm_url), self.staff.email)
        self.assertEqual(self.client.post(self.action_url).status_code, 302)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.assertEqual(BusinessMembership.objects.get(pk=self.staff_member.pk).user_id, self.staff.pk)
        self.assertEqual(InventoryAssignment.objects.get(pk=self.staff_assignment.pk).membership_id,
                         self.staff_member.pk)
        self.assertEqual(ReceiptAuditEvent.objects.get(pk=audit_id).actor_id, self.staff.pk)
        self.assertEqual(self.client.post(self.action_url).status_code, 302)

    def test_callers_targets_method_and_csrf(self):
        self.assertEqual(self.client.post(self.action_url).status_code, 302)
        self.sign_in(self.client, self.staff)
        self.assertEqual(self.client.get(self.list_url).status_code, 404)
        self.assertEqual(self.client.post(self.action_url).status_code, 404)
        self.sign_in(self.client, self.manager)
        self.assertEqual(self.client.get(self.action_url).status_code, 405)
        self.assertEqual(self.client.post(self.list_url).status_code, 405)
        secure = Client(enforce_csrf_checks=True)
        secure.cookies = self.client.cookies
        self.assertEqual(secure.post(self.action_url).status_code, 403)
        missing = reverse("deactivate-staff", args=[self.business.pk, 999999])
        self.assertEqual(self.client.post(missing).status_code, 404)
        self.assertEqual(self.client.post(reverse("deactivate-staff", args=[self.other.pk, self.staff.pk])).status_code, 404)
        self.assertTrue(get_user_model().objects.get(pk=self.staff.pk).is_active)

    def test_ineligible_accounts_are_hidden_and_denied(self):
        User = get_user_model()
        cases = []
        multi = User.objects.create_user(email="multi@example.test", password=PASSWORD)
        BusinessMembership.objects.create(user=multi, business=self.business, role="staff")
        BusinessMembership.objects.create(user=multi, business=self.other, role="staff", is_active=False)
        cases.append(multi)
        mixed = User.objects.create_user(email="mixed@example.test", password=PASSWORD)
        BusinessMembership.objects.create(user=mixed, business=self.business, role="staff")
        BusinessMembership.objects.create(user=mixed, business=self.other, role="manager", is_active=False)
        cases.append(mixed)
        admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_staff=True)
        BusinessMembership.objects.create(user=admin, business=self.business, role="staff")
        cases.append(admin)
        superuser = User.objects.create_user(email="super@example.test", password=PASSWORD, is_superuser=True)
        BusinessMembership.objects.create(user=superuser, business=self.business, role="staff")
        cases.append(superuser)
        scoped = User.objects.create_user(email="scoped@example.test", password=PASSWORD)
        scoped_member = BusinessMembership.objects.create(user=scoped, business=self.business, role="staff")
        InventoryAssignment.objects.create(membership=scoped_member, inventory=self.extra, is_active=False)
        cases.append(scoped)
        self.sign_in(self.client, self.manager)
        page = self.client.get(self.list_url)
        for target in cases:
            self.assertNotContains(page, target.email)
            self.assertEqual(self.client.get(reverse("confirm-staff-deactivation", args=[self.business.pk, target.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse("deactivate-staff", args=[self.business.pk, target.pk])).status_code, 404)
            with self.assertRaises(StaffDeactivationRejected):
                deactivate_staff(self.manager.pk, self.business.pk, target.pk)
        self.assertEqual(self.client.post(reverse("deactivate-staff", args=[self.business.pk, self.manager.pk])).status_code, 404)

    def test_inactive_assignment_and_inventory_are_not_ignored(self):
        InventoryAssignment.objects.create(membership=self.staff_member, inventory=self.extra, is_active=False)
        with self.assertRaises(StaffDeactivationRejected):
            deactivate_staff(self.manager.pk, self.business.pk, self.staff.pk)
        InventoryAssignment.objects.create(membership=self.manager_member, inventory=self.extra)
        self.extra.is_active = False
        self.extra.save(update_fields=["is_active"])
        with self.assertRaises(StaffDeactivationRejected):
            deactivate_staff(self.manager.pk, self.business.pk, self.staff.pk)
        self.assertTrue(get_user_model().objects.get(pk=self.staff.pk).is_active)

    def test_all_old_sessions_login_and_reset_are_denied(self):
        first, second = Client(), Client()
        for client in (first, second):
            self.sign_in(client, self.staff)
            self.assertEqual(client.get(reverse("home")).status_code, 200)
        reset = request_password_reset(self.staff.email, "192.0.2.1")
        self.assertIsNotNone(reset.credentials)
        deactivate_staff(self.manager.pk, self.business.pk, self.staff.pk)
        for client in (first, second):
            self.assertEqual(client.get(reverse("home")).status_code, 302)
            self.assertNotIn("_auth_user_id", client.session)
        fresh = Client()
        response = fresh.post(reverse("login"), {"email": self.staff.email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", fresh.session)
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(reset.credentials.token, "a-new-password-long-enough")


class StaffDeactivationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        business = Business.objects.create(name="Race")
        self.manager = User.objects.create_user(email="race-manager@example.test", password=PASSWORD)
        self.staff = User.objects.create_user(email="race-staff@example.test", password=PASSWORD)
        manager_member = BusinessMembership.objects.create(user=self.manager, business=business, role="manager")
        self.staff_member = BusinessMembership.objects.create(user=self.staff, business=business, role="staff")
        inventory = Inventory.objects.create(business=business, name="Race inventory")
        InventoryAssignment.objects.create(membership=manager_member, inventory=inventory)
        InventoryAssignment.objects.create(membership=self.staff_member, inventory=inventory)
        self.business_id = business.pk

    def _wait_for_lock(self, pid):
        deadline = monotonic() + 10
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", [pid])
                row = cursor.fetchone()
            if row and row[0] == "Lock":
                return
        self.fail("Worker did not reach PostgreSQL lock wait")

    def test_membership_change_first_denies_queued_deactivation(self):
        self.assertEqual(connection.vendor, "postgresql")
        worker_pid = []
        def worker():
            try:
                close_old_connections()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    worker_pid.append(cursor.fetchone()[0])
                try:
                    deactivate_staff(self.manager.pk, self.business_id, self.staff.pk)
                except StaffDeactivationRejected:
                    return False
                return True
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=self.manager.pk)
                future = pool.submit(worker)
                deadline = monotonic() + 10
                while not worker_pid and monotonic() < deadline:
                    pass
                self.assertTrue(worker_pid)
                self._wait_for_lock(worker_pid[0])
                self.staff_member.role = "manager"
                self.staff_member.save(update_fields=["role"])
            self.assertFalse(future.result(timeout=10))
        self.assertTrue(get_user_model().objects.get(pk=self.staff.pk).is_active)

    def test_assignment_revocation_first_denies_queued_deactivation(self):
        self.assertEqual(connection.vendor, "postgresql")
        worker_pid = []

        def worker():
            try:
                close_old_connections()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    worker_pid.append(cursor.fetchone()[0])
                try:
                    deactivate_staff(self.manager.pk, self.business_id, self.staff.pk)
                except StaffDeactivationRejected:
                    return False
                return True
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=self.manager.pk)
                future = pool.submit(worker)
                deadline = monotonic() + 10
                while not worker_pid and monotonic() < deadline:
                    pass
                self.assertTrue(worker_pid)
                self._wait_for_lock(worker_pid[0])
                InventoryAssignment.objects.filter(membership=self.staff_member).update(is_active=False)
                InventoryAssignment.objects.filter(membership__user=self.manager).update(is_active=False)
            self.assertFalse(future.result(timeout=10))
        self.assertTrue(get_user_model().objects.get(pk=self.staff.pk).is_active)
