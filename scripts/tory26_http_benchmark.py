"""Run TORY-26 HTTP measurements only on isolated PostgreSQL clones.

Load the normal local environment first, then invoke this script. It creates
fresh tory26_benchmark_* databases, never writes to tory or the TORY-25 copy.
Raw evidence is written after each run; inspect it before making a formal claim.
"""

import argparse
import concurrent.futures
import hashlib
import http.cookiejar
import json
import os
import platform
import secrets
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "benchmark-results" / "tory26-local.json"
HOST = "127.0.0.1"
PORT = 8002
BASE = f"http://{HOST}:{PORT}"
RUN_DATABASES = tuple(f"tory26_benchmark_run{i}" for i in range(1, 4))
CSV_DATABASE = "tory26_benchmark_csv"
SEED_DB = "tory26_benchmark_seed"
PASSWORD = hashlib.sha256(b"tory26-isolated-local-fixture-v1").hexdigest()
ALL_DATABASES = (SEED_DB,) + RUN_DATABASES + (CSV_DATABASE,)
CLASSES = ("inventory_view", "inventory_products", "stock_in", "stock_out", "login", "forecast_reorder")


def maintenance_connection():
    return psycopg.connect(
        dbname="postgres", user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"], host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"], autocommit=True,
    )


def database_exists(name):
    with maintenance_connection() as connection:
        return connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is not None


def drop_database(name):
    if name not in ALL_DATABASES:
        raise RuntimeError("Refusing to drop an unrecognized database")
    with maintenance_connection() as connection:
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def create_database(name, template="template0"):
    if name not in ALL_DATABASES or template not in ("template0", SEED_DB):
        raise RuntimeError("Refusing an unrecognized database or template")
    if database_exists(name):
        raise RuntimeError(f"Database {name} already exists; do not overwrite it")
    with maintenance_connection() as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
            sql.Identifier(name), sql.Identifier(template)))


def database_env(name):
    if name not in ALL_DATABASES:
        raise RuntimeError("Refusing to configure an unrecognized database")
    env = os.environ.copy()
    env["POSTGRES_DB"] = name
    env["DJANGO_ALLOWED_HOSTS"] = "127.0.0.1,localhost"
    env["DJANGO_DEBUG"] = "false"
    return env


def migrate_seed(output_path):
    create_database(SEED_DB)
    env = database_env(SEED_DB)
    subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"],
                   cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, "-m", "scripts.tory26_seed", str(output_path)],
                   cwd=ROOT, env=env, check=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class BrowserClient:
    def __init__(self, email, workload):
        self.email = email
        self.workload = workload
        self.jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar), NoRedirect())
        self.lock = threading.Lock()

    def csrf(self):
        for cookie in self.jar:
            if cookie.name == "csrftoken":
                return cookie.value
        raise RuntimeError("CSRF cookie was not set")

    def request(self, path, fields=None, raw=None, content_type=None):
        headers = {}
        data = None
        if fields is not None:
            data = urlencode(fields).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif raw is not None:
            data = raw
            headers["Content-Type"] = content_type
        if data is not None:
            headers["X-CSRFToken"] = self.csrf()
        request = Request(BASE + path, data=data, headers=headers)
        start = time.perf_counter()
        try:
            response = self.opener.open(request, timeout=30)
        except HTTPError as error:
            response = error
        body = response.read()
        elapsed = time.perf_counter() - start
        return elapsed, response.code, body

    def login(self):
        with self.lock:
            _, status, _ = self.request("/login/")
            if status != 200:
                raise RuntimeError(f"Login page returned {status}")
            _, status, _ = self.request("/login/", {"email": self.email, "password": PASSWORD})
            if status != 302:
                raise RuntimeError(f"Login POST returned {status}")

    def timed(self, kind):
        inventory = self.workload["inventory_id"]
        product = self.workload["product_id"]
        paths = {
            "inventory_view": f"/inventories/{inventory}/",
            "inventory_products": f"/inventories/{inventory}/products/",
            "stock_in": f"/inventories/{inventory}/products/{product}/receive/",
            "stock_out": f"/inventories/{inventory}/products/{product}/issue/",
            "login": "/login/",
            "forecast_reorder": f"/inventories/{inventory}/products/{product}/forecast/",
        }
        fields = None
        if kind == "stock_in":
            fields = {"request_token": str(uuid.uuid4()), "quantity_units": "1", "expiry_date": ""}
        elif kind == "stock_out":
            fields = {"quantity_units": "1"}
        elif kind == "login":
            fields = {"email": self.email, "password": PASSWORD}
        with self.lock:
            duration, status, body = self.request(paths[kind], fields)
        expected = 302 if fields is not None else 200
        if status != expected:
            raise RuntimeError(f"{kind} returned HTTP {status}, expected {expected}")
        return duration


def start_server(database, log_path):
    log = log_path.open("wb")
    started = time.perf_counter()
    process = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "--noreload", f"{HOST}:{PORT}"],
        cwd=ROOT, env=database_env(database), stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError(f"Server exited; inspect {log_path}")
            try:
                with build_opener(NoRedirect()).open(BASE + "/login/", timeout=1) as response:
                    response.read()
                    return process, log, time.perf_counter() - started
            except (URLError, TimeoutError):
                time.sleep(0.25)
        raise RuntimeError(f"Server did not start; inspect {log_path}")
    except BaseException:
        process.terminate()
        process.wait(timeout=10)
        log.close()
        raise


def stop_server(process, log):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    log.close()


def fixture_counts(database):
    env = database_env(database)
    with psycopg.connect(dbname=database, user=env["POSTGRES_USER"],
                         password=env["POSTGRES_PASSWORD"], host=env["POSTGRES_HOST"],
                         port=env["POSTGRES_PORT"]) as connection:
        return {name: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for name, table in (("receipts", "receiving_receiptauditevent"),
                                    ("issues", "receiving_demandauditevent"),
                                    ("imports", "receiving_stockimport"))}


def sample_class(kind, clients, count):
    durations = [None] * count
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(clients[index % 5].timed, kind) for index in range(count)]
        for index, future in enumerate(futures):
            try:
                durations[index] = future.result(timeout=60)
            except (Exception, concurrent.futures.TimeoutError) as error:
                failures.append({"class": kind, "sample": index + 1,
                                 "error_type": type(error).__name__, "error": str(error)})
    if failures:
        raise InvalidRun(failures)
    return durations


class InvalidRun(RuntimeError):
    def __init__(self, failures):
        super().__init__(f"{len(failures)} rejected response(s) or timeout(s)")
        self.failures = failures


class NumericStateUnavailable(RuntimeError):
    pass


def run_one(number, manifest, output_dir):
    database = RUN_DATABASES[number - 1]
    create_database(database, SEED_DB)
    before = fixture_counts(database)
    process, log, startup = start_server(database, output_dir / f"run{number}.log")
    try:
        workloads = manifest["workloads"]
        clients = [BrowserClient(
            user["email"], next(workload for workload in workloads
                                if workload["business"] == user["business"]),
        ) for user in manifest["users"]]
        for client in clients:
            client.login()
        _, status, forecast_body = clients[0].request(
            f"/inventories/{workloads[0]['inventory_id']}/products/{workloads[0]['product_id']}/forecast/")
        if (status != 200 or b"Average daily demand:" not in forecast_body
                or b"Reorder point:" not in forecast_body):
            raise NumericStateUnavailable("Numeric forecast/reorder preflight is unavailable; no measured run started")
        warmups = {kind: sample_class(kind, clients, 20) for kind in CLASSES}
        measurements = {kind: sample_class(kind, clients, 500 if kind == "forecast_reorder" else 100)
                        for kind in CLASSES}
        forecast_duration, status, forecast_body = clients[0].request(
            f"/inventories/{workloads[0]['inventory_id']}/products/{workloads[0]['product_id']}/forecast/")
        if status != 200:
            raise RuntimeError("Forecast state check failed")
        forecast_state = ("available" if b"Average daily demand:" in forecast_body
                          else "unavailable")
    finally:
        stop_server(process, log)
    after = fixture_counts(database)
    if after["receipts"] - before["receipts"] != 120 or after["issues"] - before["issues"] != 120:
        raise RuntimeError(f"Stock movement counts did not reconcile: {before} -> {after}")
    return {"database": database, "startup_seconds_context": startup,
            "forecast_state": forecast_state, "state_probe_seconds_context": forecast_duration,
            "before": before, "after": after,
            "warmups": warmups, "measurements": measurements}


def run_csv(manifest, output_dir):
    create_database(CSV_DATABASE, SEED_DB)
    before = fixture_counts(CSV_DATABASE)
    process, log, startup = start_server(CSV_DATABASE, output_dir / "csv.log")
    try:
        user = manifest["users"][0]
        workload = manifest["workloads"][0]
        client = BrowserClient(user["email"], workload)
        client.login()
        boundary = secrets.token_hex(16)
        sku = "T26-1-1-000"
        csv = ("sku,change\n" + f"{sku},+1\n" * 1000).encode("utf-8")
        raw = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"tory26.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() + csv + (
                   f"\r\n--{boundary}--\r\n").encode()
        duration, status, body = client.request(
            f"/inventories/{workload['inventory_id']}/import/", raw=raw,
            content_type=f"multipart/form-data; boundary={boundary}")
        if status != 200 or b"Import recorded:" not in body:
            raise RuntimeError(f"Valid CSV import failed with HTTP {status}: {body[:120]!r}")
    finally:
        stop_server(process, log)
    after = fixture_counts(CSV_DATABASE)
    if after["receipts"] - before["receipts"] != 1000 or after["imports"] - before["imports"] != 1:
        raise RuntimeError(f"CSV stock and marker did not reconcile: {before} -> {after}")
    return {"valid_rows": 1000, "raw_bytes": len(csv), "seconds": duration,
            "startup_seconds_context": startup, "before": before, "after": after}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--manifest", type=Path, help="Existing seed manifest when reusing a seed with a new output path")
    parser.add_argument("--reset", action="store_true", help="Drop only the known tory26_benchmark_* databases before rebuilding")
    parser.add_argument("--reuse-seed", action="store_true", help="Reuse the existing isolated seed and manifest after a failed HTTP run")
    args = parser.parse_args()
    if args.reset and args.reuse_seed:
        parser.error("Choose either --reset or --reuse-seed")
    if os.environ.get("POSTGRES_DB") in (None, ""):
        parser.error("Load the PostgreSQL environment first")
    if args.output.resolve().is_relative_to(ROOT / "scripts"):
        parser.error("Raw evidence must not overwrite source scripts")
    if args.output.exists():
        parser.error("Raw evidence path already exists; choose a fresh output filename")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.reset:
        for name in reversed(ALL_DATABASES):
            drop_database(name)
    manifest_path = args.manifest or args.output.with_suffix(".manifest.json")
    if args.reuse_seed:
        if not database_exists(SEED_DB) or not manifest_path.exists():
            parser.error("The isolated seed database and manifest must both exist")
        for name in RUN_DATABASES + (CSV_DATABASE,):
            drop_database(name)
    else:
        if args.manifest:
            parser.error("--manifest is for --reuse-seed only")
        migrate_seed(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with maintenance_connection() as connection:
        postgres = connection.execute(
            "SELECT current_setting('server_version'), current_setting('track_commit_timestamp'), "
            "current_setting('max_connections'), current_setting('shared_buffers'), "
            "current_setting('work_mem')"
        ).fetchone()
    evidence = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
                "fixture": manifest, "runs": [], "csv": None,
                "topology": "Python urllib client -> 127.0.0.1:8002 Django runserver -> local PostgreSQL",
                "machine": {"platform": platform.platform(), "logical_cpus": os.cpu_count()},
                "postgres": dict(zip(("version", "track_commit_timestamp", "max_connections",
                                      "shared_buffers", "work_mem"), postgres)),
                "method": "Five concurrent browser sessions; complete response body; redirects not followed"}
    for number in range(1, 4):
        print(f"Starting measured run {number}/3", flush=True)
        try:
            result = run_one(number, manifest, args.output.parent)
        except InvalidRun as error:
            evidence["invalid_run"] = {"run": number, "failures": error.failures}
            args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            raise
        except NumericStateUnavailable as error:
            evidence["blocked_run"] = {"run": number, "reason": str(error)}
            args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            raise
        except Exception as error:
            evidence["invalid_run"] = {"run": number, "phase": "setup_or_preflight",
                                       "failures": [{"error_type": type(error).__name__, "error": str(error)}]}
            args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            raise
        evidence["runs"].append(result)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        drop_database(RUN_DATABASES[number - 1])
    evidence["csv"] = run_csv(manifest, args.output.parent)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    drop_database(CSV_DATABASE)
    print(f"Raw evidence: {args.output}", flush=True)


if __name__ == "__main__":
    main()
