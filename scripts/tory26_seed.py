"""Build the isolated, deterministic TORY-26 Envelope B stock fixture.

Run only after migrating a database named tory26_benchmark_seed. This script
refuses every other database and never reads or writes an existing demo DB.
"""

import hashlib
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402

from catalogue.models import InventoryProduct, Product  # noqa: E402
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment  # noqa: E402
from receiving.models import DemandAuditEvent, ReceiptAuditEvent, ReceivingBatch  # noqa: E402
from receiving.services import issue_stock, receive_manual  # noqa: E402


DATABASE_NAME = "tory26_benchmark_seed"
PASSWORD = hashlib.sha256(b"tory26-isolated-local-fixture-v1").hexdigest()
PRODUCTS_PER_INVENTORY = 125
RECEIPTS_PER_PRODUCT = 4
ISSUES_PER_PRODUCT = 36


def seed(output_path):
    if connection.settings_dict["NAME"] != DATABASE_NAME:
        raise RuntimeError(f"Refusing to seed database {connection.settings_dict['NAME']!r}")
    if Business.objects.exists():
        raise RuntimeError("Seed database is not empty; create a fresh isolated database")
    manifest = {"database": DATABASE_NAME, "seed_version": 1, "users": [], "workloads": []}
    for business_number in range(2):
        business = Business.objects.create(name=f"TORY-26 synthetic business {business_number + 1}")
        users = []
        for user_number in range(4 if business_number == 0 else 1):
            email = f"tory26-b{business_number + 1}-u{user_number + 1}@example.test"
            user = get_user_model().objects.create_user(email=email, password=PASSWORD)
            role = (BusinessMembership.Role.MANAGER if user_number == 0
                    else BusinessMembership.Role.STAFF)
            membership = BusinessMembership.objects.create(
                business=business, user=user, role=role, is_active=True,
            )
            users.append((user, membership))
            manifest["users"].append({"email": email, "role": role,
                                      "business": business_number + 1})
        for inventory_number in range(2):
            inventory = Inventory.objects.create(
                business=business, name=f"Synthetic inventory {business_number + 1}-{inventory_number + 1}"
            )
            for _, membership in users:
                InventoryAssignment.objects.create(
                    membership=membership, inventory=inventory, is_active=True,
                )
            for product_number in range(PRODUCTS_PER_INVENTORY):
                product = Product.objects.create(
                    business=business,
                    sku=f"T26-{business_number + 1}-{inventory_number + 1}-{product_number:03d}",
                    name=f"Synthetic product {business_number + 1}-{inventory_number + 1}-{product_number:03d}",
                    base_unit_label="unit", expiry_tracking_required=False,
                    lead_time_days=7, safety_stock_units=10,
                )
                InventoryProduct.objects.create(inventory=inventory, product=product)
                actor = users[0][0]
                for receipt_number in range(RECEIPTS_PER_PRODUCT):
                    expiry = (timezone.localdate() + timedelta(days=30)
                              if receipt_number == 0 else None)
                    receive_manual(
                        user_id=actor.pk, inventory_id=inventory.pk,
                        product_id=product.pk, request_token=uuid.uuid4(),
                        quantity_units=100, expiry_date=expiry,
                    )
                for _ in range(ISSUES_PER_PRODUCT):
                    issue_stock(
                        user_id=actor.pk, inventory_id=inventory.pk,
                        product_id=product.pk, quantity_units=1,
                    )
                if product_number == 0 and business_number == 0 or (
                    business_number == 1 and inventory_number == 0 and product_number == 0
                ):
                    manifest["workloads"].append({
                        "inventory_id": inventory.pk, "product_id": product.pk,
                        "business": business_number + 1,
                    })
                if product_number % 25 == 24:
                    print(f"Seeded business {business_number + 1}, inventory {inventory_number + 1}, "
                          f"products {product_number + 1}/125", flush=True)
    counts = {
        "businesses": Business.objects.count(), "inventories": Inventory.objects.count(),
        "products": Product.objects.count(), "batches": ReceivingBatch.objects.count(),
        "receipt_history": ReceiptAuditEvent.objects.count(),
        "issue_history": DemandAuditEvent.objects.count(),
    }
    if counts != {"businesses": 2, "inventories": 4, "products": 500,
                  "batches": 2000, "receipt_history": 2000, "issue_history": 18000}:
        raise RuntimeError(f"Fixture counts differ from Envelope B: {counts}")
    manifest["counts"] = counts
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts), flush=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/tory26_seed.py MANIFEST_PATH")
    seed(Path(sys.argv[1]))
