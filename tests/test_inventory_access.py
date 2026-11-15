from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ABSOLUTE_SECONDS, ACTIVE_KEY, CREATED_KEY, IDLE_SECONDS
from inventory_access.authorization import assign_staff_inventory
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


class InventoryAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business_a = Business.objects.create(name="Business A")
        cls.business_b = Business.objects.create(name="Business B")
        cls.manager = get_user_model().objects.create_user(
            email="manager@example.test", password="test-only-password"
        )
        cls.staff = get_user_model().objects.create_user(
            email="staff@example.test", password="test-only-password"
        )
        cls.unassigned = get_user_model().objects.create_user(
            email="unassigned@example.test", password="test-only-password"
        )
        cls.manager_membership = BusinessMembership.objects.create(
            business=cls.business_a, user=cls.manager, role=BusinessMembership.Role.MANAGER
        )
        cls.staff_membership = BusinessMembership.objects.create(
            business=cls.business_a, user=cls.staff, role=BusinessMembership.Role.STAFF
        )
        cls.inventory_a = Inventory.objects.create(business=cls.business_a, name="A shelf")
        cls.inventory_b = Inventory.objects.create(business=cls.business_b, name="Secret B shelf")
        InventoryAssignment.objects.create(membership=cls.manager_membership, inventory=cls.inventory_a)
        InventoryAssignment.objects.create(membership=cls.staff_membership, inventory=cls.inventory_a)

    def authenticate(self, user):
        self.client.force_login(user)
        session = self.client.session
        now = timezone.now().timestamp()
        session[CREATED_KEY] = now
        session[ACTIVE_KEY] = now
        session.save()

    def test_assigned_manager_and_staff_can_view_inventory(self):
        for user in (self.manager, self.staff):
            self.client.logout()
            self.authenticate(user)
            response = self.client.get(reverse("inventory-detail", args=[self.inventory_a.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "A shelf")

    def test_workspace_uses_effective_role_and_assigned_inventory_navigation(self):
        for user, role in ((self.manager, "Manager"), (self.staff, "Staff")):
            self.client.logout()
            self.authenticate(user)
            response = self.client.get(reverse("inventory-products", args=[self.inventory_a.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f"<small>{role}</small>", html=True)
            self.assertContains(response, 'data-set-theme="light"')
            self.assertContains(response, 'data-set-theme="dark"')
            self.assertContains(response, 'action="/logout/"')
            self.assertNotContains(response, "Secret B shelf")
            if role == "Manager":
                self.assertContains(response, "Import CSV")
            else:
                self.assertNotContains(response, "Import CSV")

    def test_unauthenticated_user_is_redirected(self):
        response = self.client.get(reverse("inventory-list"))
        self.assertRedirects(response, reverse("login"))

    def test_authenticated_but_unassigned_user_gets_no_inventory(self):
        self.authenticate(self.unassigned)
        response = self.client.get(reverse("inventory-list"))
        self.assertContains(response, "No inventories are assigned")
        self.assertNotContains(response, "A shelf")

    def test_other_business_inventory_and_changed_url_id_are_hidden(self):
        self.authenticate(self.manager)
        url = reverse("inventory-detail", args=[self.inventory_b.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Secret B shelf", status_code=404)

    def test_staff_assignment_does_not_cross_business(self):
        self.authenticate(self.staff)
        response = self.client.get(reverse("inventory-detail", args=[self.inventory_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_inactive_user_and_expired_session_are_denied(self):
        self.authenticate(self.manager)
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(reverse("inventory-list")).status_code, 302)

        self.manager.is_active = True
        self.manager.save(update_fields=["is_active"])
        self.authenticate(self.manager)
        created = timezone.now()
        with patch("accounts.sessions.timezone.now", return_value=created + timedelta(seconds=IDLE_SECONDS)):
            self.assertEqual(self.client.get(reverse("inventory-list")).status_code, 302)

        self.authenticate(self.manager)
        created = timezone.now()
        with patch("accounts.sessions.timezone.now", return_value=created + timedelta(seconds=ABSOLUTE_SECONDS)):
            self.assertEqual(self.client.get(reverse("inventory-list")).status_code, 302)

    def test_cross_business_assignment_fails_model_validation(self):
        assignment = InventoryAssignment(
            membership=self.staff_membership, inventory=self.inventory_b
        )
        with self.assertRaises(ValidationError):
            assignment.save()

    def test_postgresql_trigger_rejects_raw_cross_business_assignment(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO inventory_access_inventoryassignment "
                    "(membership_id, inventory_id, is_active, assigned_at) "
                    "VALUES (%s, %s, TRUE, NOW())",
                    [self.staff_membership.pk, self.inventory_b.pk],
                )

    def test_postgresql_trigger_prevents_business_move_with_assignments(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.inventory_a.business = self.business_b
            self.inventory_a.save(update_fields=["business"])

    def test_manager_can_assign_staff_only_to_inventory_they_manage(self):
        new_staff = get_user_model().objects.create_user(
            email="new-staff@example.test", password="test-only-password"
        )
        membership = BusinessMembership.objects.create(
            business=self.business_a, user=new_staff, role=BusinessMembership.Role.STAFF
        )
        assignment = assign_staff_inventory(self.manager, membership, self.inventory_a)
        self.assertEqual(assignment.membership_id, membership.pk)

        with self.assertRaises(PermissionDenied):
            assign_staff_inventory(self.manager, membership, self.inventory_b)
