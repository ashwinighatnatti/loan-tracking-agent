"""The Loan Details page's top tabs other than Loan Details itself.

Comments opens the loan's comment history in a popup (#comments-dialog) whose rows live in an iframe.
The other tabs (Transaction History, Insurance Documents, Correspondence, Calls, Lender Placed Claims) have
no content in the mock page yet and no place in the loan schema, so LoanTab reads them generically: it opens
the tab and returns the rows of the first table in the tab's panel as dicts, or [] when the panel is absent.
Set PANEL on a subclass once the real screen's markup is known.
"""
from __future__ import annotations

import logging
import re
from typing import Any, ClassVar, Dict, List

from playwright.sync_api import Page

from loan_agent.loan_schema.loan import Comment

from .base import to_us_datetime

log = logging.getLogger(__name__)

# Rows of the first table under the panel, keyed by each cell's data-col (or its column header as snake_case).
READ_TABLE_JS = """panel => {
  const table = panel.querySelector('table');
  if (!table) return [];
  const snake = s => s.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  const heads = [...table.querySelectorAll('thead th')].map(th => th.dataset.col || snake(th.textContent));
  return [...table.querySelectorAll('tbody tr')].map(tr => {
    const row = {};
    [...tr.children].forEach((td, i) => { row[td.dataset.col || heads[i] || 'col_' + i] = td.textContent.replace(/\\s+/g, ' ').trim(); });
    return row;
  });
}"""


class LoanTab:
    TAB: ClassVar[str] = ""        # the tab button
    PANEL: ClassVar[str] = ""      # the region the tab shows
    HOME_TAB: ClassVar[str] = "#tab-loan-details"

    def __init__(self, page: Page):
        self.page = page

    def open(self) -> None:
        tab = self.page.locator(self.TAB)
        tab.click()
        self.page.locator(f'{self.TAB}[aria-selected="true"]').wait_for()

    def back_to_loan_details(self) -> None:
        self.page.locator(self.HOME_TAB).click()

    def read(self) -> List[Dict[str, Any]]:
        self.open()
        try:
            panel = self.page.locator(self.PANEL or "#no-panel")
            if panel.count() == 0:
                log.info("%s: no content panel on this page", type(self).__name__)
                return []
            return panel.first.evaluate(READ_TABLE_JS)
        finally:
            self.back_to_loan_details()


class TransactionHistory(LoanTab):
    TAB = "#tab-transaction-history"
    PANEL = '[data-section="transaction-history"]'


class InsuranceDocument(LoanTab):
    TAB = "#tab-insurance-documents"
    PANEL = '[data-section="insurance-documents"]'


class Correspondence(LoanTab):
    TAB = "#tab-correspondence"
    PANEL = '[data-section="correspondence"]'


class Calls(LoanTab):
    TAB = "#tab-calls"
    PANEL = '[data-section="calls"]'


class LenderPlacedClaims(LoanTab):
    TAB = "#tab-lender-placed-claims"
    PANEL = '[data-section="lender-placed-claims"]'


class Comments(LoanTab):
    """Comments tab: a popup with the comment history (newest first) in an iframe."""

    TAB = "#tab-comments"
    DIALOG = "#comments-dialog"
    FRAME = "#comments-frame"
    ROWS = "#comments-body tr[data-comment-id]"

    READ_ROWS_JS = """rows => rows.map(tr => {
      const cell = col => tr.querySelector(`td[data-col="${col}"]`);
      const time = cell('date').querySelector('time');
      return {
        comment: cell('comment').textContent.trim(),
        csr: cell('csr').textContent.trim(),
        date: time ? time.dateTime : cell('date').textContent.trim(),
        comment_type: cell('comment_type').textContent.trim(),
        source: cell('source').textContent.trim(),
      };
    })"""

    def open(self) -> None:
        self.page.locator(self.TAB).click()
        self.page.locator(f'{self.DIALOG}[data-state="open"]').wait_for()
        # The rows are written once the iframe loads; the count "(n)" is set after them.
        frame = self.page.frame_locator(self.FRAME)
        frame.locator("#comments-count").filter(has_text=re.compile(r"\(\d+\)")).wait_for()

    def close(self) -> None:
        self.page.locator("#btn-comments-cancel").click()
        self.page.locator(f'{self.DIALOG}[data-state="closed"]').wait_for(state="attached")

    def read_rows(self) -> List[Dict[str, Any]]:
        """Every comment row as shown: comment, csr, date (ISO), comment_type, source."""
        self.open()
        try:
            return self.page.frame_locator(self.FRAME).locator(self.ROWS).evaluate_all(self.READ_ROWS_JS)
        finally:
            self.close()

    def read(self) -> List[Comment]:
        return [Comment(datetime=to_us_datetime(r["date"]), type=r["comment_type"], text=r["comment"])
                for r in self.read_rows()]
