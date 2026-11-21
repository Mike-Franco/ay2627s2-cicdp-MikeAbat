from django import forms
from django.db.models import Value
from django.db.models.functions import Lower, Trim

from inventory_access.models import Inventory

from .models import Product


PRODUCT_FIELDS = ("name", "sku", "base_unit_label", "expiry_tracking_required",
                  "lead_time_days", "safety_stock_units")
DUPLICATE_SKU = "A product with this SKU already exists in this business."


class ProductForm(forms.ModelForm):
    base_unit_label = forms.CharField(max_length=40)
    expiry_tracking_required = forms.TypedChoiceField(
        choices=(("", "Choose a policy"), ("yes", "Yes"), ("no", "No")),
        coerce=lambda value: value == "yes",
    )

    class Meta:
        model = Product
        fields = PRODUCT_FIELDS
        widgets = {"name": forms.TextInput()}

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


class InventoryProductFilterForm(forms.Form):
    q = forms.CharField(
        label="Search products", required=False, max_length=200,
        widget=forms.TextInput(attrs={
            "type": "search", "class": "form-control",
            "placeholder": "Product name or SKU",
        }),
    )
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


class ReorderSettingsForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("lead_time_days", "safety_stock_units")
        widgets = {
            "lead_time_days": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 365}),
            "safety_stock_units": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 2147483647}),
        }
