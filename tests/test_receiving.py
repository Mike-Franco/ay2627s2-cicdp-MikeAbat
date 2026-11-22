from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from threading import Barrier, Event
from unittest.mock import patch
import uuid
import hashlib

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.forms import ManualReceiptForm
from receiving.models import MAX_RECEIPT_UNITS, ReceiptAuditEvent, ReceivingBatch
from receiving.services import ReceiptRejected, receive_manual


class ReceivingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = Business.objects.create(name="Receiving business")
        cls.other_business = Business.objects.create(name="Other receiving business")
        cls.manager = get_user_model().objects.create_user(
            email="receive-manager@example.test", password="test-only-password"
        )
        cls.staff = get_user_model().objects.create_user(
            email="receive-staff@example.test", password="test-only-password"
        )
        cls.unassigned = get_user_model().objects.create_user(
            email="receive-unassigned@example.test", password="test-only-password"
        )
        cls.manager_membership = BusinessMembership.objects.create(
            business=cls.business, user=cls.manager, role=BusinessMembership.Role.MANAGER
        )
        cls.staff_membership = BusinessMembership.objects.create(
            business=cls.business, user=cls.staff, role=BusinessMembership.Role.STAFF
        )
        cls.inventory = Inventory.objects.create(business=cls.business, name="Receiving shelf")
        cls.other_inventory = Inventory.objects.create(
            business=cls.other_business, name="Other shelf"
        )
        InventoryAssignment.objects.create(membership=cls.manager_membership, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=cls.staff_membership, inventory=cls.inventory)
        cls.product = Product.objects.create(
            business=cls.business,
            sku="RCV-01",
            name="Receiving product",
            base_unit_label="each",
            expiry_tracking_required=False,
        )
        cls.other_product = Product.objects.create(
            business=cls.other_business,
            sku="RCV-01",
            name="Foreign product",
            base_unit_label="each",
            expiry_tracking_required=False,
        )
        cls.link = InventoryProduct.objects.create(inventory=cls.inventory, product=cls.product)
        InventoryProduct.objects.create(inventory=cls.other_inventory, product=cls.other_product)

    def authenticate(self, user, client=None):
        client = client or self.client
        client.force_login(user)
        session = client.session
        now = timezone.now().timestamp()
        session[CREATED_KEY] = now
        session[ACTIVE_KEY] = now
        session.save()
        return client

    def receive(self, *, user=None, inventory=None, product=None, token=None, quantity=5, expiry=None):
        return receive_manual(
            user_id=(user or self.manager).pk,
            inventory_id=(inventory or self.inventory).pk,
            product_id=(product or self.product).pk,
            request_token=token or uuid.uuid4(),
            quantity_units=quantity,
            expiry_date=expiry,
        )

    def test_assigned_manager_and_staff_receive_and_audit_once(self):
        for user in (self.manager, self.staff):
            batch, replayed = self.receive(user=user, quantity=3)
            self.assertFalse(replayed)
            audit = ReceiptAuditEvent.objects.get(batch=batch)
            self.assertEqual(audit.actor_id, user.pk)
            self.assertEqual(audit.business_id, self.business.pk)
            self.assertEqual(audit.inventory_id, self.inventory.pk)
            self.assertEqual(audit.product_id, self.product.pk)
            self.assertEqual((audit.quantity_before_units, audit.quantity_change_units, audit.quantity_after_units), (0 if user == self.manager else 3, 3, 3 if user == self.manager else 6))
            self.assertEqual(audit.classification, "non_demand")
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 6)
        self.assertEqual([b.receipt_sequence for b in ReceivingBatch.objects.order_by("receipt_sequence")], [1, 2])

    def test_cross_business_unassigned_inactive_and_missing_link_denied(self):
        with self.assertRaises(ReceiptRejected):
            self.receive(inventory=self.other_inventory, product=self.other_product)
        with self.assertRaises(ReceiptRejected):
            self.receive(user=self.unassigned)
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])
        with self.assertRaises(ReceiptRejected):
            self.receive()
        self.manager.is_active = True
        self.manager.save(update_fields=["is_active"])
        self.manager_membership.is_active = False
        self.manager_membership.save(update_fields=["is_active"])
        with self.assertRaises(ReceiptRejected):
            self.receive()
        self.manager_membership.is_active = True
        self.manager_membership.save(update_fields=["is_active"])
        self.inventory.is_active = False
        self.inventory.save(update_fields=["is_active"])
        with self.assertRaises(ReceiptRejected):
            self.receive()
        self.inventory.is_active = True
        self.inventory.save(update_fields=["is_active"])
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        with self.assertRaises(ReceiptRejected):
            self.receive()
        self.product.is_active = True
        self.product.save(update_fields=["is_active"])
        link = InventoryProduct.objects.get(pk=self.link.pk)
        link.delete()
        with self.assertRaises(ReceiptRejected):
            self.receive()

    def test_unconfigured_product_requires_explicit_operator_setup(self):
        product = Product.objects.create(business=self.business, sku="RCV-02", name="Unset")
        self.assertTrue(product.is_active)
        self.assertIsNone(product.expiry_tracking_required)
        self.assertIsNone(product.base_unit_label)
        InventoryProduct.objects.create(inventory=self.inventory, product=product)
        with self.assertRaises(ReceiptRejected):
            self.receive(product=product)
        product.base_unit_label = "kg"
        product.expiry_tracking_required = True
        product.save(update_fields=["base_unit_label", "expiry_tracking_required"])
        with self.assertRaises(ReceiptRejected):
            self.receive(product=product)
        batch, _ = self.receive(product=product, expiry=timezone.localdate() + timedelta(days=1))
        self.assertEqual(batch.unit_label_snapshot, "kg")

    def test_operator_configuration_command_requires_explicit_valid_values(self):
        product = Product.objects.create(business=self.business, sku="RCV-03", name="Command setup")
        with self.assertRaises(CommandError):
            call_command(
                "configure_receiving", product.pk, base_unit_label="   ", expiry_tracking_required="false"
            )
        call_command(
            "configure_receiving", product.pk, base_unit_label=" box ", expiry_tracking_required="true"
        )
        product.refresh_from_db()
        self.assertEqual(product.base_unit_label, "box")
        self.assertTrue(product.expiry_tracking_required)

    def test_quantity_input_and_receipt_boundaries(self):
        for bad in ("0", "-1", "1.5", "2147483648", "abc"):
            form = ManualReceiptForm(
                {"request_token": str(uuid.uuid4()), "quantity_units": bad, "expiry_date": ""}
            )
            self.assertFalse(form.is_valid(), bad)
        batch, _ = self.receive(quantity=MAX_RECEIPT_UNITS)
        self.assertEqual(batch.quantity_units, MAX_RECEIPT_UNITS)
        with self.assertRaises(ReceiptRejected):
            self.receive(quantity=1)
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, MAX_RECEIPT_UNITS)
        self.assertEqual(ReceivingBatch.objects.count(), 1)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)

    def test_optional_and_mandatory_expiry_use_singapore_date(self):
        today = timezone.localdate()
        for supplied in (today, today - timedelta(days=1)):
            with self.assertRaises(ReceiptRejected):
                self.receive(expiry=supplied)
        undated, _ = self.receive()
        dated, _ = self.receive(expiry=today + timedelta(days=1))
        self.assertIsNone(undated.expiry_date)
        self.assertEqual(dated.expiry_date, today + timedelta(days=1))

    def test_singapore_midnight_changes_receipt_expiry_eligibility(self):
        day = timezone.localdate() + timedelta(days=10)
        expiry = day + timedelta(days=1)
        just_before_midnight_utc = datetime.combine(day, time(15, 59), tzinfo=datetime_timezone.utc)
        at_midnight_utc = datetime.combine(day, time(16, 0), tzinfo=datetime_timezone.utc)
        with patch("receiving.services.timezone.now", return_value=just_before_midnight_utc):
            batch, _ = self.receive(expiry=expiry)
        self.assertEqual(batch.expiry_date, expiry)
        with patch("receiving.services.timezone.now", return_value=at_midnight_utc):
            with self.assertRaises(ReceiptRejected):
                self.receive(expiry=expiry)

    def test_service_rejects_non_integer_python_values(self):
        with self.assertRaises(ReceiptRejected):
            self.receive(quantity=1.5)

    def test_token_replay_changed_input_and_fresh_form(self):
        token = uuid.uuid4()
        first, replayed = self.receive(token=token, quantity=4)
        again, replayed = self.receive(token=token, quantity=4)
        self.assertTrue(replayed)
        self.assertEqual(first.pk, again.pk)
        with self.assertRaises(ReceiptRejected):
            self.receive(token=token, quantity=5)
        another, replayed = self.receive(token=uuid.uuid4(), quantity=4)
        self.assertFalse(replayed)
        self.assertNotEqual(first.pk, another.pk)
        self.assertEqual(ReceivingBatch.objects.count(), 2)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 2)

    def test_replay_after_expiry_returns_original_without_revalidating_date(self):
        today = timezone.localdate()
        expiry = today + timedelta(days=1)
        token = uuid.uuid4()
        first, _ = self.receive(token=token, expiry=expiry)
        with patch("receiving.services.timezone.localdate", return_value=expiry + timedelta(days=1)):
            replay, was_replayed = self.receive(token=token, expiry=expiry)
        self.assertTrue(was_replayed)
        self.assertEqual(first.pk, replay.pk)

    def test_replay_after_assignment_revocation_is_denied(self):
        token = uuid.uuid4()
        self.receive(token=token)
        assignment = InventoryAssignment.objects.get(membership=self.manager_membership, inventory=self.inventory)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        with self.assertRaises(ReceiptRejected):
            self.receive(token=token)

    def test_audit_failure_rolls_back_batch_balance_and_token(self):
        token = uuid.uuid4()
        with patch("receiving.services._create_receipt_audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.receive(token=token, quantity=7)
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 0)
        self.assertEqual(self.link.last_receipt_sequence, 0)
        self.assertFalse(ReceivingBatch.objects.filter(request_token=token).exists())
        self.assertEqual(ReceiptAuditEvent.objects.count(), 0)

    def test_database_guards_reject_balance_bypass_and_audit_deletion(self):
        batch, _ = self.receive(quantity=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE catalogue_inventoryproduct SET physical_quantity_units = 0 WHERE id = %s",
                    [self.link.pk],
                )
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM receiving_receiptauditevent WHERE batch_id = %s", [str(batch.pk)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM receiving_receivingbatch WHERE id = %s", [str(batch.pk)])
        second_inventory = Inventory.objects.create(business=self.business, name="Identity guard shelf")
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE catalogue_inventoryproduct SET inventory_id = %s WHERE id = %s",
                    [second_inventory.pk, self.link.pk],
                )

    def test_new_inventory_product_links_require_zero_initial_stock_and_sequence(self):
        orm_inventory = Inventory.objects.create(business=self.business, name="ORM bypass shelf")
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryProduct.objects.create(
                inventory=orm_inventory,
                product=self.product,
                physical_quantity_units=1,
                last_receipt_sequence=0,
            )

        bulk_inventory = Inventory.objects.create(business=self.business, name="Bulk bypass shelf")
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryProduct.objects.bulk_create(
                [InventoryProduct(
                    inventory=bulk_inventory,
                    product=self.product,
                    physical_quantity_units=0,
                    last_receipt_sequence=1,
                )]
            )

        sql_inventory = Inventory.objects.create(business=self.business, name="SQL bypass shelf")
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO catalogue_inventoryproduct "
                    "(inventory_id, product_id, selling_price, physical_quantity_units, last_receipt_sequence) "
                    "VALUES (%s, %s, NULL, 1, 1)",
                    [sql_inventory.pk, self.product.pk],
                )

        valid_inventory = Inventory.objects.create(business=self.business, name="Zero initial shelf")
        InventoryAssignment.objects.create(membership=self.manager_membership, inventory=valid_inventory)
        valid_link = InventoryProduct.objects.create(inventory=valid_inventory, product=self.product)
        self.assertEqual((valid_link.physical_quantity_units, valid_link.last_receipt_sequence), (0, 0))
        batch, replayed = self.receive(inventory=valid_inventory, quantity=3)
        self.assertFalse(replayed)
        valid_link.refresh_from_db()
        self.assertEqual((valid_link.physical_quantity_units, valid_link.last_receipt_sequence), (3, 1))
        self.assertEqual(ReceiptAuditEvent.objects.get(batch=batch).quantity_after_units, 3)

    def test_database_rejects_cross_business_batch_even_with_raw_sql(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO receiving_receivingbatch "
                    "(id, actor_id, inventory_id, product_id, inventory_product_id, source, request_token, "
                    "input_fingerprint, quantity_units, remaining_quantity_units, quarantined_quantity_units, "
                    "unit_label_snapshot, expiry_date, receipt_sequence, received_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'manual', %s, %s, 1, 1, 0, 'each', NULL, 1, NOW())",
                    [
                        str(uuid.uuid4()), self.manager.pk, self.inventory.pk, self.other_product.pk,
                        self.link.pk, str(uuid.uuid4()), hashlib.sha256(b"bad scope").hexdigest(),
                    ],
                )

    def test_receiving_get_post_confirmation_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("receive-batch", args=[self.inventory.pk, self.product.pk]))
        self.assertEqual(response.status_code, 302)
        self.authenticate(self.manager, client)
        url = reverse("receive-batch", args=[self.inventory.pk, self.product.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        token = response.context["form"]["request_token"].value()
        data = {"request_token": str(token), "quantity_units": "2", "expiry_date": ""}
        denied = client.post(url, data)
        self.assertEqual(denied.status_code, 403)
        csrf = client.cookies["csrftoken"].value
        accepted = client.post(url, data, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(accepted.url, reverse("receipt-confirmation", args=[ReceivingBatch.objects.get().pk]))
        self.assertEqual(client.get(accepted.url).status_code, 200)

    def test_database_expiry_rejection_is_a_field_error_and_rolls_back_all_state(self):
        today = timezone.localdate()
        client = self.authenticate(self.manager)
        url = reverse("receive-batch", args=[self.inventory.pk, self.product.pk])
        get_response = client.get(url)
        token = get_response.context["form"]["request_token"].value()
        form_data = {
            "request_token": str(token),
            "quantity_units": "5",
            "expiry_date": today.isoformat(),
        }
        # Simulate the app-side date check occurring just before the database
        # observes Singapore midnight; PostgreSQL remains the final safeguard.
        with patch("receiving.services.timezone.localdate", return_value=today - timedelta(days=1)):
            response = client.post(url, form_data)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.context["form"]["expiry_date"].errors)
        self.assertEqual(ReceivingBatch.objects.count(), 0)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 0)
        self.assertFalse(ReceivingBatch.objects.filter(request_token=token).exists())
        self.link.refresh_from_db()
        self.assertEqual((self.link.physical_quantity_units, self.link.last_receipt_sequence), (0, 0))

    def test_unrelated_integrity_error_is_not_translated_to_expiry_error(self):
        with patch("receiving.services._create_receipt_audit", side_effect=IntegrityError("other constraint")):
            with self.assertRaises(IntegrityError):
                self.receive(quantity=4)
        self.link.refresh_from_db()
        self.assertEqual((self.link.physical_quantity_units, self.link.last_receipt_sequence), (0, 0))
        self.assertEqual(ReceivingBatch.objects.count(), 0)


class ReceivingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.business = Business.objects.create(name="Race business")
        self.user = get_user_model().objects.create_user(
            email="race-manager@example.test", password="test-only-password"
        )
        self.membership = BusinessMembership.objects.create(
            business=self.business, user=self.user, role=BusinessMembership.Role.MANAGER
        )
        self.inventory = Inventory.objects.create(business=self.business, name="Race shelf")
        InventoryAssignment.objects.create(membership=self.membership, inventory=self.inventory)
        self.product = Product.objects.create(
            business=self.business, sku="RACE-1", name="Race", base_unit_label="unit", expiry_tracking_required=False
        )
        self.link = InventoryProduct.objects.create(inventory=self.inventory, product=self.product)

    def _call_thread(self, barrier, **kwargs):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return receive_manual(**kwargs)
        finally:
            close_old_connections()

    def _race(self, kwargs_pair):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._call_thread, barrier, **kwargs) for kwargs in kwargs_pair]
            return [future.result(timeout=10) for future in futures]

    def _args(self, *, inventory=None, product=None, token=None, quantity=1):
        return {
            "user_id": self.user.pk,
            "inventory_id": (inventory or self.inventory).pk,
            "product_id": (product or self.product).pk,
            "request_token": token or uuid.uuid4(),
            "quantity_units": quantity,
            "expiry_date": None,
        }

    def test_two_connections_duplicate_token_commit_one_batch_and_event(self):
        token = uuid.uuid4()
        outcomes = self._race([self._args(token=token), self._args(token=token)])
        self.assertEqual(ReceivingBatch.objects.count(), 1)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)
        self.assertEqual(sum(1 for _, replayed in outcomes if replayed), 1)

    def test_token_collision_across_products_and_inventories_has_one_winner(self):
        other_inventory = Inventory.objects.create(business=self.business, name="Second race shelf")
        InventoryAssignment.objects.create(membership=self.membership, inventory=other_inventory)
        other_product = Product.objects.create(
            business=self.business, sku="RACE-2", name="Other race", base_unit_label="unit", expiry_tracking_required=False
        )
        InventoryProduct.objects.create(inventory=other_inventory, product=other_product)
        token = uuid.uuid4()
        args = [self._args(token=token), self._args(inventory=other_inventory, product=other_product, token=token)]
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._call_thread, barrier, **item) for item in args]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=10))
                except ReceiptRejected:
                    outcomes.append(None)
        self.assertEqual(ReceivingBatch.objects.count(), 1)
        self.assertEqual(ReceiptAuditEvent.objects.count(), 1)
        self.assertEqual(sum(outcome is not None for outcome in outcomes), 1)

    def test_competing_receipts_cannot_overflow_aggregate_balance(self):
        receive_manual(**self._args(quantity=MAX_RECEIPT_UNITS - 5))
        args = [self._args(quantity=4), self._args(quantity=4)]
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._call_thread, barrier, **item) for item in args]
            successes, failures = 0, 0
            for future in futures:
                try:
                    future.result(timeout=10)
                    successes += 1
                except ReceiptRejected:
                    failures += 1
        self.assertEqual((successes, failures), (1, 1))
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, MAX_RECEIPT_UNITS - 1)
        self.assertEqual(ReceivingBatch.objects.count(), 2)

    def test_competing_receipts_receive_unique_committed_sequences(self):
        args = [self._args(quantity=2), self._args(quantity=3)]
        self._race(args)
        self.assertEqual(list(ReceivingBatch.objects.order_by("receipt_sequence").values_list("receipt_sequence", flat=True)), [1, 2])

    def test_revocation_first_denies_receipt(self):
        assignment = InventoryAssignment.objects.get(membership=self.membership, inventory=self.inventory)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        with self.assertRaises(ReceiptRejected):
            receive_manual(**self._args())

    def test_database_requires_audit_event_before_batch_commit(self):
        token = uuid.uuid4()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO receiving_receivingbatch "
                        "(id, actor_id, inventory_id, product_id, inventory_product_id, source, request_token, "
                        "input_fingerprint, quantity_units, remaining_quantity_units, quarantined_quantity_units, "
                        "unit_label_snapshot, expiry_date, receipt_sequence, received_at) "
                        "VALUES (%s, %s, %s, %s, %s, 'manual', %s, %s, 1, 1, 0, 'unit', NULL, 1, NOW())",
                        [
                            str(uuid.uuid4()), self.user.pk, self.inventory.pk, self.product.pk,
                            self.link.pk, str(token), hashlib.sha256(b"no audit").hexdigest(),
                        ],
                    )
        self.link.refresh_from_db()
        self.assertEqual(self.link.physical_quantity_units, 0)
        self.assertFalse(ReceivingBatch.objects.filter(request_token=token).exists())

    def test_receipt_lock_first_blocks_revocation_until_receipt_commits(self):
        from receiving import services

        authorization_locked = Event()
        allow_commit = Event()
        revocation_started = Event()
        revocation_done = Event()
        original_audit = services._create_receipt_audit

        def pause_before_audit(batch, before):
            authorization_locked.set()
            if not allow_commit.wait(timeout=5):
                raise TimeoutError("bounded test synchronization expired")
            return original_audit(batch, before)

        def make_receipt():
            close_old_connections()
            try:
                with patch("receiving.services._create_receipt_audit", side_effect=pause_before_audit):
                    return receive_manual(**self._args(quantity=2))
            finally:
                close_old_connections()

        def revoke_assignment():
            close_old_connections()
            try:
                revocation_started.set()
                InventoryAssignment.objects.filter(
                    membership=self.membership, inventory=self.inventory
                ).update(is_active=False)
                revocation_done.set()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            receipt_future = pool.submit(make_receipt)
            self.assertTrue(authorization_locked.wait(timeout=5))
            revoke_future = pool.submit(revoke_assignment)
            self.assertTrue(revocation_started.wait(timeout=3))
            self.assertFalse(revocation_done.wait(timeout=0.2))
            allow_commit.set()
            batch, replayed = receipt_future.result(timeout=8)
            revoke_future.result(timeout=8)
        self.assertFalse(replayed)
        self.assertTrue(revocation_done.is_set())
        self.assertTrue(ReceiptAuditEvent.objects.filter(batch=batch).exists())

