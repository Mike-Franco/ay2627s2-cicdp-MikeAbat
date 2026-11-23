"""Populate a non-production database with a reproducible demo snapshot."""

import os
from datetime import datetime, time, timedelta
from decimal import Decimal
from secrets import token_urlsafe
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalogue.models import Category, InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.commit_times import lock_activation, tracking_enabled
from receiving.demand import verify_demand_day
from receiving.models import ObservationActivation
from receiving.services import DEMO_BUSINESS_NAME, SINGAPORE, issue_stock, receive_manual

try:
    from catalogue.product_changes import save_product_change
except ModuleNotFoundError as error:
    if error.name != "catalogue.product_changes":
        raise
    save_product_change = None

try:
    from catalogue.product_changes import save_selling_price
except ImportError:
    save_selling_price = None


# TORY-54: how each demo inventory looks (icon key, colour key).
INVENTORY_LOOKS = {"Pharmacy": ("pill", "teal"), "Grocery": ("shopping-cart", "orange")}

# SKU, display name, base unit, opening stock, days to expiry, daily issues.
INVENTORIES = {
    "Pharmacy": (
        ("PH-01", "Saline Nasal Spray", "bottle", 16, 3, 2),
        ("PH-02", "Oral Rehydration Salts", "sachet", 48, 5, 1),
        ("PH-03", "Sterile Dressings", "pack", 36, 60, 0),
        ("PH-04", "Digital Thermometer", "each", 25, None, 0),
        ("PH-05", "Hand Sanitizer", "bottle", 42, 90, 0),
        ("PH-06", "Nitrile Gloves", "box", 31, None, 0),
        ("PH-07", "Cotton Pads", "pack", 33, None, 0),
        ("PH-08", "Medical Tape", "roll", 24, None, 0),
    ),
    "Grocery": (
        ("GR-01", "Oat Milk", "carton", 18, 6, 2),
        ("GR-02", "Jasmine Rice", "bag", 50, 180, 1),
        ("GR-03", "Rolled Oats", "bag", 32, 70, 0),
        ("GR-04", "Canned Chickpeas", "can", 44, 120, 0),
        ("GR-05", "Black Tea", "box", 26, 100, 0),
        ("GR-06", "Olive Oil", "bottle", 29, 75, 0),
        ("GR-07", "Reusable Grocery Bag", "each", 20, None, 0),
    ),
}


# Retail selling prices in SGD per demo SKU (typical Singapore shelf prices).
DEMO_PRICES = {
    "PH-01": "12.90", "PH-02": "1.20", "PH-03": "6.50", "PH-04": "15.90",
    "PH-05": "4.95", "PH-06": "11.50", "PH-07": "2.80", "PH-08": "3.40",
    "GR-01": "4.65", "GR-02": "13.80", "GR-03": "5.25", "GR-04": "1.85",
    "GR-05": "6.40", "GR-06": "14.90", "GR-07": "2.50",
}

# Display name, job title and avatar colour for the two demo logins.
DEMO_PROFILES = {
    "manager": ("Mia Tan", "Store Manager", "teal"),
    "staff": ("Ravi Kumar", "Stock Assistant", "orange"),
}


DEMO_CATEGORIES = {
    "Medicine": ("PH-01", "PH-02"),
    "First aid": ("PH-03", "PH-04", "PH-06", "PH-08"),
    "Personal care": ("PH-05", "PH-07"),
    "Dairy alternatives": ("GR-01",),
    "Pantry": ("GR-02", "GR-03", "GR-04", "GR-06"),
    "Beverages": ("GR-05",),
    "Household": ("GR-07",),
}


def _create_login(user_model, email, password_env):
    supplied = os.getenv(password_env)
    password = supplied or token_urlsafe(24)
    try:
        user_model._meta.get_field("email").clean(email, None)
        validate_password(password, user_model(email=email))
    except ValidationError as error:
        raise CommandError(f"Invalid demo credentials for {email}: {' '.join(error.messages)}") from error
    return user_model.objects.create_user(email=email, password=password), None if supplied else password


def _create_product(manager, inventory, values):
    if save_product_change is not None:
        return save_product_change(user=manager, inventory=inventory, values=values,
                                   inventory_ids=(inventory.pk,))
    # Earlier develop revisions have no product creation audit service.
    product = Product.objects.create(business_id=inventory.business_id, **values)
    InventoryProduct.objects.create(inventory=inventory, product=product)
    return product


def _set_price(manager, inventory, product_id, sku):
    price = Decimal(DEMO_PRICES[sku])
    if save_selling_price is not None:
        save_selling_price(user=manager, inventory=inventory, product_id=product_id, price=price)
    else:
        InventoryProduct.objects.filter(inventory=inventory, product_id=product_id).update(selling_price=price)


def _apply_profile(user, role):
    """Fill blank profile fields only, so names a user has edited are kept."""
    name, title, colour = DEMO_PROFILES[role]
    changed = []
    if not user.display_name.strip():
        user.display_name = name
        changed.append("display_name")
    if not user.job_title.strip():
        user.job_title = title
        changed.append("job_title")
    if changed:
        if user.avatar_colour == type(user)._meta.get_field("avatar_colour").default:
            user.avatar_colour = colour
            changed.append("avatar_colour")
        user.save(update_fields=changed)
    return bool(changed)


def _backfill(business):
    """Add demo prices and names to an existing demo without touching stock or history.

    Only blank values are filled: products without a selling price get the demo
    price through the audited price service, and users without a display name
    or job title get the demo profile. Returns (users, prices) filled.
    """
    users = sum(_apply_profile(membership.user, membership.role)
                for membership in business.memberships.select_related("user"))
    manager = business.memberships.get(role=BusinessMembership.Role.MANAGER).user
    prices = 0
    links = InventoryProduct.objects.filter(
        inventory__business=business, inventory__is_active=True, selling_price__isnull=True,
        product__sku__in=DEMO_PRICES,
    ).select_related("inventory", "product").order_by("pk")
    for link in links:
        _set_price(manager, link.inventory, link.product_id, link.product.sku)
        prices += 1
    return users, prices


def _ensure_observation(first_day):
    activation = ObservationActivation.objects.filter(
        environment=settings.DJANGO_ENV, state__in=("pending", "active"),
    ).first()
    if activation is not None:
        if activation.state == "active" and activation.first_observed_date <= first_day:
            return
        raise CommandError("The existing observation boundary does not cover the demo week. Use a fresh demo database.")
    if Business.objects.exists() or ObservationActivation.objects.exists():
        raise CommandError("Synthetic demand activation requires a fresh demo database.")
    # This is historical fixture data in a fresh database, as in the forecast
    # tests. The operational activation command still requires a future date.
    ObservationActivation.objects.create(
        environment=settings.DJANGO_ENV, state="active", first_observed_date=first_day,
        origin_xid="0", actual_committed_at=datetime.combine(first_day, time.min, SINGAPORE)
        - timedelta(seconds=1),
    )


def _seed_inventory(inventory, manager, staff, dates, now):
    today = now.astimezone(SINGAPORE).date()
    received_at = datetime.combine(dates[0], time(8), SINGAPORE)
    skus = {row[0] for row in INVENTORIES[inventory.name]}
    categories = {}
    for label, category_skus in DEMO_CATEGORIES.items():
        matching = skus.intersection(category_skus)
        if matching:
            category, _ = Category.objects.get_or_create(business=inventory.business, name=label)
            categories.update(dict.fromkeys(matching, category))
    for sku, name, unit, quantity, expiry_offset, daily_issue in INVENTORIES[inventory.name]:
        product = _create_product(manager, inventory, {
            "sku": sku, "name": name, "base_unit_label": unit,
            "expiry_tracking_required": expiry_offset is not None,
            "lead_time_days": 3, "safety_stock_units": 5, "category": categories[sku],
        })
        _set_price(manager, inventory, product.pk, sku)
        scope = {"inventory_id": inventory.pk, "product_id": product.pk}
        expiry = today + timedelta(days=expiry_offset) if expiry_offset is not None else None
        receive_manual(user_id=manager.pk, **scope, request_token=uuid4(), quantity_units=quantity,
                       expiry_date=expiry, demo_received_at=received_at)
        if sku == "PH-03":
            receive_manual(user_id=manager.pk, **scope, request_token=uuid4(), quantity_units=6,
                           expiry_date=today - timedelta(days=1), demo_received_at=received_at)
        for day in dates:
            if daily_issue:
                issue_stock(user_id=staff.pk, **scope, quantity_units=daily_issue,
                            demo_issued_at=datetime.combine(day, time(12), SINGAPORE))
            # Verify every seeded date, including zero-demand ones, so a fresh
            # demo shows numeric forecasts and no unverified-day warnings.
            verify_demand_day(user_id=manager.pk, **scope, day=day, at=now)


class Command(BaseCommand):
    help = "Create the Tory demo and seven days of sample history in a non-production database."

    def handle(self, *args, **options):
        if settings.DJANGO_ENV == "production" or os.getenv("DJANGO_ENV", "").lower() == "production":
            raise CommandError("seed_demo is disabled in production.")

        User = get_user_model()
        roles = BusinessMembership.Role
        logins = {
            roles.MANAGER: User.objects.normalize_email(os.getenv("DEMO_MANAGER_EMAIL") or "manager@tory-demo.test"),
            roles.STAFF: User.objects.normalize_email(os.getenv("DEMO_STAFF_EMAIL") or "staff@tory-demo.test"),
        }
        if logins[roles.MANAGER] == logins[roles.STAFF]:
            raise CommandError("The demo Manager and Staff emails must be different.")

        now = timezone.now()
        today = now.astimezone(SINGAPORE).date()
        dates = [today - timedelta(days=offset) for offset in range(7, 0, -1)]
        generated = {}
        with transaction.atomic():
            lock_activation(shared=False)
            businesses = list(Business.objects.filter(name=DEMO_BUSINESS_NAME))
            if businesses:
                memberships = dict(businesses[0].memberships.values_list("role", "user__email"))
                if len(businesses) != 1 or memberships != logins:
                    raise CommandError("The demo business name is already in use with different accounts.")
                users, prices = _backfill(businesses[0])
                self.stdout.write("Tory Demo is already seeded.")
                if users or prices:
                    self.stdout.write(f"Backfilled {users} demo profile(s) and {prices} selling price(s).")
                return
            if User.objects.filter(email__in=logins.values()).exists():
                raise CommandError("A demo email is already in use. Configure distinct demo emails.")
            if not tracking_enabled():
                raise CommandError("PostgreSQL track_commit_timestamp must be on for numeric demo forecasts.")
            _ensure_observation(dates[0])

            business = Business.objects.create(name=DEMO_BUSINESS_NAME)
            members = {}
            for role, email in logins.items():
                user, generated[role] = _create_login(User, email, f"DEMO_{role.upper()}_PASSWORD")
                members[role] = BusinessMembership.objects.create(business=business, user=user, role=role)
                _apply_profile(user, role)
            for name in INVENTORIES:
                icon, colour = INVENTORY_LOOKS.get(name, ("package", "slate"))
                inventory = Inventory.objects.create(business=business, name=name, icon=icon, colour=colour)
                for member in members.values():
                    InventoryAssignment.objects.create(inventory=inventory, membership=member)
                _seed_inventory(inventory, members[roles.MANAGER].user, members[roles.STAFF].user, dates, now)

        self.stdout.write(self.style.SUCCESS("Seeded Tory Demo with Pharmacy and Grocery."))
        for role, email in logins.items():
            self.stdout.write(f"{role.label} email: {email}")
            if generated[role] is not None:
                self.stdout.write(f"{role.label} generated password: {generated[role]}")
