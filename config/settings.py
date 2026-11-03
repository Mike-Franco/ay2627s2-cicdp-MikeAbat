"""Minimal Tory settings; PostgreSQL is required in every environment."""

import os
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
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Singapore"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
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
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
