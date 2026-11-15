"""Profile successful login components on an isolated TORY-26 seed clone.

Run with POSTGRES_DB=tory26_benchmark_run1 after cloning the seed. This is a
diagnostic Django test-client measurement, not an HTTP benchmark sample.
"""

import concurrent.futures
import hashlib
import json
import os
import statistics
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

if os.environ.get("POSTGRES_DB") != "tory26_benchmark_run1":
    raise RuntimeError("Diagnostic requires the isolated tory26_benchmark_run1 clone")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402

from accounts import views  # noqa: E402
from accounts.models import User  # noqa: E402


PASSWORD = hashlib.sha256(b"tory26-isolated-local-fixture-v1").hexdigest()
EMAILS = [f"tory26-b1-u{i}@example.test" for i in range(1, 5)] + [
    "tory26-b2-u1@example.test"
]
local = threading.local()
original_check_password = User.check_password
original_authenticate = views.authenticate
original_throttle = views.check_and_authenticate
original_login = views.login


def timed(name, function):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            current = getattr(local, "parts", None)
            if current is not None:
                current[name] = current.get(name, 0.0) + time.perf_counter() - start
    return wrapper


@contextmanager
def sql_timing(parts):
    def wrapper(execute, sql, params, many, context):
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            parts["sql"] = parts.get("sql", 0.0) + time.perf_counter() - start
            parts["sql_count"] = parts.get("sql_count", 0) + 1
    with connection.execute_wrapper(wrapper):
        yield


def worker(email, count):
    client = Client(enforce_csrf_checks=True, HTTP_HOST="127.0.0.1")
    response = client.get("/login/")
    if response.status_code != 200:
        raise RuntimeError(f"Login GET returned {response.status_code}")
    rows = []
    for _ in range(count):
        parts = {}
        local.parts = parts
        start = time.perf_counter()
        try:
            with sql_timing(parts):
                response = client.post("/login/", {
                    "email": email, "password": PASSWORD,
                    "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
                })
        finally:
            parts["total"] = time.perf_counter() - start
            local.parts = None
        if response.status_code != 302:
            raise RuntimeError(f"Login POST returned {response.status_code}")
        rows.append(parts)
    return rows


def summarize(rows):
    keys = ("total", "throttle", "authenticate", "check_password", "login", "sql", "sql_count")
    return {key: {"median": statistics.median(row.get(key, 0) for row in rows),
                  "max": max(row.get(key, 0) for row in rows)} for key in keys}


def main():
    with patch.object(User, "check_password", timed("check_password", original_check_password)), \
         patch.object(views, "authenticate", timed("authenticate", original_authenticate)), \
         patch.object(views, "check_and_authenticate", timed("throttle", original_throttle)), \
         patch.object(views, "login", timed("login", original_login)):
        sequential = worker(EMAILS[0], 3)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            parallel_rows = [row for batch in pool.map(lambda email: worker(email, 4), EMAILS)
                             for row in batch]
    users = list(User.objects.filter(email__in=EMAILS).order_by("email"))
    if len(users) != 5:
        raise RuntimeError("Expected five isolated fixture users")
    def check_only(user):
        start = time.perf_counter()
        if not user.check_password(PASSWORD):
            raise RuntimeError("Fixture password verification failed")
        return time.perf_counter() - start
    sequential_hashes = [check_only(user) for user in users]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        parallel_hashes = list(pool.map(check_only, users))
    evidence = {
        "database": "tory26_benchmark_run1",
        "sequential_summary": summarize(sequential),
        "five_clients_summary": summarize(parallel_rows),
        "sequential_samples": sequential,
        "five_clients_samples": parallel_rows,
        "password_only_sequential_seconds": sequential_hashes,
        "password_only_parallel_seconds": parallel_hashes,
        "method": "Django test client on isolated seed clone; normal auth, throttle, sessions and middleware",
    }
    output = Path(__file__).resolve().parent.parent / "benchmark-results/tory26-login-diagnostic.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(output), "sequential": evidence["sequential_summary"],
                      "five_clients": evidence["five_clients_summary"]}, indent=2))


if __name__ == "__main__":
    main()
