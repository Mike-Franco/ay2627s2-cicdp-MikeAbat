from django import forms
from django.contrib.auth.forms import PasswordChangeForm

from config.media import ImageUploadField
from config.palette import TONE_CHOICES

from .models import User
from .password_feedback import REASONS


class LoginForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password = forms.CharField(widget=forms.PasswordInput)


class AccountPasswordChangeForm(PasswordChangeForm):
    """Django's password change form with Tory's labels and validator messages."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        for name, label in (("old_password", "Current password"), ("new_password1", "New password"),
                            ("new_password2", "Confirm new password")):
            self.fields[name].label = label
            self.fields[name].widget.attrs["class"] = "form-control"
        self.fields["new_password1"].help_text = ""

    def _post_clean(self):
        # SetPasswordForm runs the configured AUTH_PASSWORD_VALIDATORS here;
        # show the same plain messages as the invitation and reset pages.
        super()._post_clean()
        errors = self.errors.as_data().get("new_password2")
        if errors:
            self._errors["new_password2"] = self.error_class(list(dict.fromkeys(
                REASONS.get(error.code, " ".join(error.messages)) for error in errors)))


class ProfileForm(forms.ModelForm):
    """The signed-in user's own profile (TORY-55). Email and role are not editable here."""

    photo_upload = ImageUploadField(label="Photo")
    remove_photo = forms.BooleanField(label="Remove current photo", required=False)

    class Meta:
        model = User
        fields = ("display_name", "job_title", "phone", "avatar_colour")
        labels = {"display_name": "Display name", "avatar_colour": "Avatar colour"}
        help_texts = {
            "display_name": "Shown instead of your email across Tory. Up to 60 characters.",
            "job_title": "Optional, for example Pharmacist or Store supervisor.",
            "phone": "Optional. Digits, spaces, brackets and dashes; a leading + for international numbers.",
        }
        widgets = {"avatar_colour": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        for name in ("display_name", "job_title", "phone"):
            self.fields[name].widget.attrs.update({"class": "form-control", "maxlength": self.fields[name].max_length})
        self.fields["phone"].widget.input_type = "tel"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"
        self.fields["display_name"].widget.attrs["autocomplete"] = "nickname"
        self.fields["job_title"].widget.attrs["autocomplete"] = "organization-title"
        self.fields["photo_upload"].widget.attrs["class"] = "form-control"
        self.fields["avatar_colour"].choices = list(TONE_CHOICES)

    def clean(self):
        cleaned = super().clean()
        for name in ("display_name", "job_title", "phone"):
            if isinstance(cleaned.get(name), str):
                cleaned[name] = " ".join(cleaned[name].split())
        if cleaned.get("photo_upload") and cleaned.get("remove_photo"):
            self.add_error("remove_photo", "Choose a new photo or remove the current one, not both.")
        return cleaned
