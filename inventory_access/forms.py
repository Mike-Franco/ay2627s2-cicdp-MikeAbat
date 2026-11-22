from django import forms


class InventoryNameForm(forms.Form):
    name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": "form-control"}))


class InventoryStatusForm(forms.Form):
    is_active = forms.TypedChoiceField(
        choices=(("true", "Active"), ("false", "Inactive")), coerce=lambda value: value == "true",
    )
