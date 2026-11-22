"""Shared display formatting for templates."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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
