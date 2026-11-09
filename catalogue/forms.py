from django import forms

from .models import Product


class ReorderSettingsForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("lead_time_days", "safety_stock_units")
        widgets = {
            "lead_time_days": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 365}),
            "safety_stock_units": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 2147483647}),
        }
