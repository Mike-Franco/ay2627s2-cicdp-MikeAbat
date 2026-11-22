import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse


def staging_env(**overrides):
    env = os.environ.copy()
    env.update({
        "DJANGO_ENV": "staging", "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(60),
        "DJANGO_ALLOWED_HOSTS": "staging.example.test",
    })
    env.pop("DJANGO_HSTS_SECONDS", None)
    env.update(overrides)
    return env


def run_manage(env, *args):
    return subprocess.run([sys.executable, "manage.py", *args], cwd=settings.BASE_DIR, env=env,
                          capture_output=True, text=True, timeout=120)


class SecurityHeaderTests(TestCase):
    def test_pages_cannot_be_framed(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response["X-Frame-Options"], "DENY")

    @override_settings(SECURE_HSTS_SECONDS=3600, SECURE_HSTS_INCLUDE_SUBDOMAINS=False, SECURE_HSTS_PRELOAD=False)
    def test_hsts_header_on_https_without_subdomains_or_preload(self):
        response = self.client.get(reverse("login"), secure=True)
        self.assertEqual(response["Strict-Transport-Security"], "max-age=3600")

    def test_no_hsts_in_test_environment(self):
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)
        response = self.client.get(reverse("login"), secure=True)
        self.assertNotIn("Strict-Transport-Security", response)


class DeploySettingsTests(SimpleTestCase):
    def test_staging_passes_deploy_checks_at_warning_level(self):
        result = run_manage(staging_env(), "check", "--deploy", "--fail-level", "WARNING")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_staging_hsts_defaults_and_override(self):
        probe = ("from django.conf import settings as s; "
                 "print(s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SECURE_HSTS_PRELOAD, s.X_FRAME_OPTIONS)")
        def values(env):
            # The shell prints an auto-import banner first; the probe is the last line.
            return run_manage(env, "shell", "-c", probe).stdout.strip().splitlines()[-1].split()

        self.assertEqual(values(staging_env()), ["3600", "False", "False", "DENY"])
        self.assertEqual(values(staging_env(DJANGO_HSTS_SECONDS="86400"))[0], "86400")
        for bad in ("soon", "-1"):
            with self.subTest(value=bad):
                result = run_manage(staging_env(DJANGO_HSTS_SECONDS=bad), "check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DJANGO_HSTS_SECONDS", result.stderr)


class CspReadyTemplateTests(SimpleTestCase):
    """The proxy's Content-Security-Policy allows no inline styles or scripts."""

    def test_templates_have_no_inline_styles_scripts_or_handlers(self):
        offenders = []
        for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if re.search(r'\sstyle="|<style\b', text):
                offenders.append(f"{path.name}: inline style")
            if re.search(r"\son[a-z]+=", text):
                offenders.append(f"{path.name}: inline event handler")
            for tag in re.findall(r"<script\b[^>]*>", text):
                if "src=" not in tag:
                    offenders.append(f"{path.name}: inline script {tag}")
        self.assertEqual(offenders, [])
