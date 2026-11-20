import os
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import DemandAuditEvent, DemandCoverageEvent, ObservationActivation, ReceiptAuditEvent, ReceivingBatch


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
        self.assertEqual(Product.objects.filter(business=business).count(), 15)
        self.assertEqual(InventoryAssignment.objects.filter(inventory__business=business).count(), 4)
        today = timezone.localdate()
        self.assertEqual(ReceivingBatch.objects.filter(expiry_date__lt=today).count(), 1)
        self.assertGreaterEqual(
            ReceivingBatch.objects.filter(expiry_date__gt=today, expiry_date__lte=today + timedelta(days=7)).count(), 2,
        )
        self.assertEqual(ReceiptAuditEvent.objects.count(), ReceivingBatch.objects.count())
        self.assertEqual(DemandAuditEvent.objects.filter(actor=staff).count(), 28)
        self.assertEqual(DemandCoverageEvent.objects.filter(actor=manager, action="verified").count(), 28)

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
