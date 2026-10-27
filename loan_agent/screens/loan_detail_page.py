"""
Playwright automation for the Loan Details page (loan-detail-page.html). Reads the whole loan - Loan
Information, every Collateral with its Insurance Lines and their Deficiencies, and the Comments popup -
into a loan_schema.Loan and writes it as JSON (same shape as loan_schema/loan.json).

The per-area handlers live in screens/loan_detail/; this class owns the browser and composes them:

    LoanDetailPage
      .loan_information        LoanInformation
      .collateral              CollateralInformation  -> .insurance_lines -> InsuranceLineSection -> .deficiencies
      .comments                Comments (popup)
      .transaction_history, .insurance_documents, .correspondence, .calls, .lender_placed_claims

python loan_detail_page.py --url "file:///C:/.../loan_agent/mocks/loan-detail-page.html" --out loan.json
python loan_detail_page.py --url "http://localhost:9090/loan-detail-page.html?loan-number=7750646441" --headed
python loan_detail_page.py --url http://localhost:9090/loan-detail-page.html --loan-number 7750646441 --out loan-scr.json

#=== claude analysis of comapring the source json and scraped json

The scrape matches the source on every field the page displays. The differences are fields the page never shows, two formatting changes, and a few that come from how the source file is written.

**1. Formatting changes (the only real mismatches)**

| Field | Source | Scraped | Cause |
|---|---|---|---|
| `collateral[0].property_address` | `56 HAWTHORN ST, BURLINGTON, VT 05401` | `56 HAWTHORN ST BURLINGTON, VT 05401` | The page has no full-address field, so the scraper builds it. I copied the format from `loan_schema/loan.json` (no comma after the street), but this file puts a comma there. |
| `policy_term` (both lines) | `12 months` | `12 Months` | The page picks its dropdown option case-insensitively, so the scraper reads back the option text. |

**2. Fields the page doesn't show, so they come back empty**

| Field | Source | Scraped |
|---|---|---|
| `escrow_status` (loan level) | `Y` | `""` |
| `loan_originated` | `10/01/2023` | `""` |
| `loan_reported_to_app` | `10/09/2023` | `""` |
| `contacts` | 1 contact (Nora A Fenwick) | `[]` |
| `collateral[0].property_status` | `Active` | `""` |
| `collateral[0].flood_determination_date` | `08/16/2006` | `""` |
| `note_comments` (both lines) | 1 comment | `[]` |

The page has no element for any of these, so no scraper change can fill them in. Getting them would need another screen, such as the Contact Summary or Full Loan Detail popups.

**3. Differences from how the source is written (no data lost)**

- **`mortgagee`:** the source has one entry with every field blank; the scrape returns `[]`.
- **Loan `deficiencies`:**
  - The source has 5 entries, all with an empty title. The page matches deficiencies by title, so none of them showed up on screen.
  - The scrape returns the page's fixed list of 8 titled deficiencies, all unset. That is what the screen actually shows.
- **Line `deficiencies`:** this is the new per-line field, so the source doesn't have it.
- **Wind line, `total_premium_amount` → `premium_amount`:** the source uses `total_premium_amount`, which isn't a schema field. The page shows it as the premium amount, so the scrape correctly has `premium_amount: 9999.99`.
- **Wind line, `date_of_change`:** the source has it, but it isn't a schema field and the page doesn't show it, so it's dropped.
- **`committment_amount` → `commitment_amount`:** the schema already renames the misspelled key, so the value is the same.

Everything else matches, including both comments, every carrier and agent field, amounts, dates, checkboxes and warnings.

**Possible fixes**
- **`property_address`:** pick one format, then align the scraper and the two sample files to it. Since the screen doesn't show this field, you could also leave it empty.
- **Case-insensitive comparison:** if you diff scraped and source files automatically, compare text like `policy_term` without case, as the page does.
- **Source deficiencies:** give them real titles if you want them to show on the page and come back in the scrape.


"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# Make the project root importable when this file is run directly as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from loan_agent.loan_schema.loan import Loan
from loan_agent.screens.loan_detail import (Calls, CollateralInformation, Comments, Correspondence,
                                            InsuranceDocument, LenderPlacedClaims, LoanInformation,
                                            TransactionHistory, merge_deficiencies)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Screen Handler class
# ---------------------------------------------------------------------------
class LoanDetailPage:
    """
    Drives the Loan Details page.
    """
    PAGE = "#page-loan-detail"
    LOAN_INPUT = "#loan-number-input"
    LOAN_GO = "#loan-number-go"

    def __init__(self, url: str, headless: bool = True, timeout_ms: int = 15_000,
                 storage_state: Optional[str] = None, slow_mo: int = 0):
        self.url = url
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.storage_state = storage_state
        self.slow_mo = slow_mo

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self) -> "LoanDetailPage":
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
        self._context = self._browser.new_context(storage_state=self.storage_state, viewport={"width": 1280, "height": 900})
        self.attach(self._context.new_page())
        self.page.goto(self.url, wait_until="domcontentloaded")
        self.page.wait_for_selector(self.PAGE)
        # ?loan-number=... makes the page fetch the loan from the API after it loads
        if parse_qs(urlparse(self.url).query).get("loan-number"):
            self.wait_for_loan()

    def attach(self, page: Page) -> None:
        """Use an already open page (e.g. one a previous screen navigated to) and build the section handlers."""
        self.page = page
        self.page.set_default_timeout(self.timeout_ms)
        self.loan_information = LoanInformation(page)
        self.collateral = CollateralInformation(page)
        self.comments = Comments(page)
        self.transaction_history = TransactionHistory(page)
        self.insurance_documents = InsuranceDocument(page)
        self.correspondence = Correspondence(page)
        self.calls = Calls(page)
        self.lender_placed_claims = LenderPlacedClaims(page)

    def close(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()

    # -- actions -------------------------------------------------------------
    def search_loan(self, loan_number: str) -> None:
        """Load another loan through the Loan # box."""
        self.page.fill(self.LOAN_INPUT, loan_number)
        self.page.click(self.LOAN_GO)
        self.wait_for_loan()

    # -- scraping ------------------------------------------------------------
    def scrape(self) -> Loan:
        """The whole loan as shown on the page."""
        loan = Loan.from_dict(self.loan_information.read())
        loan.collateral = self.collateral.read_all()
        # The schema keeps deficiencies per loan too; the page shows the same table on every line.
        loan.deficiencies = merge_deficiencies(
            line.deficiencies for c in loan.collateral for line in c.insurance_lines)
        loan.comments = self.comments.read()
        return loan

    def scrape_tabs(self) -> Dict[str, List[Dict[str, Any]]]:
        """Rows of the tabs the loan schema has no place for (empty until those screens have content)."""
        return {
            "transaction_history": self.transaction_history.read(),
            "insurance_documents": self.insurance_documents.read(),
            "correspondence": self.correspondence.read(),
            "calls": self.calls.read(),
            "lender_placed_claims": self.lender_placed_claims.read(),
        }

    # -- internals -----------------------------------------------------------
    def wait_for_loan(self) -> None:
        self.page.locator('body[data-loan-load="ok"], body[data-loan-load="error"]').wait_for(state="attached")
        if self.page.locator("body").get_attribute("data-loan-load") == "error":
            raise RuntimeError(self.page.locator("#loan-load-status").inner_text())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape the Loan Details page via Playwright into loan JSON.")
    p.add_argument("--url", required=True, help="URL of loan-detail-page.html")
    p.add_argument("--loan-number", help="Load this loan through the Loan # box before scraping")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--out", help="Output JSON file (default: stdout)")
    p.add_argument("--storage-state", help="Playwright storage state JSON (saved login session)")
    p.add_argument("--timeout", type=int, default=15_000, help="Per-action timeout in ms")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    with LoanDetailPage(url=args.url, headless=not args.headed, timeout_ms=args.timeout,
                        storage_state=args.storage_state) as screen:
        if args.loan_number:
            screen.search_loan(args.loan_number)
        loan = screen.scrape()

    lines = sum(len(c.insurance_lines) for c in loan.collateral)
    print(f"Scraped loan {loan.loan_number}: {len(loan.collateral)} collateral, {lines} insurance lines, "
          f"{len(loan.comments)} comments.", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(loan.to_json(indent=2), encoding="utf-8")
    else:
        print(loan.to_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
