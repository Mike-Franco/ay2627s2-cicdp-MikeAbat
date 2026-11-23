import os
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.metrics import accuracy_points, forecast_accuracy
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import (DemandAuditEvent, DemandCoverageEvent, ObservationActivation, ReceiptAuditEvent,
                              ReceivingBatch, StockOut)
from receiving.services import ReceiptRejected, issue_stock, receive_manual


class SeedDemoTests(TestCase):
    def test_seed_creates_audited_data_and_numeric_forecast_without_duplicates(self):
        env = {
            "DEMO_MANAGER_EMAIL": "seed-manager@example.test",
            "DEMO_STAFF_EMAIL": "seed-staff@example.test",
            "DEMO_MANAGER_PASSWORD": "seed-env-password-1!",
            "DEMO_STAFF_PASSWORD": "",
        }
        output = StringIO()
        with patch.dict(os.environ, env), patch(
            "receiving.management.commands.seed_demo.token_urlsafe", return_value="seed-generated-password-2!",
        ):
            call_command("seed_demo", stdout=output)

        business = Business.objects.get(name="Tory Demo")
        manager = get_user_model().objects.get(email=env["DEMO_MANAGER_EMAIL"])
        staff = get_user_model().objects.get(email=env["DEMO_STAFF_EMAIL"])
        self.assertTrue(manager.check_password(env["DEMO_MANAGER_PASSWORD"]))
        self.assertTrue(staff.check_password("seed-generated-password-2!"))
        self.assertNotIn(env["DEMO_MANAGER_PASSWORD"], output.getvalue())
        self.assertIn("seed-generated-password-2!", output.getvalue())
        self.assertSetEqual(set(business.inventories.values_list("name", flat=True)), {"Pharmacy", "Grocery"})
        products = Product.objects.filter(business=business)
        self.assertEqual(products.count(), 15)
        for product in products:
            self.assertGreater(product.lead_time_days, 0)
            self.assertGreater(product.safety_stock_units, 0)
            self.assertTrue(product.supplier_name)
        self.assertEqual(InventoryAssignment.objects.filter(inventory__business=business).count(), 4)
        today = timezone.localdate()
        self.assertEqual(ReceivingBatch.objects.filter(expiry_date__lt=today).count(), 1)
        self.assertGreaterEqual(
            ReceivingBatch.objects.filter(expiry_date__gt=today, expiry_date__lte=today + timedelta(days=7)).count(), 2,
        )
        self.assertEqual(ReceiptAuditEvent.objects.count(), ReceivingBatch.objects.count())
        self.assertEqual(DemandAuditEvent.objects.filter(actor=staff).count(), 56)
        self.assertEqual(DemandCoverageEvent.objects.filter(actor=manager, action="verified").count(), 15 * 14 - 2)

        for inventory in business.inventories.all():
            links = InventoryProduct.objects.filter(inventory=inventory).select_related("product")
            accuracy = forecast_accuracy(accuracy_points(links, at=timezone.now()))
            self.assertEqual(accuracy["value"], 0)

        self.client.force_login(manager)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        for sku in ("PH-01", "GR-01"):
            link = InventoryProduct.objects.get(product__sku=sku)
            response = self.client.get(reverse("demand-forecast", args=(link.inventory_id, link.product_id)))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["forecast"].displayed_average, "2.00")
            self.assertTrue(response.context["reorder"].alert)
            self.assertGreater(response.context["reorder"].suggested_units, 0)
            overview = self.client.get(reverse("product-stock", args=(link.inventory_id, link.product_id)))
            self.assertContains(overview, "Next 7 days")
            self.assertContains(overview, "stock arrives")

        dashboard = self.client.get(reverse("home"))
        self.assertContains(dashboard, 'aria-label="Do this first"')
        task, = dashboard.context["demand_tasks"]
        self.assertEqual(task["inventory"].name, "Grocery")
        self.assertEqual(task["days"], [today - timedelta(days=2), today - timedelta(days=1)])

        models = (Business, get_user_model(), BusinessMembership, Inventory, InventoryAssignment, Product,
                  InventoryProduct, ReceivingBatch, ReceiptAuditEvent, DemandAuditEvent, DemandCoverageEvent,
                  ObservationActivation)
        counts = [model.objects.count() for model in models]
        with patch.dict(os.environ, env):
            repeated = StringIO()
            call_command("seed_demo", stdout=repeated)
        self.assertIn("already seeded", repeated.getvalue())
        self.assertNotIn("password", repeated.getvalue())
        self.assertEqual([model.objects.count() for model in models], counts)

    def test_seed_refuses_production_before_writing(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "production"}), self.assertRaisesMessage(
            CommandError, "disabled in production",
        ):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(Business.objects.exists())
        self.assertFalse(ObservationActivation.objects.exists())


class DemoBackdatingProductionGuardTests(TestCase):
    """demo_received_at / demo_issued_at must never work in production (ADR-004)."""

    @classmethod
    def setUpTestData(cls):
        business = Business.objects.create(name="Tory Demo")
        cls.inventory = Inventory.objects.create(business=business, name="Demo pharmacy")
        cls.manager = get_user_model().objects.create_user(email="demo-manager@example.test",
                                                           password="demo-guard-test-passphrase")
        membership = BusinessMembership.objects.create(user=cls.manager, business=business,
                                                       role=BusinessMembership.Role.MANAGER)
        InventoryAssignment.objects.create(membership=membership, inventory=cls.inventory)
        cls.product = Product.objects.create(business=business, sku="DEMO-GUARD", name="Guard item",
                                             base_unit_label="each", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)

    def movement(self, **kwargs):
        return {"user_id": self.manager.pk, "inventory_id": self.inventory.pk, "product_id": self.product.pk,
                "request_token": uuid4(), **kwargs}

    def test_backdated_receipt_and_issue_are_rejected_in_production(self):
        past = timezone.now() - timedelta(days=2)
        receive_manual(**self.movement(quantity_units=10, expiry_date=None))
        batches, issues = ReceivingBatch.objects.count(), StockOut.objects.count()

        with override_settings(DJANGO_ENV="production"):
            with self.assertRaisesMessage(ReceiptRejected, "limited to the demo business"):
                receive_manual(**self.movement(quantity_units=5, expiry_date=None, demo_received_at=past))
            with self.assertRaisesMessage(ReceiptRejected, "limited to the demo business"):
                issue_stock(**self.movement(quantity_units=1, demo_issued_at=past))
        self.assertEqual(ReceivingBatch.objects.count(), batches)
        self.assertEqual(StockOut.objects.count(), issues)

        # Control: the same calls succeed outside production, so the
        # environment check is what rejected them above.
        with override_settings(DJANGO_ENV="development"):
            batch, _ = receive_manual(**self.movement(quantity_units=5, expiry_date=None, demo_received_at=past))
            issue_stock(**self.movement(quantity_units=1, demo_issued_at=past))
        self.assertEqual(batch.received_at, past)
        self.assertEqual(StockOut.objects.count(), issues + 1)
