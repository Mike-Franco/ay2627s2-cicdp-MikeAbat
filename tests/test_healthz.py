from unittest import mock

from django.db import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse


class HealthzTests(TestCase):
    def test_reports_ok_without_authentication(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_is_never_cached(self):
        response = self.client.get(reverse("healthz"))

        self.assertIn("no-cache", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_head_is_allowed_and_writes_are_rejected(self):
        self.assertEqual(self.client.head(reverse("healthz")).status_code, 200)
        self.assertEqual(self.client.post(reverse("healthz")).status_code, 405)

    def test_reports_unavailable_when_database_is_unreachable(self):
        with mock.patch("config.health.connection.cursor", side_effect=OperationalError("down")):
            response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable", "database": "unreachable"})

    def test_does_not_leak_database_error_details(self):
        with mock.patch(
            "config.health.connection.cursor",
            side_effect=OperationalError('connection to server at "db" failed: password authentication failed'),
        ):
            response = self.client.get(reverse("healthz"))

        self.assertNotIn(b"password", response.content)
        self.assertNotIn(b"db", response.content.replace(b"database", b""))

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_is_exempt_from_https_redirect(self):
        self.assertEqual(self.client.get(reverse("healthz")).status_code, 200)
        self.assertEqual(self.client.get(reverse("login")).status_code, 301)
