import getpass
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase, override_settings

from inventory_access.authorization import authorized_inventories
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


PASSWORD = "unique-strong-bootstrap-password"
COMMON_PASSWORD = "1234567890qwertyuiop"


class BootstrapManagerCommandTests(TestCase):
    def command(self, **overrides):
        options = {
            "business_name": "Harbour Clinic",
            "manager_email": "manager@example.test",
            "inventory_names": ["Main Store", "Cold Room"],
        }
        options.update(overrides)
        inventory_names = options.pop("inventory_names")
        command_args = [
            "--business-name",
            options["business_name"],
            "--manager-email",
            options["manager_email"],
        ]
        for inventory_name in inventory_names:
            command_args.extend(("--inventory", inventory_name))
        return call_command("bootstrap_manager", *command_args)

    def submit_password(self, password=PASSWORD, confirmation=None):
        return patch(
            "accounts.management.commands.bootstrap_manager.getpass.getpass",
            side_effect=[password, password if confirmation is None else confirmation],
        )

    def test_project_password_validators_match_the_approved_policy(self):
        self.assertEqual(
            settings.AUTH_PASSWORD_VALIDATORS,
            [
                {
                    "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                    "OPTIONS": {"min_length": 15},
                },
                {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
                {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
            ],
        )

    def test_project_policy_accepts_15_character_lowercase_passphrase(self):
        password = "mellowriveroakx"
        self.assertEqual(len(password), 15)
        self.assertTrue(password.islower() and password.isalpha())

        with self.submit_password(password):
            self.command()

        manager = get_user_model().objects.get(email="manager@example.test")
        self.assertTrue(manager.check_password(password))

    def test_project_policy_rejects_short_common_and_email_similar_passwords_without_writes(self):
        self.assertGreaterEqual(len(COMMON_PASSWORD), 15)
        self.assertIn(COMMON_PASSWORD, CommonPasswordValidator().passwords)
        rejected_passwords = [
            ("mellowriveroak", "at least 15"),
            (COMMON_PASSWORD, "too common"),
            ("manager@example.test", "too similar"),
        ]
        for password, message in rejected_passwords:
            with self.subTest(password_kind=message):
                with self.submit_password(password), self.assertRaises(CommandError) as raised:
                    self.command()
                self.assertIn(message, str(raised.exception).lower())
                self.assertEqual(get_user_model().objects.count(), 0)
                self.assertEqual(Business.objects.count(), 0)
                self.assertEqual(BusinessMembership.objects.count(), 0)
                self.assertEqual(Inventory.objects.count(), 0)
                self.assertEqual(InventoryAssignment.objects.count(), 0)

    def test_creates_ordinary_manager_and_assigns_every_created_inventory(self):
        with self.submit_password():
            self.command()

        User = get_user_model()
        manager = User.objects.get(email="manager@example.test")
        membership = BusinessMembership.objects.get(user=manager)
        inventories = list(Inventory.objects.filter(business=membership.business))

        self.assertTrue(manager.is_active)
        self.assertFalse(manager.is_staff)
        self.assertFalse(manager.is_superuser)
        self.assertTrue(manager.check_password(PASSWORD))
        self.assertNotEqual(manager.password, PASSWORD)
        self.assertEqual(membership.role, BusinessMembership.Role.MANAGER)
        self.assertTrue(membership.is_active)
        self.assertEqual({item.name for item in inventories}, {"Main Store", "Cold Room"})
        assignments = InventoryAssignment.objects.filter(membership=membership, is_active=True)
        self.assertSetEqual(
            set(assignments.values_list("inventory_id", flat=True)),
            {item.pk for item in inventories},
        )
        self.assertSetEqual(
            set(authorized_inventories(manager).values_list("pk", flat=True)),
            {item.pk for item in inventories},
        )
        self.assertEqual(Business.objects.count(), 1)
        self.assertEqual(InventoryAssignment.objects.count(), 2)

    def test_existing_email_case_collision_does_not_create_or_attach_records(self):
        User = get_user_model()
        existing = User.objects.create_user(email="Existing@Example.test", password="old-password")
        business = Business.objects.create(name="Existing business")
        membership = BusinessMembership.objects.create(
            business=business, user=existing, role=BusinessMembership.Role.STAFF
        )
        inventory = Inventory.objects.create(business=business, name="Existing shelf")
        InventoryAssignment.objects.create(membership=membership, inventory=inventory)

        with self.submit_password() as prompt, self.assertRaises(CommandError):
            self.command(manager_email="existing@example.TEST")

        prompt.assert_not_called()
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Business.objects.count(), 1)
        self.assertEqual(BusinessMembership.objects.count(), 1)
        self.assertEqual(Inventory.objects.count(), 1)
        self.assertEqual(InventoryAssignment.objects.count(), 1)
        self.assertEqual(existing.email, "existing@example.test")

    def test_invalid_business_inventory_and_email_inputs_fail_before_prompt_or_write(self):
        bad_inputs = [
            {"business_name": ""},
            {"inventory_names": [""]},
            {"inventory_names": []},
            {"manager_email": "not-an-email"},
            {"business_name": "x" * 161},
            {"inventory_names": ["x" * 161]},
        ]
        for changes in bad_inputs:
            with self.subTest(changes=changes):
                with self.submit_password() as prompt, self.assertRaises(CommandError):
                    self.command(**changes)
                prompt.assert_not_called()
                self.assertEqual(get_user_model().objects.count(), 0)
                self.assertEqual(Business.objects.count(), 0)
                self.assertEqual(Inventory.objects.count(), 0)

    def test_password_mismatch_fails_without_writing(self):
        with self.submit_password(PASSWORD, "different-password"):
            with self.assertRaisesMessage(CommandError, "Passwords do not match"):
                self.command()
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Business.objects.count(), 0)

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {
                "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                "OPTIONS": {"min_length": 20},
            }
        ]
    )
    def test_configured_password_validation_fails_without_writing(self):
        with self.submit_password("short", "short"):
            with self.assertRaisesMessage(CommandError, "configured requirements"):
                self.command()
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Business.objects.count(), 0)

    def test_interrupted_or_unavailable_hidden_input_fails_without_writing(self):
        for failure in (
            KeyboardInterrupt(),
            OSError("no hidden input"),
            getpass.GetPassWarning("hidden input unavailable"),
        ):
            with self.subTest(failure=type(failure).__name__):
                with patch(
                    "accounts.management.commands.bootstrap_manager.getpass.getpass",
                    side_effect=failure,
                ), self.assertRaisesMessage(CommandError, "Hidden password input is unavailable"):
                    self.command()
                self.assertEqual(get_user_model().objects.count(), 0)
                self.assertEqual(Business.objects.count(), 0)

    def test_failure_during_assignment_creation_rolls_back_every_record(self):
        create_assignment = InventoryAssignment.objects.create
        calls = 0

        def create_then_fail(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise IntegrityError("injected assignment failure")
            return create_assignment(**kwargs)

        with self.submit_password(), patch.object(
            InventoryAssignment.objects,
            "create",
            side_effect=create_then_fail,
        ):
            with self.assertRaisesMessage(CommandError, "no records were created"):
                self.command()

        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Business.objects.count(), 0)
        self.assertEqual(BusinessMembership.objects.count(), 0)
        self.assertEqual(Inventory.objects.count(), 0)
        self.assertEqual(InventoryAssignment.objects.count(), 0)

    def test_repeated_setup_rejects_without_changing_existing_records(self):
        with self.submit_password():
            self.command()

        models = (
            get_user_model(),
            Business,
            BusinessMembership,
            Inventory,
            InventoryAssignment,
        )
        records_before = {
            model.__name__: list(model.objects.order_by("pk").values()) for model in models
        }
        with self.submit_password() as prompt, self.assertRaises(CommandError):
            self.command()

        prompt.assert_not_called()
        self.assertEqual(
            records_before,
            {model.__name__: list(model.objects.order_by("pk").values()) for model in models},
        )
