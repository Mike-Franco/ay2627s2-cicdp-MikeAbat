"""Browser-flow checks; intentionally not executed in the 17 November increment."""

from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.invitations import prepare_staff_invitation
from accounts.models import StaffInvitation
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


MAIL = {
    "STAFF_INVITATION_PUBLIC_ORIGIN": "https://tory.example.test",
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DEFAULT_FROM_EMAIL": "invites@example.test",
}


@override_settings(**MAIL)
class StaffInvitationWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="A")
        self.other = Business.objects.create(name="B")
        self.manager = User.objects.create_user(email="manager@example.test", password="long-manager-password")
        self.staff = User.objects.create_user(email="staff@example.test", password="long-staff-password")
        self.membership = BusinessMembership.objects.create(business=self.business, user=self.manager, role="manager")
        BusinessMembership.objects.create(business=self.business, user=self.staff, role="staff")
        self.inventory = Inventory.objects.create(business=self.business, name="Main")
        self.foreign = Inventory.objects.create(business=self.other, name="Foreign")
        InventoryAssignment.objects.create(membership=self.membership, inventory=self.inventory)
        self.list_url = reverse("staff-invitations", args=[self.business.pk])

    def sign_in(self, user):
        self.client.force_login(user)
        session = self.client.session
        # Match the protected-view clocks without changing their helpers.
        from django.utils import timezone
        from accounts.sessions import CREATED_KEY, ACTIVE_KEY
        session[CREATED_KEY] = timezone.now().timestamp()
        session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def test_access_and_scope(self):
        self.assertEqual(self.client.get(self.list_url).status_code, 302)
        self.sign_in(self.staff)
        self.assertEqual(self.client.get(self.list_url).status_code, 404)
        self.sign_in(self.manager)
        self.assertEqual(self.client.get(reverse("staff-invitations", args=[self.other.pk])).status_code, 404)
        response = self.client.post(self.list_url, {"email": "new@example.test", "inventories": [self.foreign.pk]})
        self.assertEqual(StaffInvitation.objects.count(), 0)
        self.assertNotIn(b"new@example.test", response.content)

    def test_post_csrf_and_mail_origin(self):
        self.sign_in(self.manager)
        secure = Client(enforce_csrf_checks=True)
        secure.cookies = self.client.cookies
        self.assertEqual(secure.post(self.list_url, {"email": "new@example.test", "inventories": [self.inventory.pk]}).status_code, 403)
        self.assertEqual(self.client.get(self.list_url).status_code, 200)
        with override_settings(ALLOWED_HOSTS=["testserver", "alternate.example.test"]):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.list_url, {"email": "new@example.test", "inventories": [self.inventory.pk]}, HTTP_HOST="alternate.example.test")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mail.outbox[0].to, ["new@example.test"])
        self.assertIn("https://tory.example.test/staff/setup/#", mail.outbox[0].body)
        self.assertNotIn("alternate.example.test", mail.outbox[0].body)
        self.assertNotIn("#", response["Location"])
        self.assertEqual(self.client.post(self.list_url, {"email": "rejected@example.test", "inventories": [self.inventory.pk]}, HTTP_HOST="disallowed.example.test").status_code, 400)
        self.assertFalse(StaffInvitation.objects.filter(target_email="rejected@example.test").exists())
        self.assertEqual(len(mail.outbox), 1)
        invitation = StaffInvitation.objects.get()
        change = reverse("staff-invitation-change", args=[self.business.pk, invitation.pk, "revoke"])
        self.assertEqual(self.client.get(change).status_code, 405)

    @override_settings(STAFF_INVITATION_PUBLIC_ORIGIN="")
    def test_disabled_delivery_does_not_issue(self):
        self.sign_in(self.manager)
        self.client.post(self.list_url, {"email": "new@example.test", "inventories": [self.inventory.pk]})
        self.assertFalse(StaffInvitation.objects.exists())

    def test_failed_delivery_keeps_replacement_path(self):
        self.sign_in(self.manager)
        from accounts.invitation_email import InvitationDeliveryError
        with patch("accounts.invitation_views.send_invitation", side_effect=InvitationDeliveryError("failed")) as delivery:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.list_url, {"email": "new@example.test", "inventories": [self.inventory.pk]})
        delivery.assert_called_once()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StaffInvitation.objects.get().status, "pending")
        self.assertFalse(get_user_model().objects.filter(email="new@example.test").exists())
        invitation = StaffInvitation.objects.get()
        with patch("accounts.invitation_views.send_invitation") as resend:
            with self.captureOnCommitCallbacks(execute=True):
                replacement = self.client.post(reverse("staff-invitation-change", args=[self.business.pk, invitation.pk, "replace"]))
        self.assertEqual(replacement.status_code, 302)
        resend.assert_called_once()
        invitations = list(StaffInvitation.objects.order_by("pk"))
        self.assertEqual([item.status for item in invitations], ["superseded", "pending"])

    def test_password_setup_and_reuse(self):
        credentials = prepare_staff_invitation(self.manager, business_id=self.business.pk,
            target_email="new@example.test", inventory_ids=[self.inventory.pk])
        url = reverse("staff-invitation-setup")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).content.find(credentials.token.encode()), -1)
        self.assertEqual(self.client.post(url, {"token": credentials.token, "password": "long-password-0001", "password_confirm": "wrong"}).status_code, 200)
        self.assertFalse(get_user_model().objects.filter(email="new@example.test").exists())
        response = self.client.post(url, {"token": credentials.token, "password": "long-password-0001", "password_confirm": "long-password-0001"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("login"))
        user = get_user_model().objects.get(email="new@example.test")
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(user.business_memberships.get().role, "staff")
        self.assertEqual(user.business_memberships.get().inventory_assignments.get().inventory, self.inventory)
        reused = self.client.post(url, {"token": credentials.token, "password": "long-password-0001", "password_confirm": "long-password-0001"})
        self.assertNotIn(credentials.token.encode(), reused.content)
        self.assertNotIn(b"long-password-0001", reused.content)

    def test_invalid_expired_and_superseded_links(self):
        credentials = prepare_staff_invitation(self.manager, business_id=self.business.pk,
            target_email="new@example.test", inventory_ids=[self.inventory.pk])
        url = reverse("staff-invitation-setup")
        data = {"password": "long-password-0001", "password_confirm": "long-password-0001"}
        for token in ("invalid", credentials.token):
            if token == credentials.token:
                StaffInvitation.objects.filter(pk=credentials.invitation.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
            response = self.client.post(url, {**data, "token": token})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(token.encode(), response.content)
        self.assertFalse(get_user_model().objects.filter(email="new@example.test").exists())

    def test_configured_password_validation_and_revoke(self):
        credentials = prepare_staff_invitation(self.manager, business_id=self.business.pk,
            target_email="new@example.test", inventory_ids=[self.inventory.pk])
        url = reverse("staff-invitation-setup")
        response = self.client.post(url, {"token": credentials.token,
            "password": "short", "password_confirm": "short"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(email="new@example.test").exists())
        self.sign_in(self.manager)
        change = reverse("staff-invitation-change", args=[self.business.pk, credentials.invitation.pk, "revoke"])
        self.assertEqual(self.client.post(change).status_code, 302)
        response = self.client.post(url, {"token": credentials.token,
            "password": "long-password-0001", "password_confirm": "long-password-0001"})
        self.assertEqual(response.status_code, 200)
