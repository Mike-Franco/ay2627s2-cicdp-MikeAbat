"""Unauthenticated health probe for containers and load balancers."""

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@never_cache
@require_safe
def healthz(request):
    """Return 200 when the database answers a trivial query, otherwise 503."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
