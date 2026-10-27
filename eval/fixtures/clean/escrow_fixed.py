"""Escrow handling where unknown is its own state (fix for F-02)."""
from __future__ import annotations

_YES = {"y", "yes", "true"}
_NO = {"n", "no", "false"}


def is_escrow(value: str | None) -> bool | None:
    """True/False for a recognised value, None when blank or unrecognised."""
    text = (value or "").strip().casefold()
    if text in _YES:
        return True
    if text in _NO:
        return False
    return None


def payment_decision(escrow_status: str | None, days_to_effective: int) -> str:
    escrow = is_escrow(escrow_status)
    if escrow is None:
        return "needs_human"
    if escrow and 60 <= days_to_effective <= 120:
        return "prepare_payment"
    return "no_payment"
