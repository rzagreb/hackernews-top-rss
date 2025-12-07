from __future__ import annotations

import email.utils as email_utils
from datetime import datetime, timezone
from typing import Optional, TypeVar

from dateutil import parser as date_parser

T = TypeVar("T")


def ensure_utc(dt: datetime) -> datetime:
    """
    Return a timezone aware datetime in UTC.

    The RSS specification recommends RFC 2822 dates in GMT.
    To keep things predictable we always normalise to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_rfc2822(dt: datetime) -> str:
    """
    Format a datetime in RFC 2822 format for RSS pubDate / lastBuildDate.

    Example: Tue, 03 Jun 2003 09:39:21 GMT
    """
    dt_utc = ensure_utc(dt)
    # email.utils.format_datetime knows how to format in RFC 2822
    return email_utils.format_datetime(dt_utc)


def arr_get(items: list[T], index: int = 0, default: Optional[T] = None) -> Optional[T]:
    """
    Helper to safely get an item from a list-like object by index.

    This is used in the scraper where some XPath expressions may return
    shorter lists than expected.
    """
    if items is None:
        return default
    try:
        seq = list(items)
        return seq[index]
    except (IndexError, TypeError):
        return default


def parse_human_date(date_str: str) -> datetime | None:
    """
    Parse a human readable date string into a datetime object.

    The implementation is intentionally forgiving and will return None
    when parsing fails instead of raising an exception.

    Examples:
        "2024-01-10 12:34"
        "10 Jan 2024"
        "3 hours ago"
    """
    if not date_str:
        return None
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        return dt
    except (ValueError, TypeError, OverflowError):
        return None
