import uuid

from django import forms
from django.forms import formset_factory

from .models import MAX_RECEIPT_UNITS, StockDisposal


class StockCsvImportForm(forms.Form):
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv,text/csv"}))


class DemandCoverageActionForm(forms.Form):
    day = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    action = forms.ChoiceField(choices=(("verify", "Verify"), ("incomplete", "Mark incomplete")))
    reason = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))


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


class ManualStockOutForm(forms.Form):
    quantity_units = forms.IntegerField(
        min_value=1, max_value=MAX_RECEIPT_UNITS,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
    )


class BatchCountForm(forms.Form):
    batch_id = forms.UUIDField(widget=forms.HiddenInput)
    counted_quantity_units = forms.IntegerField(
        required=False, min_value=0, max_value=MAX_RECEIPT_UNITS,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
    )
    confirmed = forms.BooleanField(required=False)

    def clean(self):
        cleaned = super().clean()
        count = cleaned.get("counted_quantity_units")
        confirmed = cleaned.get("confirmed")
        if count is not None and not confirmed:
            self.add_error("confirmed", "Confirm that this is the batch you physically counted.")
        if confirmed and count is None:
            self.add_error("counted_quantity_units", "Enter the observed whole-unit count.")
        return cleaned


BatchCountFormSet = formset_factory(BatchCountForm, extra=0, max_num=500, validate_max=True)


class ManualStockAdjustmentForm(forms.Form):
    reason = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )


class ManualStockDisposalForm(forms.Form):
    batch_id = forms.ChoiceField(widget=forms.Select(attrs={"class": "form-select"}))
    quantity_units = forms.IntegerField(
        min_value=1, max_value=MAX_RECEIPT_UNITS,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
    )
    reason_code = forms.ChoiceField(
        choices=StockDisposal.ReasonCode.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason_note = forms.CharField(
        required=False, max_length=2000, strip=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, batches, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch_id"].choices = [
            (str(batch.pk), f"Batch {batch.receipt_sequence} · expires {batch.expiry_date} · {batch.remaining_quantity_units} units")
            for batch in batches
        ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("reason_code") == StockDisposal.ReasonCode.OTHER and not cleaned.get("reason_note"):
            self.add_error("reason_note", "Enter a note for Other.")
        return cleaned
