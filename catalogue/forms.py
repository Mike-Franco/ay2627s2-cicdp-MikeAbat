from django import forms

from .models import Product


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
