"""Focused PostgreSQL reset-core cases; written without execution in this increment."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as utc
from threading import Barrier, Event, Lock
from time import monotonic
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from accounts.models import PasswordResetAttempt, PasswordResetLink
from accounts.password_resets import PasswordResetError, redeem_password_reset, request_password_reset
from accounts.sessions import ACTIVE_KEY, CREATED_KEY


ANCHOR = datetime(2026, 11, 17, 2, 0, tzinfo=utc.utc)
PASSWORD = "fresh-reset-password-9371"


class ControlledClock:
    def __init__(self, value):
        self.value = value
        self.lock = Lock()

    def __call__(self):
        with self.lock:
            return self.value

    def set(self, value):
        with self.lock:
            self.value = value


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

    def test_password_change_alone_invalidates_link(self):
        result = self.issue()
        self.user.set_password("changed-outside-reset-9382")
        self.user.save(update_fields=["password"])
        with self.assertRaises(PasswordResetError):
            redeem_password_reset(result.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=1))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("changed-outside-reset-9382"))
        self.assertEqual(PasswordResetLink.objects.get(pk=result.credentials.link.pk).status, "pending")

    def test_link_stays_valid_when_password_is_unchanged(self):
        result = self.issue()
        self.user.last_login = ANCHOR
        self.user.save(update_fields=["last_login"])
        redeem_password_reset(result.credentials.token, PASSWORD, at=ANCHOR + timedelta(minutes=1))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
        self.assertEqual(PasswordResetLink.objects.get(pk=result.credentials.link.pk).status, "redeemed")

    def test_password_fingerprint_is_keyed_hmac_of_stored_hash(self):
        from django.utils.crypto import salted_hmac
        from accounts.password_resets import PASSWORD_FINGERPRINT_SALT
        stored = self.issue().credentials.link.password_digest
        self.assertEqual(stored, salted_hmac(PASSWORD_FINGERPRINT_SALT, self.user.password, algorithm="sha256").hexdigest())
        with self.settings(SECRET_KEY="a-different-secret-key-for-this-test-only-0123456789"):
            self.assertNotEqual(stored, salted_hmac(PASSWORD_FINGERPRINT_SALT, self.user.password, algorithm="sha256").hexdigest())

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
                close_old_connections()
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

    def test_ip_limit_blocks_another_eligible_identity(self):
        ip = "198.51.100.20"
        for index in range(20):
            request_password_reset(f"unknown-{index}@example.test", ip)
        result = request_password_reset(self.user.email, ip)
        self.assertIsNone(result.credentials)
        self.assertEqual(PasswordResetAttempt.objects.count(), 20)
        self.assertFalse(PasswordResetLink.objects.exists())

    def test_concurrent_ip_quota_boundary_for_distinct_identities(self):
        ip = "198.51.100.21"
        for index in range(19):
            request_password_reset(f"unknown-{index}@example.test", ip)
        other = get_user_model().objects.create_user(email="other-race@example.test", password="old-password-9381")
        results = self.parallel(lambda index: request_password_reset(
            [self.user.email, other.email][index], ip
        ))
        self.assertEqual(sum(result.credentials is not None for result in results), 1)
        self.assertEqual(PasswordResetAttempt.objects.count(), 20)
        self.assertEqual(PasswordResetLink.objects.count(), 1)

    def test_user_row_wait_uses_post_lock_clock(self):
        self.assertEqual(connection.vendor, "postgresql")
        before = ANCHOR
        after = ANCHOR + timedelta(minutes=4)
        clock = ControlledClock(before)
        worker_at_account_lock = Event()
        worker_pid = []
        from accounts import password_resets
        original_lock = password_resets._lock

        def observe_lock(key):
            original_lock(key)
            if not worker_at_account_lock.is_set():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    worker_pid.append(cursor.fetchone()[0])
                worker_at_account_lock.set()

        def worker():
            try:
                close_old_connections()
                return request_password_reset(self.user.email, "198.51.100.22")
            finally:
                connections.close_all()

        with patch("accounts.password_resets._lock", observe_lock), patch(
            "accounts.password_resets.timezone.now", clock
        ), ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=self.user.pk)
                future = pool.submit(worker)
                self.assertTrue(worker_at_account_lock.wait(timeout=10))
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [worker_pid[0]])
                        row = cursor.fetchone()
                    if row and row[0] == "Lock":
                        break
                else:
                    self.fail("Reset worker did not reach the user-row lock wait.")
                clock.set(after)
            result = future.result(timeout=15)
        attempt = PasswordResetAttempt.objects.get()
        self.assertEqual(attempt.requested_at, after)
        self.assertEqual(result.credentials.link.issued_at, after)
        self.assertEqual(result.credentials.link.expires_at, after + timedelta(minutes=30))
