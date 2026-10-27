"""Entry validation that routes bad input to a person instead of raising (fix for F-06)."""
from __future__ import annotations

from dataclasses import dataclass

REQUIRED = ("property_address", "effective_date", "expiration_date")


@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str = ""


def intake(doc: dict) -> Outcome:
    missing = [name for name in REQUIRED if not str(doc.get(name) or "").strip()]
    if missing:
        return Outcome("edit", "Cannot ID: missing " + ", ".join(missing))
    return Outcome("proceed")
