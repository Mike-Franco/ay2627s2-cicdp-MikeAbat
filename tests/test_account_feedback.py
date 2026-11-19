"""Focused regressions for controlled feedback; not executed in this pass."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.invitations import prepare_staff_invitation
from accounts.password_resets import request_password_reset
from accounts.models import StaffInvitation, PasswordResetLink
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


class AccountFeedbackTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="manager@example.test", password="original-password-926")
        self.business = Business.objects.create(name="Private business")
        self.inventory = Inventory.objects.create(business=self.business, name="Private inventory")
        self.member = BusinessMembership.objects.create(user=self.user, business=self.business, role="manager")
        InventoryAssignment.objects.create(membership=self.member, inventory=self.inventory)
        self.invite = prepare_staff_invitation(self.user, business_id=self.business.pk,
            target_email="new@example.test", inventory_ids=[self.inventory.pk])
        self.reset = request_password_reset(self.user.email, "192.0.2.12").credentials

    def post(self, kind, password, confirmation=None, token=None):
        name, credential = (("staff-invitation-setup", self.invite) if kind == "invite"
                            else ("password-reset-setup", self.reset))
        return self.client.post(reverse(name), {"token": credential.token if token is None else token,
            "password": password, "password_confirm": password if confirmation is None else confirmation})

    def test_multiple_policy_errors_and_confirmation_retry_without_mutation(self):
        original = self.user.password
        counts = (get_user_model().objects.count(), BusinessMembership.objects.count(), InventoryAssignment.objects.count())
        for kind in ("invite", "reset"):
            result = self.post(kind, "password", "").json()
            self.assertFalse(result["ok"])
            self.assertIn("Use at least 15 characters.", result["errors"]["password"])
            self.assertIn("Choose a less common password.", result["errors"]["password"])
            self.assertEqual(result["errors"]["password_confirm"], ["Confirm your new password."])
            mismatch = self.post(kind, "unusual-fjord-lantern-2875", "different").json()
            self.assertEqual(mismatch["errors"], {"password_confirm": ["Passwords do not match."]})
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, original)
        self.assertEqual(counts, (get_user_model().objects.count(), BusinessMembership.objects.count(), InventoryAssignment.objects.count()))
        self.assertEqual(StaffInvitation.objects.get(pk=self.invite.invitation.pk).status, "pending")
        self.assertEqual(PasswordResetLink.objects.get(pk=self.reset.link.pk).status, "pending")
        for kind in ("invite", "reset"):
            self.assertTrue(self.post(kind, "unusual-fjord-lantern-2875").json()["ok"])
            self.assertFalse(self.post(kind, "unusual-fjord-lantern-2875").json()["ok"])

    def test_unusable_tokens_hide_validation_and_unknown_codes_use_safe_fallback(self):
        for kind in ("invite", "reset"):
            invalid = self.post(kind, "password", token="invalid-token").json()
            self.assertNotIn("errors", invalid)
            self.assertNotIn("password", invalid["error"].lower())
            module = "accounts.password_feedback.validate_password"
            with patch(module, side_effect=ValidationError("SECRET account@example.test", code="unknown")):
                result = self.post(kind, "long-enough-password-9843").json()
            self.assertNotIn("SECRET", str(result))
            self.assertNotIn("account@example.test", str(result))
            self.assertIn("configured requirements", result["errors"]["password"][0])

    def test_similarity_uses_real_configured_validator_without_echoing_identity(self):
        result = self.post("reset", "manager@example.test").json()
        self.assertIn("Choose a password less similar to your account details.", result["errors"]["password"])
        self.assertNotIn(self.user.email, str(result))

    @override_settings(DEBUG=True)
    def test_expected_missing_and_unauthorized_targets_have_friendly_404(self):
        self.client.force_login(self.user)
        session = self.client.session
        from django.utils import timezone
        from accounts.sessions import CREATED_KEY, ACTIVE_KEY
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        foreign = Business.objects.create(name="Undisclosed foreign business")
        urls = [reverse("staff-invitations", args=[foreign.pk]),
                reverse("manager-staff", args=[999999]),
                reverse("confirm-staff-deactivation", args=[self.business.pk,999999])]
        for url in urls:
            response = self.client.get(url)
            self.assertContains(response, "Page unavailable", status_code=404)
            self.assertNotContains(response, "URL patterns", status_code=404)
            self.assertNotContains(response, "Undisclosed foreign business", status_code=404)
        self.member.role = "staff"
        self.member.save(update_fields=["role"])
        response = self.client.get(reverse("staff-invitations", args=[self.business.pk]))
        self.assertContains(response, "Page unavailable", status_code=404)

    def test_requirements_and_accessible_fields_are_present(self):
        for name in ("staff-invitation-setup", "password-reset-setup"):
            response = self.client.get(reverse(name))
            for text in ("Use at least 15 characters.", "password-errors", "confirmation-errors", "aria-describedby", 'tabindex="-1"'):
                self.assertContains(response, text)

    def test_current_scope_and_inactive_account_deny_before_validation(self):
        assignment = InventoryAssignment.objects.get(membership=self.member)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with patch("accounts.password_feedback.validate_password") as validator:
            for kind in ("invite", "reset"):
                result = self.post(kind, "password").json()
                self.assertFalse(result["ok"])
                self.assertNotIn("errors", result)
            validator.assert_not_called()
        self.assertEqual(StaffInvitation.objects.get(pk=self.invite.invitation.pk).status, "pending")
        self.assertEqual(PasswordResetLink.objects.get(pk=self.reset.link.pk).status, "pending")
