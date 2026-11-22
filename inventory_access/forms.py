from django import forms

from config.media import ImageUploadField
from config.palette import DEFAULT_TONE, TONE_CHOICES

from .icons import DEFAULT_ICON, ICONS


class InventoryNameForm(forms.Form):
    name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": "form-control"}))


class InventoryForm(InventoryNameForm):
    """Create or edit an inventory: name plus icon, colour and optional picture (TORY-54)."""

    # Optional so a name-only submission keeps the current look (or the defaults).
    icon = forms.ChoiceField(choices=ICONS, initial=DEFAULT_ICON, widget=forms.RadioSelect, required=False)
    colour = forms.ChoiceField(choices=TONE_CHOICES, initial=DEFAULT_TONE, widget=forms.RadioSelect, required=False)
    picture_upload = ImageUploadField(
        label="Picture",
        help_text="Optional. Shown instead of the icon. JPEG, PNG or WebP, up to 2 MB; resized to 512 px.",
    )
    remove_picture = forms.BooleanField(label="Remove current picture", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Inventory name"
        self.fields["picture_upload"].widget.attrs.update({"class": "form-control", "data-picture-input": ""})

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("picture_upload") and cleaned.get("remove_picture"):
            self.add_error("remove_picture", "Choose a new picture or remove the current one, not both.")
        return cleaned


class InventoryStatusForm(forms.Form):
    is_active = forms.TypedChoiceField(
        choices=(("true", "Active"), ("false", "Inactive")), coerce=lambda value: value == "true",
    )
