from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from .forms import LoginForm
from .sessions import protected_view, start_session
from .throttle import check_and_authenticate


GENERIC_ERROR = "Sign-in was unsuccessful. Please check your details and try again."


def _safe_next(request):
    """Allow local post-login destinations without creating an open redirect."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("home")


@sensitive_post_parameters("password")
@require_http_methods(["GET", "POST"])
def login_view(request):
    """Keep invalid and throttled responses generic to avoid account enumeration.

    Global CsrfViewMiddleware checks POST before this view creates a session.
    """
    target = _safe_next(request)
    if request.method == "GET":
        return render(request, "accounts/login.html", {"next": target})

    form = LoginForm(request.POST)
    valid = form.is_valid()
    email = form.cleaned_data["email"] if valid else request.POST.get("email", "")
    password = form.cleaned_data["password"] if valid else request.POST.get("password", "")
    user, throttled = check_and_authenticate(
        email,
        password,
        request.META.get("REMOTE_ADDR", ""),
        lambda supplied_email, supplied_password: authenticate(
            request, username=supplied_email, password=supplied_password
        ) if valid else None,
    )
    if user is None or throttled:
        return render(
            request, "accounts/login.html", {"next": target, "error": GENERIC_ERROR},
            status=200,
        )

    login(request, user)
    start_session(request)
    return redirect(target)


@protected_view
def home(request):
    return render(request, "accounts/home.html")


@require_POST
def logout_view(request):
    """POST plus CsrfViewMiddleware prevents a link or tokenless POST ending a session."""
    logout(request)
    return redirect("login")
