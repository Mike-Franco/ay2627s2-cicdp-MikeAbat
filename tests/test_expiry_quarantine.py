from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import patch
from zoneinfo import ZoneInfo
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.models import (DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent,
                              ReceiptAuditEvent, ReceivingBatch, StockDisposal, StockOut)
from receiving.services import (ReceiptRejected, dispose_quarantined, expiry_boundary, issue_stock,
                                process_expiry_quarantine, quarantine_quantity, receive_manual)


SINGAPORE = ZoneInfo("Asia/Singapore")


class ExpiryQuarantineTests(TransactionTestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Expiry business")
        self.manager = get_user_model().objects.create_user(email="expiry-manager@example.test", password="test-password")
        membership = BusinessMembership.objects.create(business=self.business, user=self.manager, role="manager")
        self.inventory = Inventory.objects.create(business=self.business, name="Expiry shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.product = Product.objects.create(business=self.business, sku="EXP-1", name="Expiry product",
                                              base_unit_label="each", expiry_tracking_required=False)
        self.link = InventoryProduct.objects.create(inventory=self.inventory, product=self.product)

    def receive(self, quantity, expiry=None):
        return receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                              product_id=self.product.pk, request_token=uuid.uuid4(),
                              quantity_units=quantity, expiry_date=expiry)[0]

    def expired_batch(self, quantity=5, days_ago=0):
        batch = self.receive(quantity, timezone.localdate() + timedelta(days=1))
        # Receipts correctly reject past expiry. Rewrite this fixture with the
        # existing test-only technique to represent a batch received earlier.
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_immutable_guard")
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_batch_stock_out_guard")
            try:
                cursor.execute("UPDATE receiving_receivingbatch SET expiry_date=%s WHERE id=%s",
                               [timezone.localdate() - timedelta(days=days_ago), str(batch.pk)])
            finally:
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_stock_out_guard")
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_batch_immutable_guard")
        batch.refresh_from_db()
        return batch

    def test_midnight_boundary_is_immediate_before_evidence(self):
        batch = self.expired_batch()
        boundary = expiry_boundary(batch.expiry_date)
        self.assertEqual(boundary, datetime.combine(batch.expiry_date, datetime.min.time(), SINGAPORE))
        self.assertEqual(quarantine_quantity(batch, at=boundary - timedelta(seconds=1)), 0)
        self.assertEqual(quarantine_quantity(batch, at=boundary), 5)
        with self.assertRaises(ReceiptRejected):
            issue_stock(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                        product_id=self.product.pk, quantity_units=1)
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 0)
        self.assertEqual(DemandAuditEvent.objects.count(), 0)
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = timezone.now().timestamp()
        session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        page = self.client.get(reverse("inventory-products", args=[self.inventory.pk]))
        link = page.context["product_links"][0]
        self.assertEqual(
            (
                link.display_physical_units,
                link.display_quarantine_units,
                link.display_available_units,
            ),
            (5, 5, 0),
        )
        self.assertContains(
            page,
            '<td class="numeric available">0<span class="unit">each</span></td>',
            html=True,
        )
        self.assertContains(
            page,
            '<td class="numeric">5<span class="unit">each</span></td>',
            count=2,
            html=True,
        )
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 5)

    def test_delayed_recording_preserves_effective_and_actual_times(self):
        batch = self.expired_batch(days_ago=1)
        self.assertEqual(process_expiry_quarantine(), 1)
        batch.refresh_from_db()
        event = ExpiryQuarantineEvent.objects.get(batch=batch)
        self.assertEqual(event.effective_at, expiry_boundary(batch.expiry_date))
        self.assertGreater(event.recorded_at, event.effective_at)
        self.assertLess(abs((timezone.now() - event.recorded_at).total_seconds()), 10)
        self.assertEqual(event.actor_identity, "system:expiry_quarantine")
        self.assertEqual(event.classification, "non_demand")
        self.assertEqual((event.physical_quantity_units, event.available_before_units,
                          event.available_after_units, event.quarantine_before_units,
                          event.quarantine_after_units), (5, 5, 0, 0, 5))
        self.assertEqual(batch.quarantined_quantity_units, 5)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 5)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)
        self.assertEqual(DemandAuditEvent.objects.count(), 0)

    def test_repeated_command_and_unlinked_sql_cannot_duplicate_or_rewrite_history(self):
        batch = self.expired_batch()
        output = StringIO()
        call_command("process_expiry_quarantine", stdout=output)
        self.assertIn("Recorded 1", output.getvalue())
        self.assertEqual(process_expiry_quarantine(), 0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExpiryQuarantineEvent.objects.filter(batch=batch).update(quarantine_after_units=0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReceivingBatch.objects.filter(pk=batch.pk).update(quarantined_quantity_units=0)
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 1)

    def test_failed_event_write_rolls_back_quarantine(self):
        batch = self.expired_batch()
        with patch("receiving.services.ExpiryQuarantineEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                process_expiry_quarantine()
        batch.refresh_from_db()
        self.assertEqual(batch.quarantined_quantity_units, 0)
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 0)

    def test_issue_is_rechecked_at_commit_when_eligibility_was_stale(self):
        batch = self.expired_batch(quantity=2)
        # Simulate an application clock still reading the previous Singapore
        # day. The normal batch guard is disabled only to reach commit and
        # exercise the independent deferred PostgreSQL boundary check.
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE receiving_receivingbatch DISABLE TRIGGER receiving_expiry_batch_update_guard")
        try:
            with patch("receiving.services.timezone.localdate", return_value=batch.expiry_date - timedelta(days=1)):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        issue_stock(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                    product_id=self.product.pk, quantity_units=1)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE receiving_receivingbatch ENABLE TRIGGER receiving_expiry_batch_update_guard")
        batch.refresh_from_db()
        self.assertEqual(batch.remaining_quantity_units, 2)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 2)
        self.assertEqual(StockOut.objects.count(), 0)

    def test_two_runs_race_with_issue_and_receipt_without_lost_stock(self):
        expired = self.expired_batch()
        eligible = self.receive(2)
        barrier = Barrier(4)

        def worker(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if operation == "process":
                    return process_expiry_quarantine()
                if operation == "issue":
                    return issue_stock(user_id=self.manager.pk, inventory_id=self.inventory.pk,
                                       product_id=self.product.pk, quantity_units=1)
                return self.receive(1)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(worker, action) for action in ("process", "process", "issue", "receive")]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results[0] + results[1], 1)
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 1)
        self.assertEqual(DemandAuditEvent.objects.count(), 1)
        expired.refresh_from_db()
        eligible.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual(expired.quarantined_quantity_units, 5)
        self.assertEqual(eligible.remaining_quantity_units, 1)
        self.assertEqual(self.link.physical_quantity_units, 7)
        self.assertEqual(self.link.physical_quantity_units,
                         sum(ReceivingBatch.objects.filter(inventory_product=self.link)
                             .values_list("remaining_quantity_units", flat=True)))

    def dispose(self, batch, quantity=2, code="Expired", note="", user=None, inventory=None):
        return dispose_quarantined(
            user_id=(user or self.manager).pk,
            inventory_id=(inventory or self.inventory).pk,
            product_id=self.product.pk, batch_id=batch.pk,
            quantity_units=quantity, reason_code=code, reason_note=note,
        )

    def test_disposal_before_quarantine_recording_reconciles_boundary_and_residual(self):
        batch = self.expired_batch()
        disposal = self.dispose(batch, code="Other", note="  damaged packaging  ")
        batch.refresh_from_db()
        self.assertEqual((batch.remaining_quantity_units, batch.quarantined_quantity_units), (3, 0))
        self.assertEqual(quarantine_quantity(batch), 3)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 3)
        audit = DisposalAuditEvent.objects.get(disposal=disposal)
        self.assertEqual((audit.reason_code, audit.reason_note, audit.classification),
                         ("Other", "damaged packaging", "non_demand"))
        self.assertEqual(DemandAuditEvent.objects.count(), 0)
        self.assertEqual(process_expiry_quarantine(), 1)
        batch.refresh_from_db()
        event = batch.expiry_event
        self.assertEqual((event.physical_quantity_units, event.disposed_before_recording_units,
                          event.available_before_units, event.quarantine_after_units), (3, 2, 5, 3))
        self.assertEqual((batch.remaining_quantity_units, batch.quarantined_quantity_units), (3, 3))
        self.assertEqual(process_expiry_quarantine(), 0)

    def test_disposal_after_quarantine_recording_decrements_stored_quarantine(self):
        batch = self.expired_batch()
        process_expiry_quarantine()
        disposal = self.dispose(batch, code="Damaged")
        batch.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual((batch.remaining_quantity_units, batch.quarantined_quantity_units,
                          self.link.physical_quantity_units), (3, 3, 3))
        self.assertEqual((disposal.audit_event.reason_code, disposal.audit_event.reason_note),
                         ("Damaged", ""))
        self.assertEqual(batch.expiry_event.physical_quantity_units, 5)

    def test_reason_quantity_and_batch_validation_leave_no_mutation(self):
        batch = self.expired_batch()
        future = self.receive(2, timezone.localdate() + timedelta(days=1))
        invalid = [(batch, 1, "Other", "  "), (batch, 1, "Unknown", "note"),
                   (batch, 6, "Expired", ""), (batch, 0, "Expired", ""),
                   (future, 1, "Expired", "")]
        for target, quantity, code, note in invalid:
            with self.subTest(quantity=quantity, code=code, target=target.pk):
                with self.assertRaises(ReceiptRejected):
                    self.dispose(target, quantity=quantity, code=code, note=note)
        self.assertEqual(StockDisposal.objects.count(), 0)
        self.assertEqual(DisposalAuditEvent.objects.count(), 0)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 7)

    def test_staff_and_unassigned_manager_cannot_dispose(self):
        batch = self.expired_batch()
        staff = get_user_model().objects.create_user(email="expiry-staff@example.test", password="test-password")
        staff_member = BusinessMembership.objects.create(business=self.business, user=staff, role="staff")
        InventoryAssignment.objects.create(membership=staff_member, inventory=self.inventory)
        other_manager = get_user_model().objects.create_user(email="expiry-other@example.test", password="test-password")
        BusinessMembership.objects.create(business=self.business, user=other_manager, role="manager")
        for user in (staff, other_manager):
            with self.assertRaises(ReceiptRejected):
                self.dispose(batch, user=user)
        self.assertEqual(StockDisposal.objects.count(), 0)
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 5)

    def test_audit_failure_rolls_back_batch_and_balance(self):
        batch = self.expired_batch()
        with patch("receiving.services.DisposalAuditEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.dispose(batch)
        batch.refresh_from_db()
        self.assertEqual((batch.remaining_quantity_units, batch.quarantined_quantity_units), (5, 0))
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 5)
        self.assertEqual(StockDisposal.objects.count(), 0)

    def test_disposal_and_quarantine_processing_serialize(self):
        batch = self.expired_batch()
        barrier = Barrier(2)

        def worker(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if operation == "dispose":
                    return self.dispose(batch)
                return process_expiry_quarantine()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, operation) for operation in ("dispose", "process")]
            [future.result(timeout=20) for future in futures]
        batch.refresh_from_db()
        event = batch.expiry_event
        self.assertEqual((batch.remaining_quantity_units, batch.quarantined_quantity_units), (3, 3))
        self.assertEqual(InventoryProduct.objects.get(pk=self.link.pk).physical_quantity_units, 3)
        self.assertEqual(DisposalAuditEvent.objects.count(), 1)
        self.assertEqual(ExpiryQuarantineEvent.objects.count(), 1)
        self.assertEqual(event.physical_quantity_units + event.disposed_before_recording_units, 5)

    def test_manager_disposal_form_and_staff_denial(self):
        batch = self.expired_batch()
        url = reverse("dispose-stock", args=[self.inventory.pk, self.product.pk])
        self.client.force_login(self.manager)
        session = self.client.session
        session[CREATED_KEY] = timezone.now().timestamp()
        session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.assertContains(self.client.get(url), "Batch 1")
        rejected = self.client.post(url, {
            "batch_id": str(batch.pk), "quantity_units": "2",
            "reason_code": "Other", "reason_note": "   ",
        })
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(StockDisposal.objects.count(), 0)
        accepted = self.client.post(url, {
            "batch_id": str(batch.pk), "quantity_units": "2",
            "reason_code": "Expired", "reason_note": "",
        })
        self.assertEqual(accepted.status_code, 302)
        self.assertContains(self.client.get(accepted["Location"]), "Classification: non_demand")
        staff = get_user_model().objects.create_user(email="form-staff@example.test", password="test-password")
        membership = BusinessMembership.objects.create(business=self.business, user=staff, role="staff")
        InventoryAssignment.objects.create(membership=membership, inventory=self.inventory)
        self.client.force_login(staff)
        session = self.client.session
        session[CREATED_KEY] = timezone.now().timestamp()
        session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.assertEqual(self.client.get(url).status_code, 404)
