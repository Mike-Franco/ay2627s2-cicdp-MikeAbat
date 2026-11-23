"""Public landing page and signed-in Help page (TORY-60)."""

from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from .sessions import protected_view

REPOSITORY_URL = "https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat"


@require_GET
def landing(request):
    """Signed-in users go straight to their dashboard; everyone else sees what Tory is."""
    if request.user.is_authenticated and request.user.is_active:
        return redirect("home")
    return render(request, "accounts/landing.html", {"public_auth_page": True, "repository_url": REPOSITORY_URL})


@protected_view
@require_GET
def help_page(request):
    return render(request, "accounts/help.html", {"sections": HELP_SECTIONS})


# Table of contents for templates/accounts/help.html; every anchor must exist there.
HELP_SECTIONS = (
    ("getting-started", "Getting started"),
    ("inventories", "Inventories"),
    ("products", "Products and categories"),
    ("receiving", "Receiving stock"),
    ("issuing", "Issuing stock (FEFO and FIFO)"),
    ("adjustments", "Count adjustments and disposal"),
    ("expiry", "Expiry and quarantine"),
    ("verifying-demand", "Verifying demand"),
    ("forecasts", "Forecasts and reorder suggestions"),
    ("metrics", "Insights and dashboard metrics"),
    ("csv", "CSV import and export"),
    ("staff", "Staff and roles"),
    ("activity", "Activity log"),
    ("profile", "Profile and password"),
)
