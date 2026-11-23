"""Populate a non-production database with a reproducible demo snapshot."""

import os
import random
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
from django.db.models import Q
from django.utils import timezone

from catalogue.forms import PRODUCT_FIELDS
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

DEMO_SUPPLIERS = {"PH": "Harbour Medical Supplies", "GR": "Market Lane Wholesale"}
DEMO_WEEK_DAYS = 7
# Leave two dates for the Manager to verify without blocking the Oat Milk forecast.
DEMO_UNVERIFIED_SKU = "GR-07"
DEMO_UNVERIFIED_DAYS = 2
# Day-to-day demand varies by about +/-25%, with weekends 20% busier, so
# Insights shows a realistic forecast error (roughly 10-20%) rather than 0%.
# A fixed seed keeps every reseed and test run identical.
DEMO_DEMAND_SEED = 92
DEMO_DEMAND_SPREAD = 0.25
DEMO_WEEKEND_LIFT = 1.2

# SKU, display name, base unit, on-hand stock after the seeded history, days to expiry, typical daily issues.
INVENTORIES = {
    "Pharmacy": (
        ("PH-01", "Saline Nasal Spray", "bottle", 2, 3, 6),
        ("PH-02", "Oral Rehydration Salts", "sachet", 41, 5, 4),
        ("PH-03", "Sterile Dressings", "pack", 36, 60, 0),
        ("PH-04", "Digital Thermometer", "each", 25, None, 0),
        ("PH-05", "Hand Sanitizer", "bottle", 42, 90, 0),
        ("PH-06", "Nitrile Gloves", "box", 31, None, 0),
        ("PH-07", "Cotton Pads", "pack", 33, None, 0),
        ("PH-08", "Medical Tape", "roll", 24, None, 0),
    ),
    "Grocery": (
        ("GR-01", "Oat Milk", "carton", 4, 6, 6),
        ("GR-02", "Jasmine Rice", "bag", 43, 180, 4),
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


def _demo_category(business, sku):
    label = next((name for name, skus in DEMO_CATEGORIES.items() if sku in skus), None)
    if label is None:
        return None
    # Reuse a category the Manager already made with the same name (any case).
    category = Category.objects.filter(business=business, name__iexact=label).order_by("pk").first()
    return category or Category.objects.create(business=business, name=label)


def _ordering_settings(sku):
    return {"lead_time_days": 3, "safety_stock_units": 5, "supplier_name": DEMO_SUPPLIERS[sku[:2]]}


def _backfill_products(business, manager):
    """Fill missing demo categories and ordering settings through the audited edit."""
    categories = settings_filled = 0
    products = Product.objects.filter(business=business, sku__in=DEMO_PRICES).filter(
        Q(category__isnull=True) | Q(lead_time_days__isnull=True) | Q(safety_stock_units__isnull=True)
        | Q(supplier_name=""),
    ).order_by("pk")
    for product in products:
        link = product.inventory_links.filter(inventory__is_active=True).select_related("inventory").order_by("pk").first()
        if link is None:
            continue
        defaults = _ordering_settings(product.sku)
        changes = {field: value for field, value in defaults.items() if getattr(product, field) in (None, "")}
        settings_filled += bool(changes)
        if product.category_id is None:
            changes["category"] = _demo_category(business, product.sku)
            categories += 1
        if save_product_change is not None:
            values = {field: getattr(product, field) for field in PRODUCT_FIELDS}
            values.update(changes)
            save_product_change(user=manager, inventory=link.inventory, values=values, product_id=product.pk)
        else:
            Product.objects.filter(pk=product.pk).update(**changes)
    return categories, settings_filled


def _backfill(business):
    """Fill blank demo fields without changing stock movements or demand coverage."""
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
    categories, settings_filled = _backfill_products(business, manager)
    return users, prices, categories, settings_filled


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


def demo_demand(sku, typical, dates):
    """Deterministic daily issue quantities for one SKU: at least one unit on each date."""
    if not typical:
        return [0] * len(dates)
    rng = random.Random(f"{DEMO_DEMAND_SEED}:{sku}")
    return [
        max(1, round(typical * rng.uniform(1 - DEMO_DEMAND_SPREAD, 1 + DEMO_DEMAND_SPREAD)
                     * (DEMO_WEEKEND_LIFT if day.weekday() >= 5 else 1)))
        for day in dates
    ]


def _seed_inventory(inventory, manager, staff, dates, now):
    today = now.astimezone(SINGAPORE).date()
    received_at = datetime.combine(dates[0], time(8), SINGAPORE)
    unverified_dates = dates[-DEMO_UNVERIFIED_DAYS:]
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
            "category": categories[sku], **_ordering_settings(sku),
        })
        _set_price(manager, inventory, product.pk, sku)
        scope = {"inventory_id": inventory.pk, "product_id": product.pk}
        expiry = today + timedelta(days=expiry_offset) if expiry_offset is not None else None
        issues = demo_demand(sku, daily_issue, dates)
        # Receive enough to cover the seeded issues and leave the listed on-hand stock.
        opening_quantity = quantity + sum(issues)
        receive_manual(user_id=manager.pk, **scope, request_token=uuid4(), quantity_units=opening_quantity,
                       expiry_date=expiry, demo_received_at=received_at)
        if sku == "PH-03":
            # The expired demo batch must use the receipt guard's recent demo window.
            recent_receipt = datetime.combine(dates[-DEMO_WEEK_DAYS], time(8), SINGAPORE)
            receive_manual(user_id=manager.pk, **scope, request_token=uuid4(), quantity_units=6,
                           expiry_date=today - timedelta(days=1), demo_received_at=recent_receipt)
        for day, issued in zip(dates, issues, strict=True):
            if issued:
                issue_stock(user_id=staff.pk, **scope, quantity_units=issued,
                            demo_issued_at=datetime.combine(day, time(12), SINGAPORE))
            if sku != DEMO_UNVERIFIED_SKU or day not in unverified_dates:
                verify_demand_day(user_id=manager.pk, **scope, day=day, at=now)


class Command(BaseCommand):
    help = "Create the Tory demo and two weeks of sample history in a non-production database."

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
        dates = [today - timedelta(days=offset) for offset in range(2 * DEMO_WEEK_DAYS, 0, -1)]
        generated = {}
        with transaction.atomic():
            lock_activation(shared=False)
            businesses = list(Business.objects.filter(name=DEMO_BUSINESS_NAME))
            if businesses:
                memberships = dict(businesses[0].memberships.values_list("role", "user__email"))
                if len(businesses) != 1 or memberships != logins:
                    raise CommandError("The demo business name is already in use with different accounts.")
                users, prices, categories, settings_filled = _backfill(businesses[0])
                self.stdout.write("Tory Demo is already seeded.")
                if users or prices or categories:
                    self.stdout.write(f"Backfilled {users} demo profile(s), {prices} selling price(s) "
                                      f"and {categories} product categor{'y' if categories == 1 else 'ies'}.")
                if settings_filled:
                    self.stdout.write(f"Backfilled ordering settings for {settings_filled} demo product(s).")
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
