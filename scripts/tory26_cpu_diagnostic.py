"""Record a longer read-only Windows idle CPU and process baseline.

No Tory server or benchmark requests run during this measurement. Get-Process
reports cumulative CPU seconds; deltas are normalized by elapsed time and
logical CPU count. System CPU uses GetSystemTimes at 0.5-second intervals.
"""

import argparse
import ctypes
import json
import os
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

if os.name != "nt":
    raise RuntimeError("Windows-only diagnostic")

RESULTS = Path(__file__).resolve().parent.parent / "benchmark-results"
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


class FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


def system_times():
    idle, kernel, user = FileTime(), FileTime(), FileTime()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        raise OSError("GetSystemTimes failed")
    return tuple((part.high << 32) + part.low for part in (idle, kernel, user))


def sample_system(stop, samples):
    previous = system_times()
    previous_at = time.perf_counter()
    while not stop.wait(0.5):
        current = system_times()
        now = time.perf_counter()
        idle = current[0] - previous[0]
        total = current[1] - previous[1] + current[2] - previous[2]
        if total > 0:
            samples.append({"at_seconds": now, "interval_seconds": now - previous_at,
                            "system_cpu_percent": 100 * (total - idle) / total})
        previous, previous_at = current, now


def process_snapshots(interval_seconds, count):
    script = (
        "$ErrorActionPreference='Stop'; $out=@(); "
        f"for($i=0;$i -lt {count};$i++){{ "
        "$procs=@(Get-Process | Where-Object {$null -ne $_.CPU} | "
        "ForEach-Object {[pscustomobject]@{id=$_.Id; name=$_.ProcessName; cpu_seconds=$_.CPU}}); "
        "$out+= [pscustomobject]@{at_utc=[DateTime]::UtcNow.ToString('o'); processes=$procs}; "
        f"if($i -lt {count - 1}){{Start-Sleep -Seconds {interval_seconds}}} "
        "}; ConvertTo-Json -InputObject $out -Depth 5 -Compress"
    )
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return json.loads(result.stdout)


def summarize_processes(snapshots):
    first, last = snapshots[0], snapshots[-1]
    elapsed = (datetime.fromisoformat(last["at_utc"]) -
               datetime.fromisoformat(first["at_utc"])).total_seconds()
    before = {row["id"]: row for row in first["processes"]}
    by_name = {}
    for row in last["processes"]:
        prior = before.get(row["id"])
        if prior is None or prior["name"] != row["name"]:
            continue
        delta = row["cpu_seconds"] - prior["cpu_seconds"]
        if delta > 0:
            by_name[row["name"]] = by_name.get(row["name"], 0.0) + delta
    logical = os.cpu_count() or 1
    ranked = sorted(by_name.items(), key=lambda pair: pair[1], reverse=True)
    return {"snapshot_elapsed_seconds": elapsed,
            "logical_cpus": logical,
            "top_processes": [{"name": name, "cpu_seconds": seconds,
                               "whole_machine_cpu_percent": 100 * seconds / (elapsed * logical)}
                              for name, seconds in ranked[:20]],
            "observed_process_cpu_seconds": sum(by_name.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="Only two process snapshots, 30 seconds apart")
    args = parser.parse_args()
    output_path = RESULTS / ("tory26-cpu-idle-quiet.json" if args.quiet
                             else "tory26-cpu-idle-diagnostic.json")
    if output_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing evidence: {output_path}")
    interval_seconds, count = (30, 2) if args.quiet else (5, 7)
    system_samples = []
    stop = threading.Event()
    sampler = threading.Thread(target=sample_system, args=(stop, system_samples))
    sampler.start()
    try:
        snapshots = process_snapshots(interval_seconds, count)
    finally:
        stop.set()
        sampler.join()
    values = [row["system_cpu_percent"] for row in system_samples]
    process_summary = summarize_processes(snapshots)
    summary = {"system_sample_count": len(values),
               "system_cpu_median_percent": statistics.median(values),
               "system_cpu_min_percent": min(values),
               "system_cpu_max_percent": max(values),
               **process_summary}
    evidence = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "method": f"Windows GetSystemTimes every 0.5 s; {count} Get-Process CPU snapshots {interval_seconds} s apart; no Tory requests",
                "system_samples": system_samples,
                "process_snapshots": snapshots,
                "summary": summary}
    with output_path.open("x", encoding="utf-8") as output:
        json.dump(evidence, output, indent=2)
        output.write("\n")
    print(json.dumps({"raw_evidence": str(output_path),
                      "system_cpu_median_percent": summary["system_cpu_median_percent"],
                      "top_processes": summary["top_processes"][:8]}, indent=2))


if __name__ == "__main__":
    main()
