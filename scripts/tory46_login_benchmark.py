"""TORY-46: time sign-in against the Docker/gunicorn stack, sequential vs concurrent.

Start the stack first, for example:

    WEB_CONCURRENCY=5 docker compose up --build --detach --wait

then run from the repository root:

    python scripts/tory46_login_benchmark.py --seed --label after --output benchmark-results/tory46-login-after.json

``--seed`` creates five benchmark-only users through ``docker compose exec``.
Every login is a fresh browser session: an untimed GET for the CSRF cookie,
then a timed POST. Successful sign-ins answer 302 and record no throttle
failures, so repeated rounds never trip the limit. All clients share one
source IP (the Docker gateway), which is the contended throttle key.
"""

import argparse
import concurrent.futures
import hashlib
import http.cookiejar
import json
import platform
import statistics
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

PASSWORD = hashlib.sha256(b"tory46-benchmark-only-fixture-v1").hexdigest()
EMAILS = [f"tory46-u{i}@example.test" for i in range(1, 6)]
SEED = f"""
from django.contrib.auth import get_user_model
User = get_user_model()
for email in {EMAILS!r}:
    user, _ = User.objects.get_or_create(email=email)
    user.set_password({PASSWORD!r})
    user.save()
from accounts.models import LoginFailure
LoginFailure.objects.all().delete()
print("seeded", len({EMAILS!r}), "users")
"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def login_once(base, email):
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar), NoRedirect())
    opener.open(base + "/login/", timeout=30).read()
    token = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
    request = Request(
        base + "/login/",
        data=urlencode({"email": email, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": token,
                 "Referer": base + "/login/"},
    )
    start = time.perf_counter()
    try:
        response = opener.open(request, timeout=60)
    except HTTPError as error:
        response = error
    response.read()
    elapsed = time.perf_counter() - start
    if response.code != 302:
        raise RuntimeError(f"{email}: expected 302 after sign-in, got {response.code}")
    return elapsed


def summary(samples):
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "median_s": round(statistics.median(ordered), 4),
        "p95_s": round(ordered[max(0, round(0.95 * len(ordered)) - 1)], 4),
        "max_s": round(ordered[-1], 4),
        "mean_s": round(statistics.fmean(ordered), 4),
    }


def run(base, rounds, clients):
    for email in EMAILS[:clients]:
        login_once(base, email)  # warm-up: worker imports, connections
    sequential = [login_once(base, EMAILS[i % clients]) for i in range(rounds)]
    parallel, walls = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=clients) as pool:
        for _ in range(rounds):
            barrier = threading.Barrier(clients)

            def attempt(email, barrier=barrier):
                barrier.wait(timeout=30)
                return login_once(base, email)

            start = time.perf_counter()
            parallel.extend(pool.map(attempt, EMAILS[:clients]))
            walls.append(time.perf_counter() - start)
    return sequential, parallel, walls


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--clients", type=int, default=5, choices=range(1, len(EMAILS) + 1))
    parser.add_argument("--label", required=True, help="for example before or after")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", action="store_true", help="create the benchmark users via docker compose exec")
    args = parser.parse_args()

    if args.seed:
        print(docker("compose", "exec", "-T", "web", "python", "manage.py", "shell", "-c", SEED))
    workers = docker("compose", "exec", "-T", "web", "sh", "-c", "echo $WEB_CONCURRENCY")
    sequential, parallel, walls = run(args.base_url.rstrip("/"), args.rounds, args.clients)
    result = {
        "ticket": "TORY-46",
        "label": args.label,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                     text=True).stdout.strip(),
        "environment": {
            "server": "gunicorn (sync workers) in the docker-compose web service",
            "web_concurrency": workers,
            "docker_cpus": docker("info", "--format", "{{.NCPU}}"),
            "docker_memory_bytes": docker("info", "--format", "{{.MemTotal}}"),
            "client_host": f"{platform.system()} {platform.release()}",
            "password_hasher": "Django default PBKDF2 (iterations unchanged)",
        },
        "method": (f"{args.rounds} sequential sign-ins, then {args.rounds} rounds of {args.clients} "
                   "simultaneous sign-ins from one source IP; each timed POST is a fresh session"),
        "sequential": summary(sequential),
        "concurrent_same_ip": summary(parallel),
        "concurrent_round_wall": summary(walls),
        "raw_seconds": {"sequential": [round(s, 4) for s in sequential],
                        "concurrent_same_ip": [round(s, 4) for s in parallel]},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("label", "sequential", "concurrent_same_ip",
                                                   "concurrent_round_wall")}, indent=2))


if __name__ == "__main__":
    main()
