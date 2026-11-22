from django import forms
from django.contrib.auth.forms import PasswordChangeForm

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
