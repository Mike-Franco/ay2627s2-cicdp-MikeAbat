"""Shared display formatting for templates."""

from datetime import date, datetime
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
