"""Document-to-loan linking on name AND address with an explicit ambiguity outcome (fix for F-10)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class LoanRecord:
    loan_number: str
    borrowers: str
    property_address: str


def link(doc_borrowers: str, doc_address: str, records: list[LoanRecord],
         names_match: Callable[[str, str], bool],
         addresses_match: Callable[[str, str], bool]) -> tuple[str, list[LoanRecord]]:
    hits = [r for r in records
            if names_match(doc_borrowers, r.borrowers) and addresses_match(doc_address, r.property_address)]
    if not hits:
        return "no_match", []
    if len(hits) > 1:
        return "ambiguous", hits
    return "matched", hits
