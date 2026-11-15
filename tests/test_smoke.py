"""Framework and real-PostgreSQL smoke checks; no Tory feature acceptance yet."""

from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import SimpleTestCase, TestCase
from django.urls import resolve
from django.views.static import serve as serve_static


class ConfigurationSmokeTests(SimpleTestCase):
    def test_django_system_check_passes(self):
        call_command("check")

    def test_default_backend_is_postgresql(self):
        self.assertEqual(connection.vendor, "postgresql")

    @skipUnless(settings.DJANGO_ENV == "development" and not settings.DEBUG,
                "Only the local development static route is under test")
    def test_local_static_route_is_limited_to_project_assets(self):
        match = resolve("/static/tory/app.css")
        self.assertIs(match.func, serve_static)
        self.assertEqual(match.kwargs["document_root"], settings.BASE_DIR / "static")
        self.assertFalse(match.kwargs["show_indexes"])
        response = self.client.get("/static/tory/app.css")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/css"))
        self.assertEqual(self.client.get("/static/").status_code, 404)


class PostgreSQLSmokeTests(TestCase):
    def test_orm_writes_and_reads(self):
        self.assertEqual(connection.vendor, "postgresql")
        user = get_user_model().objects.create_user(
            email="smoke@example.test", password="test-only-password"
        )
        self.assertEqual(
            get_user_model().objects.get(pk=user.pk).email, "smoke@example.test"
        )

    def test_fresh_test_database_applies_standard_migrations(self):
        self.assertEqual(connection.vendor, "postgresql")
        applied = MigrationRecorder(connection).applied_migrations()
        self.assertIn(("auth", "0001_initial"), applied)
        self.assertIn(("contenttypes", "0001_initial"), applied)
