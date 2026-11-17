"""Public password reset request and password confirmation pages."""

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .password_resets import ACKNOWLEDGEMENT, PasswordResetError, redeem_password_reset
from .reset_dispatch import enqueue_reset


def _private_response(response, *, referrer_policy="no-referrer"):
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = referrer_policy
    return response


@never_cache
@sensitive_post_parameters("email")
@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    if request.method == "POST":
        try:
            enqueue_reset(request.POST.get("email", ""), request.META.get("REMOTE_ADDR", ""))
        except Exception:
            pass
        return _private_response(render(request, "accounts/reset_request.html", {
            "acknowledgement": ACKNOWLEDGEMENT,
        }), referrer_policy="same-origin")
    return _private_response(render(request, "accounts/reset_request.html"), referrer_policy="same-origin")


@never_cache
@sensitive_post_parameters("token", "password", "password_confirm")
@require_http_methods(["GET", "POST"])
def password_reset_setup(request):
    if request.method == "GET":
        return _private_response(render(request, "accounts/reset_setup.html"))
    password = request.POST.get("password", "")
    if not password or password != request.POST.get("password_confirm", ""):
        result = {"ok": False, "error": "Passwords must match and meet the password requirements."}
    else:
        try:
            redeem_password_reset(request.POST.get("token", ""), password)
            result = {"ok": True, "sign_in_url": reverse("login")}
        except PasswordResetError:
            result = {"ok": False, "error": "This link cannot be used, or the password does not meet the requirements."}
    return _private_response(JsonResponse(result))
