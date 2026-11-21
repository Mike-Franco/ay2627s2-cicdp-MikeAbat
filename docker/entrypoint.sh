#!/bin/sh
# Apply migrations, then hand off to the container command (gunicorn by default).
set -eu

if [ "${DJANGO_MIGRATE_ON_START:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
