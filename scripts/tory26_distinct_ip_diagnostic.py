"""Diagnostic-only HTTP logins from five distinct Windows loopback IPs.

This is 20 login samples, not the approved TORY-26 benchmark workload or a
performance-pass claim. It uses an isolated seed clone and normal Tory code.
"""

import concurrent.futures
import http.client
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import HTTPCookieProcessor, HTTPHandler, ProxyHandler, build_opener

if os.environ.get("POSTGRES_DB") != "tory26_benchmark_run1":
    raise RuntimeError("Distinct-IP diagnostic requires isolated tory26_benchmark_run1")

from scripts.tory26_http_benchmark import (  # noqa: E402
    BrowserClient, NoRedirect, PASSWORD, fixture_counts, start_server, stop_server,
)


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "benchmark-results/tory26-distinct-ip-diagnostic.json"
LOG = ROOT / "benchmark-results/tory26-distinct-ip-server.log"
IPS = tuple(f"127.0.0.{index}" for index in range(2, 7))


class BoundHTTPHandler(HTTPHandler):
    def __init__(self, source_ip):
        super().__init__()
        self.source_ip = source_ip

    def http_open(self, request):
        source_ip = self.source_ip

        class BoundConnection(http.client.HTTPConnection):
            def __init__(self, host, **kwargs):
                super().__init__(host, source_address=(source_ip, 0), **kwargs)

            def connect(self):
                super().connect()
                if self.sock.getsockname()[0] != source_ip:
                    raise RuntimeError("HTTP connection did not use its assigned source IP")

        return self.do_open(BoundConnection, request)


def login_sample(client):
    with client.lock:
        elapsed, status, _ = client.request(
            "/login/", {"email": client.email, "password": PASSWORD}
        )
    if status != 302:
        raise RuntimeError(f"Unexpected login HTTP {status}")
    return {"seconds": elapsed, "status": status}


def main():
    if OUTPUT.exists() or LOG.exists():
        raise RuntimeError("Refusing to overwrite distinct-IP evidence or server log")
    manifest = json.loads((ROOT / "benchmark-results/tory26-local.manifest.json").read_text(encoding="utf-8"))
    before = fixture_counts("tory26_benchmark_run1")
    process, log, startup = start_server("tory26_benchmark_run1", LOG)
    try:
        clients = []
        for user, source_ip in zip(manifest["users"], IPS):
            workload = next(row for row in manifest["workloads"]
                            if row["business"] == user["business"])
            client = BrowserClient(user["email"], workload)
            client.opener = build_opener(
                ProxyHandler({}), HTTPCookieProcessor(client.jar), NoRedirect(),
                BoundHTTPHandler(source_ip),
            )
            client.login()
            clients.append(client)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(login_sample, clients[index % 5]) for index in range(20)]
            samples = [future.result(timeout=60) for future in futures]
    finally:
        stop_server(process, log)
    after = fixture_counts("tory26_benchmark_run1")
    if after != before:
        raise RuntimeError(f"Login diagnostic changed stock evidence: {before} -> {after}")
    durations = [sample["seconds"] for sample in samples]
    evidence = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "tory26_benchmark_run1",
        "method": "Five bound loopback source IPs, real HTTP POST /login/, normal Django runserver, isolated clone; diagnostic only",
        "source_ips": IPS,
        "startup_seconds_context": startup,
        "samples": [{"client": index % 5 + 1, "source_ip": IPS[index % 5], **sample}
                    for index, sample in enumerate(samples)],
        "stock_counts_before": before,
        "stock_counts_after": after,
        "summary": {"count": len(samples), "median_seconds": statistics.median(durations),
                    "max_seconds": max(durations),
                    "nearest_rank_p95_seconds": sorted(durations)[18]},
    }
    with OUTPUT.open("x", encoding="utf-8") as output:
        json.dump(evidence, output, indent=2)
        output.write("\n")
    print(json.dumps({"raw_evidence": str(OUTPUT), **evidence["summary"]}, indent=2))


if __name__ == "__main__":
    main()
