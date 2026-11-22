"""Validate and summarize raw TORY-26 Envelope B timing evidence.

This is an analyzer, not an HTTP load generator or a benchmark claim. Input is
JSON with three runs; each run has ``warmups`` and ``measurements`` mappings of
class name to duration-in-seconds arrays. The separate ``csv`` object contains
``valid_rows`` and ``seconds``. Keep the raw JSON as reviewable evidence.
"""

import argparse
import json
import math
from pathlib import Path


ORDINARY = ("inventory_view", "inventory_products", "stock_in", "stock_out", "login")
DEPENDENT = ("forecast_reorder",)
CLASSES = ORDINARY + DEPENDENT


def nearest_rank_p95(samples):
    if not samples or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError("Durations must be finite, nonnegative numbers")
    return sorted(samples)[math.ceil(0.95 * len(samples)) - 1]


def analyze(evidence):
    if isinstance(evidence, dict) and evidence.get("invalid_run") is not None:
        raise ValueError("A rejected response or timeout invalidated a complete run")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("runs"), list) or len(evidence["runs"]) != 3:
        raise ValueError("Exactly three independent runs are required")
    results = []
    for index, run in enumerate(evidence["runs"], start=1):
        for group, expected in (("warmups", {name: 20 for name in CLASSES}),
                                ("measurements", {**{name: 100 for name in ORDINARY},
                                                  **{name: 500 for name in DEPENDENT}})):
            rows = run.get(group)
            if not isinstance(rows, dict) or set(rows) != set(expected):
                raise ValueError(f"Run {index}: {group} must contain exactly the six approved route classes")
            for name, count in expected.items():
                if not isinstance(rows[name], list) or len(rows[name]) != count:
                    raise ValueError(f"Run {index}: {group}.{name} must contain {count} durations")
                nearest_rank_p95(rows[name])
        ordinary = [value for name in ORDINARY for value in run["measurements"][name]]
        dependent = [value for name in DEPENDENT for value in run["measurements"][name]]
        ordinary_p95 = nearest_rank_p95(ordinary)
        dependent_p95 = nearest_rank_p95(dependent)
        results.append({"run": index, "ordinary_p95_seconds": ordinary_p95,
                        "ordinary_pass": ordinary_p95 <= 2,
                        "forecast_reorder_p95_seconds": dependent_p95,
                        "forecast_reorder_pass": dependent_p95 <= 3})
    csv = evidence.get("csv")
    if not isinstance(csv, dict) or csv.get("valid_rows") != 1000:
        raise ValueError("A separately validated 1,000-row CSV result is required")
    csv_seconds = csv.get("seconds")
    nearest_rank_p95([csv_seconds])
    return {"runs": results, "csv_seconds": csv_seconds, "csv_pass": csv_seconds <= 30,
            "timing_thresholds_met": all(
                row["ordinary_pass"] and row["forecast_reorder_pass"] for row in results
            ) and csv_seconds <= 30}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="Raw JSON timing evidence")
    args = parser.parse_args()
    try:
        result = analyze(json.loads(args.evidence.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
