from datetime import timedelta

from django import forms
from django.db.models import Value
from django.db.models.functions import Lower, Trim

from inventory_access.models import Inventory

from .models import Product


PRODUCT_FIELDS = ("name", "sku", "base_unit_label", "expiry_tracking_required",
                  "lead_time_days", "safety_stock_units")
DUPLICATE_SKU = "A product with this SKU already exists in this business."


class PlainLabelsMixin:
    """Render labels without Django's default trailing colon."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class ProductForm(PlainLabelsMixin, forms.ModelForm):
    base_unit_label = forms.CharField(
        max_length=40, label="Base unit",
        help_text="The single item you count, receive and issue, such as bottle, box or bag. "
                  "Quantities are always whole numbers of this unit.",
    )
    expiry_tracking_required = forms.TypedChoiceField(
        label="Expiry policy",
        choices=(("", "Choose a policy"), ("yes", "Track expiry dates"), ("no", "No expiry dates")),
        coerce=lambda value: value == "yes",
        help_text="Track expiry dates: every receipt needs an expiry date, and expired stock is "
                  "quarantined automatically. No expiry dates: an expiry date is optional.",
    )

    class Meta:
        model = Product
        fields = PRODUCT_FIELDS
        widgets = {"name": forms.TextInput()}
        labels = {"name": "Product name", "sku": "SKU", "lead_time_days": "Lead time (days)",
                  "safety_stock_units": "Safety stock (units)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["sku"].disabled = True
            self.fields["sku"].help_text = "SKU is permanent after creation."
            if self.instance.expiry_tracking_required is not None:
                self.initial["expiry_tracking_required"] = "yes" if self.instance.expiry_tracking_required else "no"
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"

    def clean_sku(self):
        sku = self.cleaned_data["sku"]
        products = Product.objects.filter(business_id=self.instance.business_id).annotate(
            normalized_sku=Lower(Trim("sku")),
        ).filter(normalized_sku=Lower(Value(sku))).exclude(pk=self.instance.pk)
        if products.exists():
            raise forms.ValidationError(DUPLICATE_SKU, code="duplicate")
        return sku


class ProductCreateForm(ProductForm):
    inventories = forms.ModelMultipleChoiceField(
        queryset=Inventory.objects.none(),
        help_text="Choose one or more assigned inventories in this business.",
    )

    def __init__(self, *args, inventories, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["inventories"].queryset = inventories


class ProductSearchForm(PlainLabelsMixin, forms.Form):
    q = forms.CharField(
        label="Search products", required=False, max_length=200,
        widget=forms.TextInput(attrs={
            "type": "search", "class": "form-control",
            "placeholder": "Product name or SKU",
        }),
    )


class InventoryProductFilterForm(ProductSearchForm):
    reorder = forms.ChoiceField(
        label="Reorder status", required=False,
        choices=(
            ("", "All reorder statuses"),
            ("attention", "At or below reorder point"),
            ("above", "Above reorder point"),
            ("unavailable", "Reorder point unavailable"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sort = forms.ChoiceField(
        label="Sort by", required=False,
        choices=(
            ("", "SKU"),
            ("name", "Name (A–Z)"),
            ("-name", "Name (Z–A)"),
            ("available", "Available (lowest first)"),
            ("-available", "Available (highest first)"),
            ("status", "Reorder status (needs attention first)"),
            ("-status", "Reorder status (unavailable first)"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class ReorderSettingsForm(PlainLabelsMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ("lead_time_days", "safety_stock_units")
        labels = {"lead_time_days": "Lead time (days)", "safety_stock_units": "Safety stock (units)"}
        widgets = {
            "lead_time_days": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 365}),
            "safety_stock_units": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 2147483647}),
        }


class BulkDemandVerifyForm(PlainLabelsMixin, forms.Form):
    SCOPE_DAY = "day"
    SCOPE_WEEK = "week"
    scope = forms.ChoiceField(
        choices=(
            (SCOPE_DAY, "Only this date"),
            (SCOPE_WEEK, "Every unreviewed date in the last 7 days"),
        ),
        initial=SCOPE_DAY,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    day = forms.DateField(
        required=False,
        label="Singapore date",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, today, **kwargs):
        super().__init__(*args, **kwargs)
        yesterday = today - timedelta(days=1)
        self.today = today
        self.fields["day"].initial = yesterday
        self.fields["day"].widget.attrs["max"] = yesterday.isoformat()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("scope") == self.SCOPE_DAY:
            day = cleaned.get("day")
            if day is None:
                self.add_error("day", "Choose a date.")
            elif day >= self.today:
                self.add_error("day", "Choose a complete Singapore date before today.")
        return cleaned


class SellingPriceForm(PlainLabelsMixin, forms.Form):
    selling_price = forms.DecimalField(
        label="Selling price (SGD)", required=False, min_value=0, max_digits=12, decimal_places=2,
        help_text="Price per base unit in this inventory. Leave blank if the product is not sold here.",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01", "inputmode": "decimal"}),
    )
