"""Shared display formatting for templates."""

from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django import template
from django.utils import dateformat, timezone
from django.utils.dateparse import parse_date, parse_datetime

register = template.Library()
SINGAPORE = ZoneInfo("Asia/Singapore")


@register.filter
def sgdate(value):
    """Format a date as "20 Nov 2026" and a datetime as "20 Nov 2026, 12:00" in Asia/Singapore.

    ISO strings are parsed first. None and empty values render as an empty string.
    """
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        parsed = parse_datetime(value) if "T" in value or " " in value else parse_date(value)
        if parsed is None:
            return value
        value = parsed
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = value.astimezone(SINGAPORE)
        return dateformat.format(value, "j M Y, H:i")
    if isinstance(value, date):
        return dateformat.format(value, "j M Y")
    return value


@register.filter
def sgd(value):
    """Format a price as "S$1,234.50"; empty values render as an em dash."""
    if value in (None, ""):
        return "—"
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"S${amount:,.2f}"


def whole_units(value):
    """Round a unit quantity up to a whole number of units (None stays None).

    Reorder points can be fractional (average demand × lead time + safety
    stock). Rounding up matches the suggested order, which is the reorder
    point minus available units, rounded up.
    """
    if value in (None, ""):
        return None
    try:
        return int(Decimal(str(value)).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, TypeError, ValueError):
        return None


def one_decimal(value):
    """Round days of supply (or another ratio) to one decimal place, as a string."""
    if value in (None, ""):
        return None
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def units(value):
    """Show a unit quantity as a whole number, rounded up; empty values render as an em dash."""
    result = whole_units(value)
    return "—" if result is None else result


@register.filter
def days(value):
    """Show days of supply with one decimal place; empty values render as an em dash."""
    result = one_decimal(value)
    return "—" if result is None else result


@register.filter
def day_list(values):
    """Join dates as "Sat 21 Nov and Sun 22 Nov" (or "Fri 20 Nov, Sat 21 Nov and Sun 22 Nov")."""
    labels = [dateformat.format(value, "D j M") for value in values]
    if len(labels) < 2:
        return "".join(labels)
    return ", ".join(labels[:-1]) + " and " + labels[-1]


@register.filter
def sgweekday(value):
    """Format a date as "Thu 26 Nov" (weekday and day, for near-future dates such as a run-out day)."""
    if not value:
        return ""
    if isinstance(value, datetime):
        value = timezone.localtime(value, SINGAPORE).date()
    return dateformat.format(value, "D j M")


def _singapore(value, now):
    return value.astimezone(SINGAPORE), (now or timezone.now()).astimezone(SINGAPORE)


@register.filter
def sgrelative(value, now=None):
    """A short relative time for activity rows (TORY-67): "just now", "25 min ago", "2 h ago",
    "Yesterday 18:40", "Fri 14:30", then "20 Oct 2026". Pair it with sgdate in a title for the exact time."""
    if not isinstance(value, datetime):
        return sgdate(value)
    local, current = _singapore(value, now)
    seconds = (current - local).total_seconds()
    if 0 <= seconds < 60:
        return "just now"
    if 0 <= seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    days = (current.date() - local.date()).days
    if days == 0 and seconds >= 0:
        return f"{int(seconds // 3600)} h ago"
    if days == 1:
        return f"Yesterday {local:%H:%M}"
    if 1 < days < 7:
        return f"{local:%a %H:%M}"
    return sgdate(value)


@register.filter
def sgdayheading(value, now=None):
    """Day separator text: "Today · Mon 23 Nov", "Yesterday · Sun 22 Nov", otherwise "Fri 20 Nov"."""
    if not value:
        return ""
    today = (now or timezone.now()).astimezone(SINGAPORE).date()
    label = dateformat.format(value, "D j M")
    if value == today:
        return f"Today · {label}"
    if value == today - timedelta(days=1):
        return f"Yesterday · {label}"
    return label
