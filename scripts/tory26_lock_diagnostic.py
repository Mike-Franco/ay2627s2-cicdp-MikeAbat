"""Time individual login advisory locks on an isolated TORY-26 clone.

Diagnostic only: Django test-client requests, not approved HTTP benchmark
samples. The SQL wrapper calls the original execute exactly once. No Tory
authentication, hashing, throttle, middleware, or rate-limit code is changed.
"""

import concurrent.futures
import ctypes
import hashlib
import json
import os
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

if os.name != "nt" or os.environ.get("POSTGRES_DB") != "tory26_benchmark_run1":
    raise RuntimeError("Run only on Windows against isolated tory26_benchmark_run1")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import psycopg  # noqa: E402
from django.db import connection, connections  # noqa: E402
from django.test import Client  # noqa: E402

from accounts.throttle import _key  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "benchmark-results/tory26-lock-diagnostic.json"
PASSWORD = hashlib.sha256(b"tory26-isolated-local-fixture-v1").hexdigest()
EMAILS = [f"tory26-b1-u{i}@example.test" for i in range(1, 5)] + [
    "tory26-b2-u1@example.test"
]
SOURCE_IP = "127.0.0.1"


class FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


def system_times():
    idle, kernel, user = FileTime(), FileTime(), FileTime()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        raise OSError("GetSystemTimes failed")
    return tuple((part.high << 32) + part.low for part in (idle, kernel, user))


def lock_id(kind, value):
    return int.from_bytes(bytes.fromhex(_key(kind, value)[:16]), "big", signed=True)


def cpu_observer(stop, phase, samples):
    prior = system_times()
    prior_at = time.perf_counter()
    while not stop.wait(0.25):
        current = system_times()
        now = time.perf_counter()
        idle = current[0] - prior[0]
        total = current[1] - prior[1] + current[2] - prior[2]
        if total > 0:
            samples.append({"phase": phase[0], "at_seconds": now,
                            "system_cpu_percent": 100 * (total - idle) / total,
                            "interval_seconds": now - prior_at})
        prior, prior_at = current, now


def lock_observer(stop, samples):
    with psycopg.connect(
        dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"], host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"], autocommit=True,
    ) as observer:
        while not stop.wait(0.05):
            count = observer.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = %s AND wait_event_type = 'Lock' AND wait_event = 'advisory'",
                [os.environ["POSTGRES_DB"]],
            ).fetchone()[0]
            samples.append({"at_seconds": time.perf_counter(), "advisory_waiters": count})


def worker(index, count):
    email = EMAILS[index]
    expected = {lock_id("identity", email): "identity",
                lock_id("ip", SOURCE_IP): "source_ip"}
    client = Client(enforce_csrf_checks=True, HTTP_HOST=SOURCE_IP, REMOTE_ADDR=SOURCE_IP)
    if client.get("/login/").status_code != 200:
        raise RuntimeError("Login GET failed")
    rows = []
    try:
        for _ in range(count):
            calls = []

            def observe(execute, sql, params, many, context):
                is_lock = sql.strip().lower().startswith("select pg_advisory_xact_lock(")
                start = time.perf_counter()
                try:
                    return execute(sql, params, many, context)
                finally:
                    if is_lock:
                        label = expected.get(params[0])
                        if label is None:
                            raise RuntimeError("Unexpected advisory lock identifier")
                        calls.append({"lock": label, "elapsed_seconds": time.perf_counter() - start})

            started = time.perf_counter()
            with connection.execute_wrapper(observe):
                response = client.post("/login/", {
                    "email": email, "password": PASSWORD,
                    "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
                })
            total = time.perf_counter() - started
            if response.status_code != 302 or {call["lock"] for call in calls} != {"identity", "source_ip"}:
                raise RuntimeError(f"Unexpected login result or lock calls: HTTP {response.status_code}")
            rows.append({"client": index + 1, "request_seconds": total, "lock_calls": calls})
    finally:
        connections.close_all()
    return rows


def medians(rows):
    return {name: statistics.median(
        next(call["elapsed_seconds"] for call in row["lock_calls"] if call["lock"] == name)
        for row in rows
    ) for name in ("identity", "source_ip")}


def main():
    if OUTPUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing evidence: {OUTPUT}")
    cpu_samples, wait_samples = [], []
    phase = ["idle_baseline"]
    cpu_stop = threading.Event()
    cpu_thread = threading.Thread(target=cpu_observer, args=(cpu_stop, phase, cpu_samples))
    cpu_thread.start()
    try:
        time.sleep(3)
        phase[0] = "sequential_login"
        sequential = worker(0, 3)
        phase[0] = "five_shared_ip_logins"
        wait_stop = threading.Event()
        wait_thread = threading.Thread(target=lock_observer, args=(wait_stop, wait_samples))
        wait_thread.start()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                parallel = [row for batch in pool.map(lambda i: worker(i, 4), range(5))
                            for row in batch]
        finally:
            wait_stop.set()
            wait_thread.join()
    finally:
        cpu_stop.set()
        cpu_thread.join()
    baseline = [sample["system_cpu_percent"] for sample in cpu_samples
                if sample["phase"] == "idle_baseline"]
    evidence = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "tory26_benchmark_run1",
        "method": "Django test client; SQL execute_wrapper per advisory call; original execute once; Windows GetSystemTimes CPU sampling; read-only pg_stat_activity waiter sampling",
        "source_ip": SOURCE_IP,
        "sequential": sequential,
        "five_shared_ip": parallel,
        "cpu_samples": cpu_samples,
        "advisory_waiter_samples": wait_samples,
        "summary": {
            "sequential_lock_median_seconds": medians(sequential),
            "five_shared_ip_lock_median_seconds": medians(parallel),
            "sequential_request_median_seconds": statistics.median(row["request_seconds"] for row in sequential),
            "five_shared_ip_request_median_seconds": statistics.median(row["request_seconds"] for row in parallel),
            "idle_baseline_cpu_median_percent": statistics.median(baseline),
            "peak_observed_advisory_waiters": max(
                (sample["advisory_waiters"] for sample in wait_samples), default=0
            ),
        },
    }
    with OUTPUT.open("x", encoding="utf-8") as output:
        json.dump(evidence, output, indent=2)
        output.write("\n")
    print(json.dumps({"raw_evidence": str(OUTPUT), **evidence["summary"]}, indent=2))


if __name__ == "__main__":
    main()
