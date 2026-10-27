"""Policy numbers are validated once at intake; the helper relies on that. Nothing to report."""
from __future__ import annotations


def intake_policy(raw: dict) -> str | None:
    value = raw.get("policy_number")
    if not isinstance(value, str) or not value.strip():
        return None
    return normalise_policy(value) or None  # a placeholder such as "---" normalises to nothing


def normalise_policy(policy_number: str) -> str:
    # Caller (intake_policy) guarantees a str.
    return "".join(ch for ch in policy_number if ch.isalnum()).upper()
