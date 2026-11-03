"""Framework and real-PostgreSQL smoke checks; no Tory feature acceptance yet."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import SimpleTestCase, TestCase


class ConfigurationSmokeTests(SimpleTestCase):
    def test_django_system_check_passes(self):
        call_command("check")

    def test_default_backend_is_postgresql(self):
        self.assertEqual(connection.vendor, "postgresql")


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
