import getpass
import warnings

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from inventory_access.models import (
    Business,
    BusinessMembership,
    Inventory,
    InventoryAssignment,
)


class Command(BaseCommand):
    help = "Create a business, its initial inventories, and an assigned Manager."

    def add_arguments(self, parser):
        parser.add_argument("--business-name", required=True)
        parser.add_argument("--manager-email", required=True)
        parser.add_argument(
            "--inventory",
            dest="inventory_names",
            action="append",
            required=True,
            help="Name an initial inventory; repeat this option for multiple inventories.",
        )

    @staticmethod
    def _clean_model_field(model, name, value):
        field = model._meta.get_field(name)
        try:
            return field.clean(value, None)
        except ValidationError as error:
            raise CommandError(
                "Invalid %s: %s" % (name.replace("_", " "), error.messages[0])
            ) from error

    def _password(self, user):
        try:
            # getpass warns before reading when it must fall back to visible input.
            # Promote that warning to an exception so a password is never echoed.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Manager password: ")
                confirmation = getpass.getpass("Confirm password: ")
        except (getpass.GetPassWarning, EOFError, OSError, KeyboardInterrupt) as error:
            raise CommandError("Hidden password input is unavailable; no records were created.") from error

        if password != confirmation:
            raise CommandError("Passwords do not match; no records were created.")
        if not password:
            raise CommandError("Password cannot be blank; no records were created.")
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(
                "Password does not meet the configured requirements: " + "; ".join(error.messages)
            ) from error
        return password

    def handle(self, *args, **options):
        User = get_user_model()
        business_name = self._clean_model_field(Business, "name", options["business_name"])
        inventory_names = [
            self._clean_model_field(Inventory, "name", name)
            for name in options["inventory_names"]
        ]
        if not inventory_names:
            raise CommandError("At least one --inventory is required; no records were created.")
        email = self._clean_model_field(User, "email", options["manager_email"])
        email = User.objects.normalize_email(email)

        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("An account with this email already exists; no records were created.")

        manager = User(email=email, is_active=True, is_staff=False, is_superuser=False)
        password = self._password(manager)
        manager.set_password(password)

        try:
            with transaction.atomic():
                manager.save()
                business = Business.objects.create(name=business_name)
                membership = BusinessMembership.objects.create(
                    business=business,
                    user=manager,
                    role=BusinessMembership.Role.MANAGER,
                    is_active=True,
                )
                for name in inventory_names:
                    inventory = Inventory.objects.create(
                        business=business,
                        name=name,
                        is_active=True,
                    )
                    InventoryAssignment.objects.create(
                        membership=membership,
                        inventory=inventory,
                        is_active=True,
                    )
        except IntegrityError as error:
            # This also handles an email inserted concurrently after the preflight check.
            if User.objects.filter(email__iexact=email).exists():
                raise CommandError(
                    "An account with this email already exists; no records were created."
                ) from error
            raise CommandError("Setup could not be completed; no records were created.") from error

        self.stdout.write(
            self.style.SUCCESS(
                "Created Manager %s for business %s with %d assigned inventory item(s)."
                % (manager.email, business.name, len(inventory_names))
            )
        )
