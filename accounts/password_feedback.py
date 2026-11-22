"""Controlled public feedback, called only after locked redemption checks."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

UNSET = object()
FALLBACK = "Password does not meet the configured requirements. Choose another password."
REASONS = {
    "password_too_short": "Use at least 15 characters.",
    "password_too_common": "Choose a less common password.",
    "password_too_similar": "Choose a password less similar to your account details.",
}
REQUIREMENTS = ["Use at least 15 characters.", "Avoid commonly used passwords.",
                "Avoid passwords similar to your account details."]

class PasswordFeedbackError(Exception):
    def __init__(self, errors):
        super().__init__("Password fields need correction.")
        self.errors = errors

def validate_new_password(password, user, confirmation, error_class):
    errors = {}
    if not isinstance(password, str) or not password:
        errors["password"] = ["Enter a new password."]
    else:
        try:
            validate_password(password, user)
        except ValidationError as error:
            errors["password"] = list(dict.fromkeys(
                REASONS.get(item.code, FALLBACK) for item in error.error_list))
    if confirmation is not UNSET:
        if not confirmation:
            errors["password_confirm"] = ["Confirm your new password."]
        elif password != confirmation:
            errors["password_confirm"] = ["Passwords do not match."]
    if errors:
        raise error_class(errors)
