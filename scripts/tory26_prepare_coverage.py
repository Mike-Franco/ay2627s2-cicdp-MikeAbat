"""Verify the TORY-26 seed's first seven complete observed Singapore dates.

Use only after the dates actually complete. Calls the normal Manager service;
never inserts or changes coverage rows directly. Reruns skip verified days.
"""

import json
import os
from datetime import timedelta
from pathlib import Path

if os.environ.get("POSTGRES_DB") != "tory26_benchmark_seed":
    raise RuntimeError("Coverage preparation requires the isolated benchmark seed")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402

from accounts.models import User  # noqa: E402
from catalogue.models import InventoryProduct  # noqa: E402
from receiving.demand import seven_day_forecast, verify_demand_day  # noqa: E402
from receiving.models import DemandCoverageDay, ObservationActivation  # noqa: E402


def main():
    if connection.settings_dict["NAME"] != "tory26_benchmark_seed":
        raise RuntimeError("Wrong database")
    manifest = json.loads((Path(__file__).resolve().parent.parent /
                           "benchmark-results/tory26-local.manifest.json").read_text(encoding="utf-8"))
    activation = ObservationActivation.objects.get(environment="development", state="active")
    first = timezone.localdate() - timedelta(days=7)
    if first < activation.first_observed_date:
        raise RuntimeError(f"Seven complete dates are not available until "
                           f"{activation.first_observed_date + timedelta(days=7)}")
    for workload in manifest["workloads"]:
        email = f"tory26-b{workload['business']}-u1@example.test"
        manager = User.objects.get(email=email)
        link = InventoryProduct.objects.get(inventory_id=workload["inventory_id"],
                                            product_id=workload["product_id"])
        for offset in range(7):
            day = first + timedelta(days=offset)
            coverage = DemandCoverageDay.objects.filter(inventory_product=link, day=day).first()
            if coverage is not None:
                latest = coverage.events.order_by("-pk").first()
                if latest is not None and latest.action == "verified":
                    continue
                raise RuntimeError(f"Day {day} has non-verified evidence; no correction path is approved")
            verify_demand_day(user_id=manager.pk, inventory_id=link.inventory_id,
                              product_id=link.product_id, day=day)
        result = seven_day_forecast(user_id=manager.pk, inventory_id=link.inventory_id,
                                    product_id=link.product_id)
        if not result.available:
            raise RuntimeError(f"Numeric forecast unavailable for product {link.product_id}: {result.reason}")
        print(f"Verified numeric forecast for inventory {link.inventory_id}, product {link.product_id}")


if __name__ == "__main__":
    main()
