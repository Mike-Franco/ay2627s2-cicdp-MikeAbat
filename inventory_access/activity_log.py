"""Manager activity log (TORY-61): who did what across a business, read-only.

Built only from the existing audit tables. Each source becomes a ``values()``
query with the same columns; they are combined with ``UNION ALL``, ordered and
paginated in PostgreSQL, and only the rows on the page are then hydrated with
a fixed number of bulk lookups, so the query count does not grow with history.
"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import BigIntegerField, Case, CharField, F, Q, TextField, Value, When
from django.db.models.functions import Cast, Concat

from accounts.models import StaffInvitation
from catalogue.models import Product, ProductChangeAuditEvent, ProductLifecycleAuditEvent
from receiving.models import (
    DemandAuditEvent, DemandCoverageEvent, DisposalAuditEvent, ExpiryQuarantineEvent, ReceiptAuditEvent,
    StockAdjustmentAuditEvent,
)
from receiving.services import SINGAPORE

from .models import BusinessMembership, Inventory, InventoryAccessAuditEvent, InventoryChangeAuditEvent

KINDS = (
    ("receipt", "Stock received"),
    ("issue", "Stock issued"),
    ("adjustment", "Count adjusted"),
    ("disposal", "Stock disposed"),
    ("quarantine", "Expiry quarantine"),
    ("verification", "Demand day reviewed"),
    ("product", "Product created or edited"),
    ("lifecycle", "Product activated or deactivated"),
    ("inventory", "Inventory changed"),
    ("access", "Inventory access changed"),
    ("invitation", "Staff invitation sent"),
)
KIND_LABELS = dict(KINDS)
# TORY-67: Staff see stock movements only (CSV imports arrive as receipts and issues);
# settings, access, product and demand-review rows stay Manager-only.
STAFF_KINDS = ("receipt", "issue", "adjustment", "quarantine")
# Short pill label and tone per kind, as in docs/ui-reference/v1.2/mockup/ActivityLog.dc.html.
PILLS = {
    "receipt": ("Received", "green"), "issue": ("Issued", "amber"), "adjustment": ("Adjusted", "neutral"),
    "disposal": ("Disposed", "red"), "quarantine": ("Quarantined", "red"), "verification": ("Verified", "blue"),
    "product": ("Product", "neutral"), "lifecycle": ("Product", "neutral"), "inventory": ("Settings", "neutral"),
    "access": ("Access", "neutral"), "invitation": ("Invitation", "neutral"),
}
SYSTEM_ACTOR = "System (expiry quarantine)"
NULL_INT = Value(None, output_field=BigIntegerField())
NULL_TEXT = Value(None, output_field=TextField())


def _text(expression):
    return Cast(expression, output_field=TextField())


def _source(queryset, kind, *, at, actor, inventory, product, change=NULL_INT, before=NULL_INT, after=NULL_INT,
            note=NULL_TEXT):
    # Prefixed names avoid clashing with model fields (several have before/after).
    return queryset.order_by().annotate(
        a_kind=Value(kind, output_field=CharField()), a_ref=Cast("pk", BigIntegerField()), a_at=at,
        a_actor=Cast(actor, BigIntegerField()), a_inventory=Cast(inventory, BigIntegerField()),
        a_product=Cast(product, BigIntegerField()), a_change=Cast(change, BigIntegerField()),
        a_before=Cast(before, BigIntegerField()), a_after=Cast(after, BigIntegerField()),
        a_note=Cast(note, TextField()),
    ).values_list(*ANNOTATED)


COLUMNS = ("kind", "ref", "at", "actor_id", "inventory_id", "product_id", "change", "before", "after", "note")
ANNOTATED = ("a_kind", "a_ref", "a_at", "a_actor", "a_inventory", "a_product", "a_change", "a_before", "a_after",
             "a_note")


def _csv_note(import_field):
    return Case(When(**{f"{import_field}__isnull": False}, then=Concat(
        Value("CSV import "), _text(import_field), output_field=TextField())), default=NULL_TEXT)


def _sources(business_id):
    scope = {"business_id": business_id}
    coverage_inventory = "coverage_day__inventory_product__inventory"
    return {
        "receipt": _source(
            ReceiptAuditEvent.objects.filter(**scope), "receipt", at=F("occurred_at"), actor=F("actor_id"),
            inventory=F("inventory_id"), product=F("product_id"), change=F("quantity_change_units"),
            before=F("quantity_before_units"), after=F("quantity_after_units"),
            note=_csv_note("batch__import_record_id")),
        "issue": _source(
            DemandAuditEvent.objects.filter(**scope), "issue", at=F("occurred_at"), actor=F("actor_id"),
            inventory=F("inventory_id"), product=F("product_id"), change=-F("quantity_change_units"),
            before=F("quantity_before_units"), after=F("quantity_after_units"),
            note=_csv_note("stock_out__import_record_id")),
        "adjustment": _source(
            StockAdjustmentAuditEvent.objects.filter(**scope), "adjustment", at=F("occurred_at"),
            actor=F("actor_id"), inventory=F("inventory_id"), product=F("product_id"),
            change=F("quantity_change_units"), before=F("quantity_before_units"), after=F("quantity_after_units"),
            note=_text("reason")),
        "disposal": _source(
            DisposalAuditEvent.objects.filter(**scope), "disposal", at=F("occurred_at"), actor=F("actor_id"),
            inventory=F("inventory_id"), product=F("product_id"), change=-F("quantity_units"),
            before=F("physical_before_units"), after=F("physical_after_units"),
            note=Concat(_text("reason_code"), Value(": "), _text("reason_note"), output_field=TextField())),
        "quarantine": _source(
            ExpiryQuarantineEvent.objects.filter(**scope), "quarantine", at=F("recorded_at"), actor=NULL_INT,
            inventory=F("inventory_id"), product=F("product_id"),
            change=F("quarantine_after_units") - F("quarantine_before_units"),
            before=F("available_before_units"), after=F("available_after_units")),
        "verification": _source(
            DemandCoverageEvent.objects.filter(**{f"{coverage_inventory}__business_id": business_id}),
            "verification", at=F("recorded_at"), actor=F("actor_id"), inventory=F(f"{coverage_inventory}_id"),
            product=F("coverage_day__inventory_product__product_id"), after=F("verified_total_units"),
            note=Concat(_text("action"), Value(" "), _text("coverage_day__day"), Value(" "), _text("reason"),
                        output_field=TextField())),
        "product": _source(
            ProductChangeAuditEvent.objects.filter(**scope), "product", at=F("occurred_at"), actor=F("actor_id"),
            inventory=F("inventory_id"), product=F("product_id"), note=_text("action")),
        "lifecycle": _source(
            ProductLifecycleAuditEvent.objects.filter(**scope), "lifecycle", at=F("occurred_at"),
            actor=F("actor_id"), inventory=F("inventory_id"), product=F("product_id"), note=_text("action")),
        "inventory": _source(
            InventoryChangeAuditEvent.objects.filter(**scope), "inventory", at=F("occurred_at"),
            actor=F("actor_id"), inventory=F("inventory_id"), product=NULL_INT, note=_text("action")),
        "access": _source(
            InventoryAccessAuditEvent.objects.filter(**scope), "access", at=F("occurred_at"),
            actor=F("actor_id"), inventory=F("inventory_id"), product=NULL_INT),
        "invitation": _source(
            StaffInvitation.objects.filter(**scope), "invitation", at=F("issued_at"), actor=F("invited_by_id"),
            inventory=NULL_INT, product=NULL_INT, note=_text("target_email")),
    }


TIME_FIELDS = {"quarantine": "recorded_at", "verification": "recorded_at", "invitation": "issued_at"}
ACTOR_FIELDS = {"invitation": "invited_by_id", "quarantine": None}
INVENTORY_FIELDS = {"verification": "coverage_day__inventory_product__inventory_id", "invitation": None}
PRODUCT_FIELDS = {"verification": "coverage_day__inventory_product__product_id", "inventory": None,
                  "access": None, "invitation": None}


def activity_rows(business_id, *, actor_id=None, kinds=(), inventory_id=None, product_query="", start=None,
                  end=None, inventory_ids=None):
    """The filtered, newest-first union queryset of activity tuples (see COLUMNS).

    inventory_ids, when given, limits every source to those inventories (the Staff
    view, TORY-67); sources without an inventory are then left out.
    """
    product_ids = None
    if product_query:
        product_ids = Product.objects.filter(business_id=business_id).filter(
            Q(name__icontains=product_query) | Q(sku__icontains=product_query)).values("pk")
    parts = []
    for kind, queryset in _sources(business_id).items():
        if kinds and kind not in kinds:
            continue
        filters = Q()
        time_field = TIME_FIELDS.get(kind, "occurred_at")
        if start:
            filters &= Q(**{f"{time_field}__gte": datetime.combine(start, time.min, SINGAPORE)})
        if end:
            filters &= Q(**{f"{time_field}__lt": datetime.combine(end + timedelta(days=1), time.min, SINGAPORE)})
        if actor_id is not None:
            field = ACTOR_FIELDS.get(kind, "actor_id")
            if field is None:
                continue
            filters &= Q(**{field: actor_id})
        if inventory_id is not None:
            field = INVENTORY_FIELDS.get(kind, "inventory_id")
            if field is None:
                continue
            filters &= Q(**{field: inventory_id})
        if inventory_ids is not None:
            field = INVENTORY_FIELDS.get(kind, "inventory_id")
            if field is None:
                continue
            filters &= Q(**{f"{field}__in": inventory_ids})
        if product_ids is not None:
            field = PRODUCT_FIELDS.get(kind, "product_id")
            if field is None:
                continue
            filters &= Q(**{f"{field}__in": product_ids})
        parts.append(queryset.filter(filters))
    if not parts:
        return ReceiptAuditEvent.objects.none().values_list("pk")
    first, *rest = parts
    if not rest:
        return first.order_by("-a_at", "-a_ref")
    return first.union(*rest, all=True).order_by("-a_at", "a_kind", "-a_ref")


DETAIL_MODELS = {
    "product": ProductChangeAuditEvent.objects, "lifecycle": ProductLifecycleAuditEvent.objects,
    "inventory": InventoryChangeAuditEvent.objects, "invitation": StaffInvitation.objects,
    "access": InventoryAccessAuditEvent.objects.select_related("membership__user"),
}


def _changed_keys(before, after):
    before = before or {}
    return [key for key in (after or {}) if before.get(key) != after.get(key)]


def _details(row, extra):
    kind, note = row["kind"], row["note"] or ""
    if kind in ("receipt", "issue"):
        return note or "Manual"
    if kind == "adjustment":
        # The audit row holds the product's physical total before and after the count.
        text = f"Physical count {row['before']} → {row['after']}"
        return f"{text}. Reason: {note}" if note else text
    if kind == "disposal":
        return note.rstrip(": ")
    if kind == "quarantine":
        return f"Available {row['before']} → {row['after']}"
    if kind == "verification":
        action, _, rest = note.partition(" ")
        day, _, reason = rest.partition(" ")
        if action == "verified":
            return f"{day} verified at {row['after']} units"
        return f"{day} marked incomplete" + (f": {reason}" if reason.strip() else "")
    if kind == "lifecycle":
        return "Deactivated" if note == "deactivate" else "Reactivated"
    if kind == "product" and extra is not None:
        if extra.action == "create":
            return "Created"
        changed = _changed_keys(extra.before, extra.after)
        return "Changed " + ", ".join(key.replace("_", " ") for key in changed) if changed else "Edited"
    if kind == "inventory" and extra is not None:
        if extra.action == "create":
            return f"Created “{extra.after.get('name', '')}”"
        if extra.action == "rename":
            return f"Renamed “{(extra.before or {}).get('name', '')}” → “{extra.after.get('name', '')}”"
        if extra.action in ("deactivate", "reactivate"):
            return extra.get_action_display()
        changed = [key for key in _changed_keys(extra.before, extra.after) if key != "is_active"]
        return "Changed " + ", ".join(changed) if changed else extra.get_action_display()
    if kind == "access" and extra is not None:
        name = extra.membership.user.display_label
        return f"Gave {name} access" if extra.granted else f"Removed {name}’s access"
    if kind == "invitation" and extra is not None:
        return f"Invited {extra.target_email} (now {extra.get_status_display().lower()})"
    return note


def hydrate(business_id, tuples):
    """Turn union tuples into display dicts with a fixed number of bulk queries."""
    rows = [dict(zip(COLUMNS, values, strict=True)) for values in tuples]
    users = get_user_model().objects.in_bulk({row["actor_id"] for row in rows if row["actor_id"]})
    inventories = Inventory.objects.in_bulk({row["inventory_id"] for row in rows if row["inventory_id"]})
    products = Product.objects.in_bulk({row["product_id"] for row in rows if row["product_id"]})
    roles = dict(BusinessMembership.objects.filter(business_id=business_id, user_id__in=users).values_list(
        "user_id", "role"))
    extras = {}
    for kind, model in DETAIL_MODELS.items():
        refs = {row["ref"] for row in rows if row["kind"] == kind}
        if refs:
            extras[kind] = model.in_bulk(refs)
    role_labels = dict(BusinessMembership.Role.choices)
    for row in rows:
        row["label"] = KIND_LABELS[row["kind"]]
        row["at_iso"] = row["at"].isoformat(timespec="seconds")
        row["actor"] = users.get(row["actor_id"])
        row["actor_label"] = row["actor"].display_label if row["actor"] else SYSTEM_ACTOR
        row["role"] = role_labels.get(roles.get(row["actor_id"]), "System" if row["actor"] is None else "")
        row["inventory"] = inventories.get(row["inventory_id"])
        row["product"] = products.get(row["product_id"])
        row["details"] = _details(row, extras.get(row["kind"], {}).get(row["ref"]))
        row["pill"], row["tone"] = PILLS[row["kind"]]
        if row["kind"] in ("receipt", "issue") and (row["note"] or "").startswith("CSV import"):
            row["pill"], row["tone"] = "Imported", "green"
        row["day"] = row["at"].astimezone(SINGAPORE).date()
        row["magnitude"] = abs(row["change"]) if row["change"] is not None else None
    return rows


# --- View -----------------------------------------------------------------------------------------------------

from django import forms  # noqa: E402
from catalogue.pagination import paginate  # noqa: E402
from django.shortcuts import get_object_or_404, render  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.views.decorators.http import require_GET  # noqa: E402

from accounts.sessions import protected_view  # noqa: E402
from catalogue.csv_exports import csv_download  # noqa: E402
from catalogue.templatetags.tory_format import sgdate  # noqa: E402

from django.core.exceptions import PermissionDenied  # noqa: E402
from .authorization import authorized_inventories  # noqa: E402
from .selection import current_inventory, scope_chip, scope_filter  # noqa: E402

PAGE_SIZE = 50


class ActivityFilterForm(forms.Form):
    user = forms.TypedChoiceField(required=False, coerce=int, empty_value=None, label="User")
    action = forms.ChoiceField(required=False, choices=(("", "All actions"), *KINDS), label="Action")
    inventory = forms.TypedChoiceField(required=False, coerce=int, empty_value=None, label="Inventory")
    q = forms.CharField(required=False, max_length=200, label="Product name or SKU")
    start = forms.DateField(required=False, label="From", widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, label="To", widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, data, *, business_id, inventory_ids=None):
        """inventory_ids limits the choices to a Staff member's assigned inventories (TORY-67)."""
        super().__init__(data)
        members = get_user_model().objects.filter(business_memberships__business_id=business_id)
        inventories = Inventory.objects.filter(business_id=business_id)
        if inventory_ids is not None:
            # Only people who work in the same inventories, and only the movement kinds.
            members = members.filter(business_memberships__inventory_assignments__inventory_id__in=inventory_ids,
                                     business_memberships__inventory_assignments__is_active=True)
            inventories = inventories.filter(pk__in=inventory_ids)
            self.fields["action"].choices = [("", "All stock movements"),
                                             *((kind, KIND_LABELS[kind]) for kind in STAFF_KINDS)]
        members = members.distinct().order_by("email")
        self.fields["user"].choices = [("", "Everyone"), *((user.pk, user.display_label) for user in members)]
        self.fields["inventory"].choices = [("", "All inventories"), *inventories.order_by("name", "pk")
                                            .values_list("pk", "name")]
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-select" if isinstance(field, forms.ChoiceField)
                                          else "form-control")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start") and cleaned.get("end") and cleaned["start"] > cleaned["end"]:
            self.add_error("end", "The end date must be on or after the start date.")
        return cleaned

    def query(self):
        data = self.cleaned_data
        return {"actor_id": data["user"], "kinds": {data["action"]} if data["action"] else (),
                "inventory_id": data["inventory"], "product_query": data["q"].strip(),
                "start": data["start"], "end": data["end"]}


def _membership(request, business_id):
    """Managers and (TORY-67) Staff of the business; anyone else gets a 404."""
    return get_object_or_404(
        BusinessMembership.objects.filter(user=request.user, is_active=True).select_related("business"),
        business_id=business_id,
    )


def _csv_rows(business_id, rows):
    for start in range(0, len(rows), 500):
        for row in hydrate(business_id, rows[start:start + 500]):
            yield (
                sgdate(row["at"]), row["actor_label"], row["actor"].email if row["actor"] else "", row["role"],
                row["label"], row["inventory"].name if row["inventory"] else "",
                row["product"].sku if row["product"] else "", row["product"].name if row["product"] else "",
                row["change"] if row["change"] is not None else "", row["details"],
            )


@protected_view
@require_GET
def activity_log(request, business_id, export=False):
    membership = _membership(request, business_id)
    business = membership.business
    staff = membership.role == BusinessMembership.Role.STAFF
    if staff and export:
        raise PermissionDenied("The activity CSV is for Managers.")
    assigned = list(authorized_inventories(request.user).filter(business_id=business.pk))
    staff_scope = {"inventory_ids": [inventory.pk for inventory in assigned]} if staff else {}
    # TORY-63: default to the inventory selected in the sidebar when it belongs to
    # this business; ?scope=all (or choosing "All inventories") shows the business.
    current = current_inventory(request, assigned)
    shown, defaulted = scope_filter(request, current)
    data = request.GET.copy()
    if defaulted:
        data["inventory"] = shown
    form = ActivityFilterForm(data, business_id=business.pk, **staff_scope)
    if not form.is_valid():
        return render(request, "inventory_access/activity_log.html", {
            "business": business, "form": form, "rows": [], "page": None, "is_staff_view": staff,
        }, status=400)
    query = form.query()
    if staff:
        query["kinds"] = set(query["kinds"]) & set(STAFF_KINDS) if query["kinds"] else set(STAFF_KINDS)
        query.update(staff_scope)
    rows = activity_rows(business.pk, **query)
    if export:
        stamp = timezone.now().astimezone(SINGAPORE).strftime("%Y%m%d-%H%M")
        return csv_download(f"tory-activity-{stamp}.csv", (
            "Time (Asia/Singapore)", "User", "Email", "Role", "Action", "Inventory", "SKU", "Product",
            "Quantity change", "Details",
        ), _csv_rows(business.pk, list(rows)))
    page = paginate(request, rows, default=PAGE_SIZE)
    all_count = activity_rows(business.pk, **{**query, "inventory_id": None}).count() if current else 0
    return render(request, "inventory_access/activity_log.html", {
        "scope": scope_chip(request, current, shown_id=str(form.cleaned_data["inventory"] or "") or None,
                            all_count=all_count, noun="activity"),
        "breadcrumbs": [("Dashboard", reverse("home")), (business.name, None), ("Activity log", None)],
        "business": business, "form": form, "page": page, "rows": hydrate(business.pk, list(page.object_list)),
        "is_filtered": any(request.GET.get(name) for name in form.fields), "is_staff_view": staff,
    })
