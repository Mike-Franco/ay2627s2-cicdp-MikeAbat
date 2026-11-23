"""TORY-65: "Who can use this inventory" on the edit page, and type-the-name deactivation."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from inventory_access.inventory_changes import AccessRejected, confirms_name, set_staff_access
from inventory_access.models import (
    Business, BusinessMembership, Inventory, InventoryAccessAuditEvent, InventoryAssignment, InventoryChangeAuditEvent,
)


class InventoryStaffAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Access business")
        cls.other_business = Business.objects.create(name="Elsewhere")
        cls.manager = users.create_user(email="mia@example.test", display_name="Mia Tan")
        cls.aisha = users.create_user(email="aisha@example.test", display_name="Aisha Rahman")
        cls.ravi = users.create_user(email="ravi@example.test", display_name="Ravi Kumar")
        cls.outsider = users.create_user(email="out@example.test")
        cls.manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.aisha_role = BusinessMembership.objects.create(business=cls.business, user=cls.aisha, role="staff")
        cls.ravi_role = BusinessMembership.objects.create(business=cls.business, user=cls.ravi, role="staff")
        cls.foreign_role = BusinessMembership.objects.create(business=cls.other_business, user=cls.outsider,
                                                             role="staff")
        cls.grocery = Inventory.objects.create(business=cls.business, name="Grocery")
        cls.pharmacy = Inventory.objects.create(business=cls.business, name="Pharmacy")
        for inventory in (cls.grocery, cls.pharmacy):
            InventoryAssignment.objects.create(membership=cls.manager_role, inventory=inventory)
        InventoryAssignment.objects.create(membership=cls.ravi_role, inventory=cls.grocery)
        InventoryAssignment.objects.create(membership=cls.aisha_role, inventory=cls.pharmacy)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def edit(self, staff_ids, *, name="Grocery"):
        return self.client.post(reverse("inventory-rename", args=[self.grocery.pk]),
                                {"name": name, "access_form": "1", "staff": [str(pk) for pk in staff_ids]})

    def access(self, membership):
        return InventoryAssignment.objects.filter(membership=membership, inventory=self.grocery,
                                                  is_active=True).exists()

    def test_edit_page_lists_managers_as_always_and_staff_as_checkboxes(self):
        self.login(self.manager)
        response = self.client.get(reverse("inventory-rename", args=[self.grocery.pk]))
        self.assertContains(response, "Who can use this inventory")
        self.assertContains(response, "2 of 3 people have access")
        self.assertContains(response, '<input type="checkbox" checked disabled aria-label="Mia Tan, always has access">',
                            html=True)
        self.assertContains(response, "Manager · always")
        self.assertContains(response, f'name="staff" value="{self.ravi_role.pk}"')
        self.assertContains(response, f'value="{self.aisha_role.pk}" id="staff-{self.aisha_role.pk}" '
                                      'aria-label="Aisha Rahman"')
        self.assertContains(response, "aisha@example.test · Pharmacy only")
        self.assertContains(response, "Select all staff")
        self.assertContains(response, reverse("staff-invitations", args=[self.business.pk]))
        self.assertNotContains(response, "out@example.test")

    def test_bulk_sync_toggles_rows_in_one_save_and_audits_each_change(self):
        self.login(self.manager)
        self.assertRedirects(self.edit([self.aisha_role.pk]), reverse("inventory-list"))
        self.assertTrue(self.access(self.aisha_role))
        self.assertFalse(self.access(self.ravi_role))
        # Ravi's row is switched off, never deleted.
        self.assertTrue(InventoryAssignment.objects.filter(membership=self.ravi_role, inventory=self.grocery).exists())
        events = InventoryAccessAuditEvent.objects.order_by("membership__user__email")
        self.assertEqual([(event.membership_id, event.granted, event.actor_id) for event in events],
                         [(self.aisha_role.pk, True, self.manager.pk), (self.ravi_role.pk, False, self.manager.pk)])
        # Saving again with no change writes nothing new; re-granting reuses the old row.
        self.edit([self.aisha_role.pk])
        self.assertEqual(InventoryAccessAuditEvent.objects.count(), 2)
        self.edit([self.aisha_role.pk, self.ravi_role.pk])
        self.assertEqual(InventoryAssignment.objects.filter(membership=self.ravi_role, inventory=self.grocery).count(), 1)
        self.assertTrue(self.access(self.ravi_role))

    def test_changes_show_up_in_the_activity_log(self):
        self.login(self.manager)
        self.edit([self.aisha_role.pk])
        response = self.client.get(reverse("activity-log", args=[self.business.pk]), {"scope": "all"})
        self.assertContains(response, "Gave Aisha Rahman access")
        self.assertContains(response, "Removed Ravi Kumar’s access")
        self.assertContains(response, "Inventory access changed")
        filtered = self.client.get(reverse("activity-log", args=[self.business.pk]), {"action": "access"})
        self.assertEqual(filtered.context["page"].paginator.count, 2)

    def test_a_membership_from_another_business_is_rejected(self):
        self.login(self.manager)
        response = self.edit([self.ravi_role.pk, self.foreign_role.pk])
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Choose Staff from this business only.", status_code=400)
        self.assertFalse(InventoryAssignment.objects.filter(membership=self.foreign_role).exists())
        self.assertFalse(InventoryAccessAuditEvent.objects.exists())
        self.assertEqual(self.edit(["junk"]).status_code, 400)
        # A manager membership is not a staff checkbox either.
        with self.assertRaises(AccessRejected):
            set_staff_access(user=self.manager, inventory=self.grocery, membership_ids={self.manager_role.pk})
        self.assertTrue(self.access(self.ravi_role))

    def test_a_name_only_submission_leaves_access_alone(self):
        self.login(self.manager)
        self.client.post(reverse("inventory-rename", args=[self.grocery.pk]), {"name": "Grocery"})
        self.assertTrue(self.access(self.ravi_role))
        self.assertFalse(InventoryAccessAuditEvent.objects.exists())

    def test_only_managers_can_change_access(self):
        self.login(self.ravi)
        self.assertEqual(self.client.get(reverse("inventory-rename", args=[self.grocery.pk])).status_code, 404)
        self.assertEqual(self.edit([self.ravi_role.pk, self.aisha_role.pk]).status_code, 404)
        self.assertFalse(self.access(self.aisha_role))
        self.login(self.outsider)
        self.assertEqual(self.edit([]).status_code, 404)
        self.assertTrue(self.access(self.ravi_role))

    def test_staff_lose_access_immediately(self):
        self.login(self.ravi)
        products = reverse("inventory-products", args=[self.grocery.pk])
        self.assertEqual(self.client.get(products).status_code, 200)
        set_staff_access(user=self.manager, inventory=self.grocery, membership_ids=set())
        self.assertEqual(self.client.get(products).status_code, 404)
        self.assertNotContains(self.client.get(reverse("inventory-list")), "Grocery")


class TypeNameToDeactivateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Confirm business")
        cls.manager = get_user_model().objects.create_user(email="confirm@example.test")
        membership = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Grocery")
        InventoryAssignment.objects.create(membership=membership, inventory=cls.inventory)

    def setUp(self):
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.url = reverse("inventory-status", args=[self.inventory.pk])

    def test_name_check_is_case_sensitive_and_trimmed(self):
        self.assertTrue(confirms_name(self.inventory, "Grocery"))
        self.assertTrue(confirms_name(self.inventory, "  Grocery \n"))
        for typed in ("grocery", "GROCERY", "Grocer", "", None):
            with self.subTest(typed=typed):
                self.assertFalse(confirms_name(self.inventory, typed))

    def test_wrong_name_is_rejected_and_nothing_changes(self):
        for typed in (None, "grocery", "Pharmacy"):
            data = {"is_active": "false"} if typed is None else {"is_active": "false", "confirm_name": typed}
            with self.subTest(typed=typed):
                response = self.client.post(self.url, data)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Type Grocery exactly to confirm.", status_code=400)
        self.inventory.refresh_from_db()
        self.assertTrue(self.inventory.is_active)
        self.assertFalse(InventoryChangeAuditEvent.objects.exists())

    def test_right_name_deactivates_and_reactivation_needs_no_name(self):
        self.assertRedirects(self.client.post(self.url, {"is_active": "false", "confirm_name": " Grocery "}),
                             reverse("inventory-list"))
        self.inventory.refresh_from_db()
        self.assertFalse(self.inventory.is_active)
        self.client.post(self.url, {"is_active": "true"})
        self.inventory.refresh_from_db()
        self.assertTrue(self.inventory.is_active)

    def test_edit_page_has_the_danger_section_with_the_mockup_wording(self):
        response = self.client.get(reverse("inventory-rename", args=[self.inventory.pk]))
        self.assertContains(response, "Hides Grocery from staff and stops new stock movements.")
        self.assertContains(response, "0 products and 0 staff will lose access. Type <strong>Grocery</strong> to confirm.")
        self.assertContains(response, 'name="confirm_name" placeholder="Grocery"')
