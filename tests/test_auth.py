from datetime import datetime, timedelta, timezone as utc_timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import throttle
from accounts.models import LoginFailure
from accounts.sessions import ABSOLUTE_SECONDS, IDLE_SECONDS
from accounts.views import GENERIC_ERROR


BASE = datetime(2026, 11, 3, 1, 0, tzinfo=utc_timezone.utc)
PASSWORD = "test-only-strong-password"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="person@example.test", password=PASSWORD
        )

    def login(self, email="person@example.test", password=PASSWORD, **extra):
        return self.client.post(
            reverse("login"), {"email": email, "password": password, **extra}
        )

    def test_email_identity_is_unique_without_case_sensitivity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            direct = get_user_model()(email="PERSON@EXAMPLE.TEST")
            direct.set_password(PASSWORD)
            direct.save()
        self.assertEqual(self.user.email, "person@example.test")
        self.assertNotEqual(self.user.password, PASSWORD)

    def test_successful_case_insensitive_login_and_authenticated_home(self):
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            response = self.login(email="PERSON@EXAMPLE.TEST")
            self.assertRedirects(response, reverse("home"))
            home = self.client.get(reverse("home"))
            self.assertTrue(self.client.session.get("_auth_user_id"))
        self.assertContains(home, "Inventory dashboard")
        self.assertTrue(self.client.cookies["sessionid"]["httponly"])
        self.assertEqual(self.client.cookies["sessionid"]["samesite"], "Lax")

    def test_existing_short_password_can_still_sign_in(self):
        legacy_password = "legacy-short"
        legacy_user = get_user_model().objects.create_user(
            email="legacy-password@example.test",
            password=legacy_password,
        )

        with patch("accounts.sessions.timezone.now", return_value=BASE):
            response = self.login(email=legacy_user.email, password=legacy_password)
            self.assertRedirects(response, reverse("home"))
            self.assertEqual(self.client.session.get("_auth_user_id"), str(legacy_user.pk))

    def test_wrong_unknown_and_inactive_use_generic_feedback(self):
        for email, password in [
            ("person@example.test", "wrong"),
            ("unknown@example.test", "wrong"),
        ]:
            response = self.login(email=email, password=password)
            self.assertContains(response, GENERIC_ERROR, status_code=200)
            self.assertNotIn("_auth_user_id", self.client.session)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.login()
        self.assertContains(response, GENERIC_ERROR, status_code=200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unauthenticated_home_is_denied(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("login"))

    def test_logout_requires_post_and_ends_current_session(self):
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            self.login()
            self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
            self.assertContains(self.client.get(reverse("home")), "Inventory dashboard")
            self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
        self.assertRedirects(self.client.get(reverse("home")), reverse("login"))

    def test_inactive_user_old_session_cannot_access_home(self):
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            self.login()
            self.user.is_active = False
            self.user.save(update_fields=["is_active"])
            self.assertRedirects(self.client.get(reverse("home")), reverse("login"))
            self.user.is_active = True
            self.user.save(update_fields=["is_active"])
            self.assertRedirects(self.client.get(reverse("home")), reverse("login"))

    def test_idle_boundary_and_successful_activity(self):
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            self.login()
        with patch("accounts.sessions.timezone.now", return_value=BASE + timedelta(seconds=IDLE_SECONDS - 1)):
            self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        with patch("accounts.sessions.timezone.now", return_value=BASE + timedelta(seconds=2 * IDLE_SECONDS - 2)):
            self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        with patch("accounts.sessions.timezone.now", return_value=BASE + timedelta(seconds=3 * IDLE_SECONDS - 2)):
            self.assertRedirects(self.client.get(reverse("home")), reverse("login"))

    def test_idle_exactly_thirty_minutes_expires(self):
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            self.login()
        with patch("accounts.sessions.timezone.now", return_value=BASE + timedelta(seconds=IDLE_SECONDS)):
            self.assertRedirects(self.client.get(reverse("home")), reverse("login"))

    def test_absolute_expiry_is_not_extended_by_activity(self):
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            self.login()
        for minutes in range(20, 8 * 60, 20):
            with patch("accounts.sessions.timezone.now", return_value=BASE + timedelta(minutes=minutes)):
                self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        with patch("accounts.sessions.timezone.now", return_value=BASE + timedelta(seconds=ABSOLUTE_SECONDS)):
            self.assertRedirects(self.client.get(reverse("home")), reverse("login"))

    def test_safe_local_next_and_reject_external_redirect(self):
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            response = self.login(next="/local/path/")
        self.assertEqual(response["Location"], "/local/path/")
        self.client.post(reverse("logout"))
        with patch("accounts.sessions.timezone.now", return_value=BASE):
            response = self.login(next="https://attacker.example/path")
        self.assertEqual(response["Location"], reverse("home"))

    def test_csrf_rejects_login_and_logout_without_mutation(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("login"), {"email": self.user.email, "password": PASSWORD})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertEqual(LoginFailure.objects.count(), 0)

        client.get(reverse("login"))
        token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("login"), {"email": self.user.email, "password": PASSWORD},
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(client.session.get("_auth_user_id"))
        self.assertEqual(client.post(reverse("logout")).status_code, 403)
        self.assertTrue(client.session.get("_auth_user_id"))
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(reverse("logout"), HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ThrottleTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user(email="person@example.test", password=PASSWORD)

    def post(self, email, password="wrong", ip="192.0.2.1"):
        return self.client.post(
            reverse("login"), {"email": email, "password": password},
            REMOTE_ADDR=ip,
        )

    def test_identity_fifth_failure_allowed_then_next_attempt_throttled(self):
        with patch("accounts.throttle.timezone.now", return_value=BASE):
            for _ in range(5):
                self.assertContains(self.post("PERSON@EXAMPLE.TEST"), GENERIC_ERROR)
            self.assertEqual(LoginFailure.objects.count(), 5)
            self.assertContains(self.post("person@example.test", PASSWORD), GENERIC_ERROR)
        self.assertEqual(LoginFailure.objects.count(), 5)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ip_twentieth_failure_allowed_then_other_identity_throttled(self):
        with patch("accounts.throttle.timezone.now", return_value=BASE):
            for i in range(20):
                self.assertContains(self.post(f"unknown{i}@example.test"), GENERIC_ERROR)
            self.assertContains(self.post("person@example.test", PASSWORD), GENERIC_ERROR)
        self.assertEqual(LoginFailure.objects.count(), 20)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_independent_ip_and_identity_keys_and_window_boundary(self):
        with patch("accounts.throttle.timezone.now", return_value=BASE):
            for _ in range(5):
                self.post("person@example.test", ip="192.0.2.1")
            self.assertContains(self.post("PERSON@example.test", PASSWORD, ip="192.0.2.2"), GENERIC_ERROR)
        with patch("accounts.throttle.timezone.now", return_value=BASE + timedelta(minutes=15)):
            response = self.post("person@example.test", PASSWORD, ip="192.0.2.2")
        self.assertEqual(response["Location"], reverse("home"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentThrottleTests(TransactionTestCase):
    def test_competing_failures_share_postgresql_limit(self):
        barrier = Barrier(6)

        def attempt(i):
            try:
                close_old_connections()
                client = Client()
                barrier.wait(timeout=10)
                return client.post(
                    reverse("login"),
                    {"email": "shared@example.test", "password": "wrong"},
                    REMOTE_ADDR=f"192.0.2.{i + 1}",
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(attempt, range(6)))
        self.assertEqual(results, [200] * 6)
        self.assertEqual(LoginFailure.objects.count(), 5)

    def _in_thread(self, function):
        def run():
            try:
                close_old_connections()
                return function()
            finally:
                connections.close_all()
        return run

    def test_slow_password_check_does_not_block_same_key_attempt(self):
        started, release = Event(), Event()

        def slow_authenticate(email, password):
            started.set()
            self.assertTrue(release.wait(timeout=20))
            return None

        attempt = self._in_thread(lambda: throttle.check_and_authenticate(
            "same@example.test", "wrong", "192.0.2.9", slow_authenticate))
        with ThreadPoolExecutor(max_workers=2) as pool:
            slow = pool.submit(attempt)
            self.assertTrue(started.wait(timeout=10))
            try:
                # Before TORY-46 this waited on the advisory lock until the slow
                # check finished, so it would time out here.
                fast = pool.submit(self._in_thread(lambda: throttle.check_and_authenticate(
                    "same@example.test", "wrong", "192.0.2.9", lambda email, password: None)))
                self.assertEqual(fast.result(timeout=5), (None, False))
                self.assertFalse(slow.done())
            finally:
                release.set()
            self.assertEqual(slow.result(timeout=10), (None, False))
        self.assertEqual(LoginFailure.objects.count(), 2)

    def test_in_flight_attempt_counts_towards_limit_until_it_succeeds(self):
        identity_key = throttle._key("identity", "busy@example.test")
        ip_key = throttle._key("ip", "192.0.2.10")
        for _ in range(throttle.IDENTITY_LIMIT - 1):
            LoginFailure.objects.create(identity_key=identity_key, ip_key=ip_key, occurred_at=timezone.now())
        started, release = Event(), Event()
        user = get_user_model()(email="busy@example.test")

        def slow_success(email, password):
            started.set()
            self.assertTrue(release.wait(timeout=20))
            return user

        with ThreadPoolExecutor(max_workers=1) as pool:
            slow = pool.submit(self._in_thread(lambda: throttle.check_and_authenticate(
                "busy@example.test", "right", "192.0.2.10", slow_success)))
            self.assertTrue(started.wait(timeout=10))
            try:
                self.assertEqual(
                    throttle.check_and_authenticate(
                        "BUSY@example.test", "right", "192.0.2.10", lambda email, password: user),
                    (None, True),
                )
            finally:
                release.set()
            self.assertEqual(slow.result(timeout=10), (user, False))
        self.assertEqual(LoginFailure.objects.count(), throttle.IDENTITY_LIMIT - 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ThrottleReservationTests(TestCase):
    def test_success_removes_only_its_own_reservation(self):
        for _ in range(2):
            throttle.check_and_authenticate("keep@example.test", "wrong", "192.0.2.11", lambda e, p: None)
        user = get_user_model()(email="keep@example.test")
        self.assertEqual(
            throttle.check_and_authenticate("keep@example.test", "right", "192.0.2.11", lambda e, p: user),
            (user, False),
        )
        self.assertEqual(LoginFailure.objects.count(), 2)

    def test_error_during_password_check_stays_counted(self):
        def broken(email, password):
            raise RuntimeError("hasher failed")

        with self.assertRaises(RuntimeError):
            throttle.check_and_authenticate("crash@example.test", "pw", "192.0.2.12", broken)
        self.assertEqual(LoginFailure.objects.count(), 1)
