"""Focused PostgreSQL reset-core cases; written without execution in this increment."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as utc
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from accounts.models import PasswordResetAttempt, PasswordResetLink
from accounts.password_resets import PasswordResetError, redeem_password_reset, request_password_reset
from accounts.sessions import ACTIVE_KEY, CREATED_KEY


ANCHOR = datetime(2026, 11, 17, 2, 0, tzinfo=utc.utc)
PASSWORD = "fresh-reset-password-9371"


class PasswordResetCoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="person@example.test", password="old-password-9381")

    def issue(self, email="person@example.test", ip="127.0.0.1", at=ANCHOR):
        return request_password_reset(email, ip, at=at)

    def test_latest_only_single_use_and_private_result(self):
        first = self.issue()
        second = self.issue(at=ANCHOR + timedelta(seconds=1))
        self.assertEqual(first.acknowledgement, second.acknowledgement)
        self.assertNotIn(first.credentials.token, repr(first))
        self.assertNotIn(first.credentials.token, repr(first.credentials))
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(first.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=1))
        redeem_password_reset(second.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=1))
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(second.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=2))
        self.assertEqual(PasswordResetLink.objects.filter(status="redeemed").count(), 1)

    def test_expiry_equality_and_policy_rollback(self):
        result = self.issue()
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(result.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=30))
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(result.credentials.token, "short", at=ANCHOR + timedelta(minutes=1))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-password-9381"))
        self.assertEqual(PasswordResetLink.objects.get(pk=result.credentials.link.pk).status, "pending")

    def test_processing_crosses_expiry_and_rolls_back(self):
        result = self.issue()
        with patch("accounts.password_resets._operation_time", side_effect=[
            ANCHOR + timedelta(minutes=29), ANCHOR + timedelta(minutes=30)
        ]):
            with self.assertRaises(PasswordResetError):
                redeem_password_reset(result.credentials.token, PASSWORD)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-password-9381"))
        self.assertEqual(PasswordResetLink.objects.get(pk=result.credentials.link.pk).status, "pending")

    def test_invitation_purpose_cannot_redeem_reset(self):
        from accounts.invitations import TOKEN_PURPOSE as INVITATION_PURPOSE
        import hashlib
        self.assertNotEqual(INVITATION_PURPOSE, b"tory:password-reset:v1\0")
        result = self.issue()
        self.assertNotEqual(
            hashlib.sha256(INVITATION_PURPOSE + result.credentials.token.encode()).hexdigest(),
            result.credentials.link.token_digest,
        )
        with self.assertRaises(PasswordResetError):
            redeem_password_reset("an-invitation-only-token", PASSWORD)

    def test_inactive_account_and_password_state_change_fail_redemption(self):
        result = self.issue()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(result.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=1))
        self.user.is_active = True
        self.user.set_password("changed-outside-reset-9381")
        self.user.save(update_fields=["is_active", "password"])
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(result.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=1))

    def test_open_left_hour_boundary(self):
        for _ in range(3):
            self.issue("missing@example.test")
        self.assertEqual(PasswordResetAttempt.objects.count(), 3)
        self.issue("missing@example.test", at=ANCHOR + timedelta(hours=1))
        self.assertEqual(PasswordResetAttempt.objects.count(), 4)

    def test_unknown_inactive_and_independent_limits(self):
        unknown = self.issue("missing@example.test")
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        inactive = self.issue()
        self.assertEqual(unknown.acknowledgement, inactive.acknowledgement)
        self.assertIsNone(unknown.credentials)
        self.assertIsNone(inactive.credentials)
        self.assertEqual(PasswordResetAttempt.objects.count(), 2)
        for i in range(2):
            self.issue("missing@example.test", ip=str(i))
        self.assertEqual(PasswordResetAttempt.objects.filter(identity_key=PasswordResetAttempt.objects.first().identity_key).count(), 3)
        for i in range(18):
            self.issue(f"other{i}@example.test")
        self.assertEqual(PasswordResetAttempt.objects.filter(ip_key=PasswordResetAttempt.objects.first().ip_key).count(), 20)

    def test_old_sessions_denied_and_fresh_login_works(self):
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(self.user)
            session = client.session
            session[CREATED_KEY] = timezone.now().timestamp()
            session[ACTIVE_KEY] = timezone.now().timestamp()
            session.save()
            self.assertEqual(client.get("/").status_code, 200)
        result = request_password_reset(self.user.email, "127.0.0.1")
        redeem_password_reset(result.credentials.token, PASSWORD)
        for client in clients:
            self.assertEqual(client.get("/").status_code, 302)
        fresh = Client()
        self.assertTrue(fresh.login(username=self.user.email, password=PASSWORD))


class PasswordResetRaceTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="race@example.test", password="old-password-9381")

    def parallel(self, operation):
        barrier = Barrier(2)
        def worker(index):
            try:
                barrier.wait(timeout=10)
                return operation(index)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, i) for i in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_concurrent_issuance_and_redemption(self):
        issued = self.parallel(lambda i: request_password_reset(self.user.email, str(i)))
        self.assertEqual(PasswordResetLink.objects.filter(status="pending").count(), 1)
        current = PasswordResetLink.objects.get(status="pending")
        token = next(result.credentials.token for result in issued if result.credentials.link.pk == current.pk)
        def redeem(_):
            try:
                redeem_password_reset(token, PASSWORD)
                return True
            except PasswordResetError:
                return False
        self.assertEqual(sorted(self.parallel(redeem)), [False, True])

    def test_concurrent_identity_quota_boundary(self):
        for _ in range(2):
            request_password_reset("missing@example.test", "seed")
        results = self.parallel(lambda i: request_password_reset("missing@example.test", str(i)))
        self.assertEqual(len(results), 2)
        self.assertEqual(PasswordResetAttempt.objects.count(), 3)
