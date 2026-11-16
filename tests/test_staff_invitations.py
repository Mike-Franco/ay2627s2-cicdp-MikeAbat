from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as datetime_timezone
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase, override_settings

from accounts.invitations import (
    INVITATION_LIFETIME,
    StaffInvitationError,
    prepare_staff_invitation,
    redeem_staff_invitation,
    replace_staff_invitation,
    revoke_staff_invitation,
)
from accounts.models import StaffInvitation, StaffInvitationInventory
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


ANCHOR = datetime(2026, 11, 16, 2, 0, tzinfo=datetime_timezone.utc)
PASSWORD = "invitation-test-password-9381"


class StaffInvitationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.business = Business.objects.create(name="Clinic A")
        cls.other_business = Business.objects.create(name="Clinic B")
        cls.manager = User.objects.create_user(email="manager@example.test", password="manager-pass")
        cls.other_manager = User.objects.create_user(email="other-manager@example.test", password="manager-pass")
        cls.manager_membership = BusinessMembership.objects.create(
            business=cls.business,
            user=cls.manager,
            role=BusinessMembership.Role.MANAGER,
        )
        cls.other_manager_membership = BusinessMembership.objects.create(
            business=cls.other_business,
            user=cls.other_manager,
            role=BusinessMembership.Role.MANAGER,
        )
        cls.inventory_one = Inventory.objects.create(business=cls.business, name="Main Shop")
        cls.inventory_two = Inventory.objects.create(business=cls.business, name="Cold Room")
        cls.foreign_inventory = Inventory.objects.create(
            business=cls.other_business,
            name="Other Shop",
        )
        InventoryAssignment.objects.create(
            membership=cls.manager_membership,
            inventory=cls.inventory_one,
        )
        InventoryAssignment.objects.create(
            membership=cls.manager_membership,
            inventory=cls.inventory_two,
        )
        InventoryAssignment.objects.create(
            membership=cls.other_manager_membership,
            inventory=cls.foreign_inventory,
        )

    def prepare(self, email="staff@example.test", inventory_ids=None, **kwargs):
        return prepare_staff_invitation(
            self.manager,
            business_id=self.business.pk,
            target_email=email,
            inventory_ids=(
                [self.inventory_one.pk, self.inventory_two.pk]
                if inventory_ids is None
                else inventory_ids
            ),
            at=kwargs.pop("at", ANCHOR),
        )

    def test_issue_stores_only_purpose_digest_and_has_24_hour_expiry(self):
        result = self.prepare()

        self.assertEqual(result.invitation.target_email, "staff@example.test")
        self.assertEqual(result.invitation.status, StaffInvitation.Status.PENDING)
        self.assertEqual(result.invitation.expires_at, ANCHOR + INVITATION_LIFETIME)
        self.assertNotEqual(result.invitation.token_digest, result.token)
        self.assertNotIn(result.token, repr(result))
        self.assertEqual(
            set(result.invitation.inventories.values_list("pk", flat=True)),
            {self.inventory_one.pk, self.inventory_two.pk},
        )

    def test_casefolded_identity_allows_only_one_pending_invitation(self):
        first = self.prepare(email="Staff@Example.Test")

        with self.assertRaises(StaffInvitationError):
            self.prepare(email="staff@example.test")

        self.assertEqual(
            StaffInvitation.objects.filter(status=StaffInvitation.Status.PENDING).count(),
            1,
        )
        self.assertEqual(first.invitation.target_email, "staff@example.test")

    def test_replacement_supersedes_old_token_and_issues_new_latest_token(self):
        old = self.prepare()
        replacement = replace_staff_invitation(
            self.manager,
            old.invitation.pk,
            inventory_ids=[self.inventory_two.pk],
            at=ANCHOR + timedelta(minutes=1),
        )

        old.invitation.refresh_from_db()
        self.assertEqual(old.invitation.status, StaffInvitation.Status.SUPERSEDED)
        self.assertEqual(
            set(replacement.invitation.inventories.values_list("pk", flat=True)),
            {self.inventory_two.pk},
        )
        with self.assertRaises(StaffInvitationError):
            redeem_staff_invitation(old.token, PASSWORD, at=ANCHOR + timedelta(minutes=2))
        user = redeem_staff_invitation(
            replacement.token,
            PASSWORD,
            at=ANCHOR + timedelta(minutes=2),
        )
        self.assertEqual(user.email, "staff@example.test")

    def test_replacement_after_expiry_issues_a_fresh_24_hour_token(self):
        old = self.prepare()
        now = old.invitation.expires_at
        replacement = replace_staff_invitation(
            self.manager,
            old.invitation.pk,
            at=now,
        )

        old.invitation.refresh_from_db()
        self.assertEqual(old.invitation.status, StaffInvitation.Status.EXPIRED)
        self.assertEqual(replacement.invitation.expires_at, now + INVITATION_LIFETIME)

    def test_expiry_boundary_is_exclusive_and_pre_boundary_redemption_succeeds(self):
        expired = self.prepare(email="expired@example.test")
        with self.assertRaises(StaffInvitationError):
            redeem_staff_invitation(
                expired.token,
                PASSWORD,
                at=expired.invitation.expires_at,
            )
        self.assertFalse(get_user_model().objects.filter(email="expired@example.test").exists())

        valid = self.prepare(email="valid@example.test")
        user = redeem_staff_invitation(
            valid.token,
            PASSWORD,
            at=valid.invitation.expires_at - timedelta(microseconds=1),
        )
        self.assertEqual(user.email, "valid@example.test")

    def test_revoked_token_cannot_be_redeemed(self):
        result = self.prepare()
        revoked = revoke_staff_invitation(self.manager, result.invitation.pk, at=ANCHOR)

        self.assertEqual(revoked.status, StaffInvitation.Status.REVOKED)
        with self.assertRaises(StaffInvitationError):
            redeem_staff_invitation(result.token, PASSWORD, at=ANCHOR)

    def test_existing_email_created_after_issue_is_not_reused_or_changed(self):
        result = self.prepare()
        existing = get_user_model().objects.create_user(
            email="STAFF@example.test",
            password="existing-account-password",
        )
        before = (existing.password, existing.is_active, existing.is_staff, existing.is_superuser)

        with self.assertRaises(StaffInvitationError):
            redeem_staff_invitation(result.token, PASSWORD, at=ANCHOR)

        existing.refresh_from_db()
        self.assertEqual(
            (existing.password, existing.is_active, existing.is_staff, existing.is_superuser),
            before,
        )
        self.assertEqual(BusinessMembership.objects.filter(user=existing).count(), 0)
        result.invitation.refresh_from_db()
        self.assertEqual(result.invitation.status, StaffInvitation.Status.PENDING)

    def test_cross_business_pending_collision_is_generic_and_preserves_first_invitation(self):
        first = self.prepare()

        with self.assertRaises(StaffInvitationError) as raised:
            prepare_staff_invitation(
                self.other_manager,
                business_id=self.other_business.pk,
                target_email="STAFF@example.test",
                inventory_ids=[self.foreign_inventory.pk],
                at=ANCHOR,
            )

        self.assertNotIn("Clinic A", str(raised.exception))
        self.assertNotIn("staff@example.test", str(raised.exception))
        self.assertEqual(StaffInvitation.objects.count(), 1)
        first.invitation.refresh_from_db()
        self.assertEqual(first.invitation.status, StaffInvitation.Status.PENDING)

    def test_invalid_inventory_and_cross_business_scope_are_rejected(self):
        with self.assertRaises(StaffInvitationError):
            self.prepare(inventory_ids=[])
        with self.assertRaises(StaffInvitationError):
            self.prepare(inventory_ids=[self.inventory_one.pk, self.foreign_inventory.pk])
        with self.assertRaises(StaffInvitationError):
            prepare_staff_invitation(
                self.other_manager,
                business_id=self.business.pk,
                target_email="other@example.test",
                inventory_ids=[self.inventory_one.pk],
                at=ANCHOR,
            )
        self.assertEqual(StaffInvitation.objects.count(), 0)

    def test_redemption_rechecks_manager_authority_and_assignment_changes(self):
        result = self.prepare(inventory_ids=[self.inventory_one.pk])
        InventoryAssignment.objects.filter(
            membership=self.manager_membership,
            inventory=self.inventory_one,
        ).update(is_active=False)

        with self.assertRaises(StaffInvitationError):
            redeem_staff_invitation(result.token, PASSWORD, at=ANCHOR)

        self.assertFalse(get_user_model().objects.filter(email="staff@example.test").exists())
        result.invitation.refresh_from_db()
        self.assertEqual(result.invitation.status, StaffInvitation.Status.PENDING)

    def test_revoke_requires_current_manager_scope_to_every_selected_inventory(self):
        result = self.prepare()
        InventoryAssignment.objects.filter(
            membership=self.manager_membership,
            inventory=self.inventory_two,
        ).update(is_active=False)

        with self.assertRaises(StaffInvitationError):
            revoke_staff_invitation(self.manager, result.invitation.pk, at=ANCHOR)
        result.invitation.refresh_from_db()
        self.assertEqual(result.invitation.status, StaffInvitation.Status.PENDING)

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {
                "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                "OPTIONS": {"min_length": 20},
            }
        ]
    )
    def test_configured_password_validation_rejects_without_consuming_invite(self):
        result = self.prepare()
        with self.assertRaises(StaffInvitationError):
            redeem_staff_invitation(result.token, "too-short", at=ANCHOR)
        self.assertFalse(get_user_model().objects.filter(email="staff@example.test").exists())
        result.invitation.refresh_from_db()
        self.assertEqual(result.invitation.status, StaffInvitation.Status.PENDING)

    def test_empty_password_rejected_even_when_project_has_no_password_validators(self):
        result = self.prepare()
        with self.assertRaises(StaffInvitationError):
            redeem_staff_invitation(result.token, "", at=ANCHOR)
        self.assertFalse(get_user_model().objects.filter(email="staff@example.test").exists())

    def test_assignment_failure_rolls_back_user_membership_and_consumption(self):
        result = self.prepare()
        with patch.object(InventoryAssignment.objects, "bulk_create", side_effect=IntegrityError):
            with self.assertRaises(StaffInvitationError):
                redeem_staff_invitation(result.token, PASSWORD, at=ANCHOR)

        self.assertFalse(get_user_model().objects.filter(email="staff@example.test").exists())
        self.assertEqual(BusinessMembership.objects.filter(business=self.business).count(), 1)
        self.assertEqual(
            InventoryAssignment.objects.filter(membership__role=BusinessMembership.Role.STAFF).count(),
            0,
        )
        result.invitation.refresh_from_db()
        self.assertEqual(result.invitation.status, StaffInvitation.Status.PENDING)

    def test_manager_daily_limit_counts_replacements_and_uses_singapore_calendar_day(self):
        current = self.prepare()
        for _ in range(4):
            current = replace_staff_invitation(
                self.manager,
                current.invitation.pk,
                at=ANCHOR + timedelta(minutes=1),
            )
        self.assertEqual(
            StaffInvitation.objects.filter(invited_by=self.manager).count(),
            5,
        )
        with self.assertRaises(StaffInvitationError):
            self.prepare(email="sixth@example.test", at=ANCHOR + timedelta(hours=2))

        next_singapore_day = datetime(2026, 11, 16, 16, 0, tzinfo=datetime_timezone.utc)
        next_issue = self.prepare(email="next-day@example.test", at=next_singapore_day)
        self.assertEqual(next_issue.invitation.status, StaffInvitation.Status.PENDING)


class StaffInvitationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="Concurrency clinic")
        self.manager = User.objects.create_user(email="race-manager@example.test", password="manager-pass")
        self.membership = BusinessMembership.objects.create(
            business=self.business,
            user=self.manager,
            role=BusinessMembership.Role.MANAGER,
        )
        self.inventory_one = Inventory.objects.create(business=self.business, name="Front Store")
        self.inventory_two = Inventory.objects.create(business=self.business, name="Back Store")
        for inventory in (self.inventory_one, self.inventory_two):
            InventoryAssignment.objects.create(membership=self.membership, inventory=inventory)
        self.inventory_ids = [self.inventory_one.pk, self.inventory_two.pk]

    def _parallel(self, count, operation):
        barrier = Barrier(count)

        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return operation(index)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(run, range(count)))

    def test_concurrent_issuance_for_one_identity_creates_one_pending_invitation(self):
        self.assertEqual(connection.vendor, "postgresql")

        def issue(_):
            try:
                return prepare_staff_invitation(
                    self.manager,
                    business_id=self.business.pk,
                    target_email="same@example.test",
                    inventory_ids=self.inventory_ids,
                    at=ANCHOR,
                )
            except StaffInvitationError:
                return None

        results = self._parallel(2, issue)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(
            StaffInvitation.objects.filter(
                target_email="same@example.test",
                status=StaffInvitation.Status.PENDING,
            ).count(),
            1,
        )

    def test_concurrent_redemption_creates_one_staff_account_and_consumes_once(self):
        issued = prepare_staff_invitation(
            self.manager,
            business_id=self.business.pk,
            target_email="redeem-race@example.test",
            inventory_ids=self.inventory_ids,
            at=ANCHOR,
        )

        def redeem(_):
            try:
                user = redeem_staff_invitation(issued.token, PASSWORD, at=ANCHOR)
                return user.pk
            except StaffInvitationError:
                return None

        results = self._parallel(2, redeem)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(
            get_user_model().objects.filter(email="redeem-race@example.test").count(),
            1,
        )
        invitation = StaffInvitation.objects.get(pk=issued.invitation.pk)
        self.assertEqual(invitation.status, StaffInvitation.Status.REDEEMED)
        staff_membership = BusinessMembership.objects.get(
            user__email="redeem-race@example.test",
            business=self.business,
        )
        self.assertSetEqual(
            set(
                InventoryAssignment.objects.filter(membership=staff_membership).values_list(
                    "inventory_id", flat=True
                )
            ),
            set(self.inventory_ids),
        )

    def test_concurrent_issuance_cannot_exceed_daily_manager_limit(self):
        for index in range(4):
            prepare_staff_invitation(
                self.manager,
                business_id=self.business.pk,
                target_email=f"prior-{index}@example.test",
                inventory_ids=self.inventory_ids,
                at=ANCHOR,
            )

        def issue(index):
            try:
                return prepare_staff_invitation(
                    self.manager,
                    business_id=self.business.pk,
                    target_email=f"race-limit-{index}@example.test",
                    inventory_ids=self.inventory_ids,
                    at=ANCHOR,
                )
            except StaffInvitationError:
                return None

        results = self._parallel(2, issue)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(
            StaffInvitation.objects.filter(invited_by=self.manager).count(),
            5,
        )
