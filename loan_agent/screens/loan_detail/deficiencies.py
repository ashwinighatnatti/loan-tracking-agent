"""Deficiencies table inside one insurance line panel."""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from playwright.sync_api import Locator

from loan_agent.loan_schema.loan import Deficiency

from .base import Section

# One row per deficiency: the Deficient checkbox, and for some rows a Corrected / Waived radio pair.
READ_DEFICIENCIES_JS = """root => [...root.querySelectorAll('tbody tr')].map(tr => {
  const box = tr.querySelector('input[type=checkbox]');
  const picked = tr.querySelector('input[type=radio]:checked');
  return {
    title: tr.querySelector('.title').textContent.replace(/\\s+/g, ' ').trim(),
    flag: !!(box && box.checked),
    corrected: !!picked && picked.value === 'Corrected',
    waived: !!picked && picked.value === 'Waived',
  };
})"""


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", title or "").strip().casefold()


class Deficiencies(Section):
    ROOT = '[data-section="deficiencies"]'

    def read(self) -> List[Deficiency]:
        return [Deficiency.from_dict(d) for d in self.root.evaluate(READ_DEFICIENCIES_JS)]

    # -- actions -------------------------------------------------------------
    def mark(self, title: str, flag: bool, status: Optional[str] = None) -> None:
        """Tick/untick a deficiency by its title; status "Corrected" or "Waived" picks the radio where the row has one."""
        row = self._row(title)
        row.locator("input[type=checkbox]").set_checked(flag)
        if status:
            row.locator(f'input[type=radio][value="{status}"]').check()

    def request_letters(self) -> None:
        self.click("btn-request-letters")

    def _row(self, title: str) -> Locator:
        rows = self.root.locator("tbody tr")
        for i in range(rows.count()):
            row = rows.nth(i)
            if _norm(row.locator(".title").text_content()) == _norm(title):
                return row
        raise ValueError(f"No deficiency titled {title!r}")


def merge_deficiencies(groups: Iterable[List[Deficiency]]) -> List[Deficiency]:
    """Loan-level view of per-line deficiencies: one entry per title, set if it is set on any line."""
    merged: dict[str, Deficiency] = {}
    for group in groups:
        for d in group:
            m = merged.setdefault(_norm(d.title), Deficiency(title=d.title))
            m.flag |= d.flag
            m.corrected |= d.corrected
            m.waived |= d.waived
    return list(merged.values())
