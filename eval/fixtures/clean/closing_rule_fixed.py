"""Just-closed rule with signed arithmetic and an explicit unknown (fix for F-03)."""
from __future__ import annotations

from datetime import date, datetime

DATE_FORMAT = "%m/%d/%Y"


def parse_date(text: str | None) -> date | None:
    try:
        return datetime.strptime((text or "").strip(), DATE_FORMAT).date()
    except ValueError:
        return None


def payment_blocked_by_closing(closing_date: str | None, effective_date: str | None) -> bool | None:
    """True when the policy starts 0-59 days after closing; None when either date is unusable."""
    closing, effective = parse_date(closing_date), parse_date(effective_date)
    if closing is None or effective is None:
        return None
    return 0 <= (effective - closing).days < 60
