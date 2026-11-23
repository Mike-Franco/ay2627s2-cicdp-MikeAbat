"""The current inventory: the one picked in the sidebar switcher (TORY-63).

Opening any page of an inventory (its products, insights, a product, …)
selects it, and the choice is kept in the session so pages without an
inventory in their URL — Catalogue, Activity log, the dashboard — default to
it. The stored id is only a preference: it is re-checked against the user's
authorised inventories on every request, so a revoked assignment or a
deactivated inventory simply stops being selected.
"""

SESSION_KEY = "tory_inventory_id"


def url_inventory_id(request):
    inventory_id = getattr(request, "tory_inventory_id", None)
    if inventory_id is None and request.resolver_match:
        inventory_id = (request.resolver_match.kwargs or {}).get("inventory_id")
    return inventory_id


def current_inventory(request, inventories):
    """Return the selected inventory from ``inventories`` (already authorised), remembering URL choices."""
    by_id = {inventory.pk: inventory for inventory in inventories}
    session = getattr(request, "session", None)  # error handlers may render without one
    from_url = url_inventory_id(request)
    if from_url in by_id:
        if session is not None and session.get(SESSION_KEY) != from_url:
            session[SESSION_KEY] = from_url
        return by_id[from_url]
    return by_id.get(session.get(SESSION_KEY)) if session is not None else None


def scope_filter(request, current, *, param="inventory"):
    """Which inventory a Manage list shows: an explicit ?inventory= wins, then ?scope=all, then the current one.

    Returns (inventory id or None for "all", whether that id is the defaulted current inventory).
    """
    if param in request.GET:
        return request.GET.get(param) or None, False
    if request.GET.get("scope") == "all" or current is None:
        return None, False
    return str(current.pk), True


def scope_chip(request, current, *, shown_id, all_count, noun, param="inventory"):
    """Context for includes/scope_chip.html, or None when there is no current inventory to talk about."""
    if current is None:
        return None
    widen = request.GET.copy()
    for key in (param, "page", "scope"):
        widen.pop(key, None)
    widen["scope"] = "all"
    narrow = request.GET.copy()
    for key in (param, "page", "scope"):
        narrow.pop(key, None)
    narrow_query = narrow.urlencode()
    return {
        "inventory": current, "noun": noun, "all_count": all_count,
        "showing_current": shown_id == str(current.pk), "showing_all": shown_id is None,
        "all_url": "?" + widen.urlencode(),
        "current_url": "?" + narrow_query if narrow_query else request.path,
    }
