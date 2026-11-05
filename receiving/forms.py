import uuid

from django import forms

from .models import MAX_RECEIPT_UNITS


class ManualReceiptForm(forms.Form):
    request_token = forms.UUIDField(widget=forms.HiddenInput)
    quantity_units = forms.IntegerField(
        min_value=1,
        max_value=MAX_RECEIPT_UNITS,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, expiry_required=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expiry_date"].required = expiry_required

    @classmethod
    def new_form(cls, **kwargs):
        return cls(initial={"request_token": uuid.uuid4()}, **kwargs)
