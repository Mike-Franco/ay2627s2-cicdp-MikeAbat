"""Web/adapter checks; no background worker or network email is started."""

from datetime import timedelta
from threading import BoundedSemaphore
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import PasswordResetAttempt, PasswordResetLink
from accounts.password_resets import request_password_reset
from accounts.sessions import ACTIVE_KEY, CREATED_KEY


MAIL = {
    "STAFF_INVITATION_PUBLIC_ORIGIN": "https://tory.example.test",
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DEFAULT_FROM_EMAIL": "reset@example.test",
}


@override_settings(**MAIL)
class PasswordResetWebTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="person@example.test", password="old-password-9381")
        self.request_url = reverse("password-reset-request")
        self.setup_url = reverse("password-reset-setup")

    def test_request_is_deferred_and_acknowledgement_uniform(self):
        with patch("accounts.reset_views.enqueue_reset", return_value=True) as enqueue:
            get_response = self.client.get(self.request_url)
            active = self.client.post(self.request_url, {"email": self.user.email}, REMOTE_ADDR="192.0.2.1")
            unknown = self.client.post(self.request_url, {"email": "unknown@example.test"})
            self.user.is_active = False
            self.user.save(update_fields=["is_active"])
            inactive = self.client.post(self.request_url, {"email": self.user.email})
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(enqueue.call_count, 3)
        self.assertEqual(enqueue.call_args_list[0].args, (self.user.email, "192.0.2.1"))
        self.assertEqual([r.status_code for r in (active, unknown, inactive)], [200] * 3)
        for response in (active, unknown, inactive):
            self.assertContains(response, "If eligible, instructions will be sent.")
        self.assertFalse(PasswordResetAttempt.objects.exists())
        self.assertFalse(PasswordResetLink.objects.exists())

    def test_queue_rejection_and_failure_use_same_acknowledgement(self):
        responses = []
        for result in (False, RuntimeError("queue failed"), True):
            with patch("accounts.reset_views.enqueue_reset", side_effect=result if isinstance(result, Exception) else None,
                       return_value=result if not isinstance(result, Exception) else None):
                responses.append(self.client.post(self.request_url, {"email": self.user.email}))
        self.assertEqual([r.status_code for r in responses], [200, 200, 200])
        for response in responses:
            self.assertContains(response, "If eligible, instructions will be sent.")

    def test_mail_recipient_origin_fragment_and_disabled_delivery(self):
        from accounts.reset_dispatch import _run_reset
        from accounts.reset_email import ResetDeliveryError
        with override_settings(ALLOWED_HOSTS=["testserver", "alternate.example.test"]):
            with patch("accounts.reset_views.enqueue_reset") as enqueue:
                self.client.post(self.request_url, {"email": self.user.email}, HTTP_HOST="alternate.example.test")
                enqueue.assert_called_once()
        _run_reset(self.user.email, "192.0.2.2")
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("https://tory.example.test/password/reset/setup/#", mail.outbox[0].body)
        self.assertNotIn("alternate.example.test", mail.outbox[0].body)
        self.assertFalse(PasswordResetLink.objects.filter(token_digest__contains="#").exists())
        link_count = PasswordResetLink.objects.count()
        attempt_count = PasswordResetAttempt.objects.count()
        with override_settings(STAFF_INVITATION_PUBLIC_ORIGIN=""):
            with self.assertRaises(ResetDeliveryError):
                _run_reset(self.user.email, "192.0.2.3")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(PasswordResetLink.objects.count(), link_count)
        self.assertEqual(PasswordResetAttempt.objects.count(), attempt_count)

    def test_dispatch_boundary_releases_capacity_after_disabled_delivery(self):
        from accounts.reset_dispatch import process_reset
        slot = BoundedSemaphore(1)
        self.assertTrue(slot.acquire(blocking=False))
        with patch("accounts.reset_dispatch._slots", slot):
            with override_settings(STAFF_INVITATION_PUBLIC_ORIGIN=""):
                process_reset(self.user.email, "192.0.2.7")
            self.assertFalse(PasswordResetLink.objects.exists())
            self.assertEqual(len(mail.outbox), 0)
            self.assertTrue(slot.acquire(blocking=False))
            process_reset(self.user.email, "192.0.2.7")
            self.assertTrue(slot.acquire(blocking=False))
            slot.release()
        self.assertEqual(PasswordResetLink.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_delivery_failure_does_not_change_password_and_retry_is_possible(self):
        from accounts.reset_dispatch import _run_reset
        from accounts.reset_email import ResetDeliveryError
        with patch("accounts.reset_dispatch.send_reset", side_effect=ResetDeliveryError("failed")):
            with self.assertRaises(ResetDeliveryError):
                _run_reset(self.user.email, "192.0.2.4")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-password-9381"))
        _run_reset(self.user.email, "192.0.2.4")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(list(PasswordResetLink.objects.values_list("status", flat=True)), ["superseded", "pending"])

    def test_csrf_and_read_only_get(self):
        secure = Client(enforce_csrf_checks=True)
        self.assertEqual(secure.get(self.request_url).status_code, 200)
        self.assertEqual(secure.get(self.setup_url).status_code, 200)
        self.assertEqual(secure.post(self.request_url, {"email": self.user.email}).status_code, 403)
        self.assertEqual(secure.post(self.setup_url, {"token": "x", "password": "x"}).status_code, 403)
        self.assertFalse(PasswordResetAttempt.objects.exists())
        self.assertFalse(PasswordResetLink.objects.exists())

    def test_password_errors_retry_and_prior_sessions(self):
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(self.user)
            session = client.session
            session[CREATED_KEY] = timezone.now().timestamp()
            session[ACTIVE_KEY] = timezone.now().timestamp()
            session.save()
        credentials = request_password_reset(self.user.email, "192.0.2.5").credentials
        token = credentials.token
        get_response = self.client.get(self.setup_url)
        self.assertNotIn(token.encode(), get_response.content)
        self.assertIn("no-store", {part.strip() for part in get_response["Cache-Control"].split(",")})
        self.assertEqual(get_response["Referrer-Policy"], "no-referrer")
        mismatch = self.client.post(self.setup_url, {"token": token, "password": "long-password-0001", "password_confirm": "wrong"})
        rejected = self.client.post(self.setup_url, {"token": token, "password": "short", "password_confirm": "short"})
        self.assertFalse(mismatch.json()["ok"] or rejected.json()["ok"])
        self.assertEqual(PasswordResetLink.objects.get(pk=credentials.link.pk).status, "pending")
        valid = self.client.post(self.setup_url, {"token": token, "password": "long-password-0001", "password_confirm": "long-password-0001"})
        self.assertEqual(valid.json(), {"ok": True, "sign_in_url": reverse("login")})
        for response in (mismatch, rejected, valid):
            self.assertNotIn(token.encode(), response.content)
            self.assertNotIn(b"long-password-0001", response.content)
        for client in clients:
            self.assertEqual(client.get("/").status_code, 302)
        self.assertFalse(self.client.post(self.setup_url, {"token": token, "password": "long-password-0001", "password_confirm": "long-password-0001"}).json()["ok"])

    def test_expired_and_superseded_links_fail(self):
        first = request_password_reset(self.user.email, "192.0.2.6").credentials
        second = request_password_reset(self.user.email, "192.0.2.6").credentials
        PasswordResetLink.objects.filter(pk=second.link.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        for token in (first.token, second.token):
            response = self.client.post(self.setup_url, {"token": token, "password": "long-password-0001", "password_confirm": "long-password-0001"})
            self.assertFalse(response.json()["ok"])
            self.assertNotIn(token.encode(), response.content)
