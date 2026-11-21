# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.13-slim

# Build stage: install pinned dependencies into an isolated virtualenv.
FROM ${PYTHON_IMAGE} AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install --require-virtualenv -r /tmp/requirements.txt

# Runtime stage: application code and the virtualenv only, run as non-root.
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    DJANGO_ENV=production \
    WEB_CONCURRENCY=3
RUN groupadd --system --gid 10001 tory \
    && useradd --system --uid 10001 --gid tory --create-home --home-dir /home/tory --shell /usr/sbin/nologin tory
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# Code stays owned by root so the runtime user cannot modify it.
COPY . .
# Settings require these at import time. The values are throwaway placeholders
# scoped to this one command; they are not stored in the image environment.
RUN DJANGO_SECRET_KEY=collectstatic-build-only-placeholder \
    DJANGO_ALLOWED_HOSTS=localhost \
    POSTGRES_DB=unused POSTGRES_USER=unused POSTGRES_PASSWORD=unused \
    POSTGRES_HOST=unused POSTGRES_PORT=5432 \
    python manage.py collectstatic --noinput \
    && chmod 0755 docker/entrypoint.sh
USER tory:tory
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-"]
