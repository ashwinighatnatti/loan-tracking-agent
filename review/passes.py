"""Focused review passes. Each is a separate model call with its own emphasis; their findings are merged.

Reviewers disagree on which bugs they find (REVIEW.md research notes), so several narrow, adversarial
passes find more than one broad one. `general` is the original single broad pass, kept for ablation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pass:
    name: str
    focus: str  # empty means no extra section in the prompt


ADVERSARIAL = (
    "Assume the code under review is wrong in a way that matters to your focus, and try to demonstrate it: "
    "trace concrete inputs through the code and state the wrong result. Other reviewers cover the other "
    "focus areas, so report a problem outside your focus only when it is critical. If you cannot "
    "demonstrate a defect, report none; do not pad the list."
)

GENERAL = Pass("general", "")
CORRECTNESS = Pass("correctness", (
    "Money and decisions. Look hardest for BT-01, BT-02, BT-03, BT-04, BT-06, BT-07 and BT-08: wrong or "
    "string-typed comparisons of escrow, premium or coverage; defaults standing in for unknown; literals "
    "in decision logic; date and term arithmetic (signed vs absolute, boundaries, today()); branches and "
    "scenario combinations nobody handles; fuzzy or substring matching that links a document to the wrong "
    "loan; wording not mapped to the closed vocabularies; fields silently dropped or defaulted."))
SAFETY = Pass("safety", (
    "Failure handling and agent safety. Look hardest for BT-05, BT-09, BT-11 and BT-12, and invariants 2, "
    "5 and 8: malformed input that has no get-out path; the trust boundary between document text and the "
    "LLM (prompt injection, model-built arguments, tools that write); missing human gates for payments and "
    "low confidence; network exposure of data; run tracking and where outputs are written; borrower data "
    "in logs and fixtures."))
ROBUSTNESS = Pass("robustness", (
    "Screens, environment and tests. Look hardest for BT-10, BT-13, BT-14 and BT-15, and invariant 7: "
    "selectors built by interpolation or matched by suffix; fallbacks that return sample data as real "
    "data; reads and writes that are not symmetric; modules that do not parse or contain leftovers from "
    "other projects; undeclared environment requirements; tests that assert the missing behavior as "
    "expected or only run from __main__."))

ALL = {p.name: p for p in (GENERAL, CORRECTNESS, SAFETY, ROBUSTNESS)}
DEFAULT = ("correctness", "safety", "robustness")


def select(spec: str) -> list[Pass]:
    """'all' = the three focused passes; otherwise comma-separated names (e.g. 'general')."""
    names = DEFAULT if spec == "all" else tuple(n.strip() for n in spec.split(",") if n.strip())
    unknown = [n for n in names if n not in ALL]
    if unknown or not names:
        raise ValueError(f"unknown pass {unknown or spec!r}; choose from {sorted(ALL)} or 'all'")
    return [ALL[n] for n in names]
