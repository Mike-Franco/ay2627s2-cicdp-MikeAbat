"""One pagination component for every table (TORY-62).

``paginate`` reads ``?page=`` and ``?per_page=`` (or ``<prefix>page`` /
``<prefix>per_page`` when one page has several tables), clamps the page size to
the allowed set, and attaches what ``includes/pagination.html`` needs: the
"Showing 26–50 of 142" range, the rows-per-page choices, and URLs for
‹ 1 2 3 … › that keep every other query parameter.
"""

from django.core.paginator import Paginator

PER_PAGE_CHOICES = (10, 25, 50, 100)
SMALL_PER_PAGE_CHOICES = (5, *PER_PAGE_CHOICES)


def clamp_per_page(value, *, default, choices=PER_PAGE_CHOICES):
    """Return the largest allowed size not above ``value``; junk falls back to ``default``."""
    try:
        wanted = int(value)
    except (TypeError, ValueError):
        return default
    allowed = [size for size in sorted(choices) if size <= wanted]
    return allowed[-1] if allowed else min(choices)


def _url(request, **changes):
    query = request.GET.copy()
    for key, value in changes.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else request.path


def paginate(request, rows, *, default=25, prefix="", choices=PER_PAGE_CHOICES, fragment=""):
    if default not in choices:
        raise ValueError(f"default page size {default} is not one of {choices}")
    page_param, size_param = f"{prefix}page", f"{prefix}per_page"
    per_page = clamp_per_page(request.GET.get(size_param, default), default=default, choices=choices)
    page = Paginator(rows, per_page).get_page(request.GET.get(page_param))
    size_value = None if per_page == default else str(per_page)
    anchor = f"#{fragment}" if fragment else ""

    def page_url(number):
        return _url(request, **{page_param: str(number), size_param: size_value}) + anchor

    page.page_param, page.per_page_param, page.per_page = page_param, size_param, per_page
    page.per_page_choices = choices
    page.fragment = fragment
    page.touched = page_param in request.GET or size_param in request.GET
    page.links = [
        {"number": number, "url": page_url(number), "current": number == page.number}
        if number != Paginator.ELLIPSIS else {"ellipsis": True}
        for number in page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    ]
    page.previous_url = page_url(page.previous_page_number()) if page.has_previous() else None
    page.next_url = page_url(page.next_page_number()) if page.has_next() else None
    # Hidden fields for the rows-per-page form: everything except this table's page and size.
    page.keep = [(key, value) for key, values in request.GET.lists()
                 if key not in (page_param, size_param) for value in values]
    return page
