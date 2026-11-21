"""Minimal Tory settings; PostgreSQL is required in every environment."""

import os
import warnings
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def required_env(name):
    value = os.environ.get(name)
    if not value or not value.strip():
        raise ImproperlyConfigured(f"{name} must be set; see .env.example")
    return value


DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").lower()
if DJANGO_ENV not in {"development", "test", "staging", "production"}:
    raise ImproperlyConfigured("DJANGO_ENV must be development, test, staging, or production")

debug_value = os.environ.get("DJANGO_DEBUG", "false").lower()
if debug_value not in {"true", "false"}:
    raise ImproperlyConfigured("DJANGO_DEBUG must be true or false")
DEBUG = debug_value == "true"

SECRET_KEY = required_env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]

if DJANGO_ENV in {"staging", "production"}:
    if DEBUG:
        raise ImproperlyConfigured("DJANGO_DEBUG must be false outside development/test")
    if not os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip():
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be explicit outside development/test")

INSTALLED_APPS = [
    "accounts",
    "inventory_access",
    "catalogue",
    "receiving",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 15},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "inventory_access.context_processors.workspace",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required_env("POSTGRES_DB"),
        "USER": required_env("POSTGRES_USER"),
        "PASSWORD": required_env("POSTGRES_PASSWORD"),
        "HOST": required_env("POSTGRES_HOST"),
        "PORT": required_env("POSTGRES_PORT"),
        # Reuse connections across requests in a worker; health checks drop a
        # stale connection (for example after a database restart) before use.
        # Tests keep per-request connections: threaded tests issue requests from
        # worker threads, and kept-alive connections there would block dropping
        # the test database.
        "CONN_MAX_AGE": 0 if DJANGO_ENV == "test" else 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Singapore"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# collectstatic writes here (the container image runs it at build time) and
# WhiteNoise serves it. Hashed, compressed names are used where the manifest
# is guaranteed to exist; development and test keep plain names.
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if DJANGO_ENV in {"staging", "production"}
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}
if DJANGO_ENV in {"development", "test"}:
    # Outside the container image collectstatic has usually not run; the
    # development static route serves files instead, so the warning is noise.
    warnings.filterwarnings("ignore", message=r"No directory at: .*staticfiles")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Development settings are not a deployment configuration. Staging/production
# require explicit hostnames, TLS/proxy review, secure cookies, and secret storage.
SESSION_COOKIE_SECURE = DJANGO_ENV in {"staging", "production"}
CSRF_COOKIE_SECURE = DJANGO_ENV in {"staging", "production"}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = DJANGO_ENV in {"staging", "production"}
# Platform health probes call the container directly over HTTP.
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

# Set only where the app is reachable solely through the deployment's reverse
# proxy (deploy/docker-compose.prod.yml). The proxy terminates TLS, so trust its
# scheme header for SECURE_SSL_REDIRECT and secure cookies, and take the client
# address it reports so the login throttle sees real visitor IPs.
trusted_proxy_value = os.environ.get("DJANGO_TRUSTED_PROXY", "false").lower()
if trusted_proxy_value not in {"true", "false"}:
    raise ImproperlyConfigured("DJANGO_TRUSTED_PROXY must be true or false")
TRUSTED_PROXY = trusted_proxy_value == "true"
if TRUSTED_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    MIDDLEWARE.insert(0, "config.proxy.TrustedProxyMiddleware")
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"

# Invitation delivery is opt-in. Console and file backends are deliberately not
# configurable here because they would expose a redeemable link.
STAFF_INVITATION_PUBLIC_ORIGIN = os.environ.get("STAFF_INVITATION_PUBLIC_ORIGIN", "")
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
try:
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
except ValueError:
    EMAIL_PORT = 0  # The invitation adapter rejects this before issuance.
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")
PASSWORD_RESET_SMTP_TIMEOUT = 10
