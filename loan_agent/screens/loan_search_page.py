"""
Playwright automation for the My Workspace -> Suggested Items Search page
(loan-search.html). Fills the search fields, clicks Search (or Save + Search),
and scrapes every matching loan in the results into a LoanRecord.

python loan_search_page.py --url http://localhost:9090/loan-search.html?doc-number=8202026950003648249 --headed --loan-number="104211" --property-address-1="4410 LINCOLN BLVD" --state="NJ" --zip="07304"
python loan_search_page.py --url http://localhost:9090/loan-search.html?doc-number=8202026950003648249 --headed --state="NJ"
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PWTimeout, sync_playwright

# Make loan_agent/ importable when this file is run directly as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.tools import match_insurance_names

@dataclass
class LoanSearchCriteria:
    
    primary_borrower: Optional[str] = None
    co_borrower: Optional[str] = None

    loan_number: Optional[str] = None
    policy_number: Optional[str] = None
    previous_policy_number: Optional[str] = None
    property_address_1: Optional[str] = None
    property_address_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None

@dataclass
class LoanRecord:
    row_index: int
    loan_number: str
    primary_borrower: str
    co_borrower: str
    officer_code: str
    investor: str
    property_address: str
    closing_date: str
    loan_type: str
    closing_code: str
    flood_zone: str
    lien_position: str
    usage: str

    def to_dict(self) -> dict:
        return asdict(self)

# ---------------------------------------------------------------------------
# Screen Handler class
# ---------------------------------------------------------------------------
class LoanSearchPage:
    """
    Drives the Loan Search page.
    """
    # -- Tags for scraping
    FORM = "#suggested-items-search"
    RESULTS = "#search-results"
    ROWS = "#results-list .result-item[data-loan-number]"

    # -- Tags for actions
    TODO_ACTIONS = "#todo-actions"
    DOCUMENT_ACTIONS = "#document-actions"

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
    def __enter__(self) -> "LoanSearchPage":
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
        self._context = self._browser.new_context(storage_state=self.storage_state, viewport={"width": 1280, "height": 900})
        self.page = self._context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        self.page.goto(self.url, wait_until="domcontentloaded")
        self.page.wait_for_selector(self.FORM)

    def close(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()    

    def wait_for_results(self) -> None:
        try:
            self.page.locator(f'{self.RESULTS}[data-status="loading"]').wait_for(timeout=1_000)
        except PWTimeout:
            pass
        self.page.locator(f'{self.RESULTS}[data-status="done"], {self.RESULTS}[data-status="error"]').wait_for()
        if self.page.locator(self.RESULTS).get_attribute("data-status") == "error":
            raise RuntimeError(self.page.locator("#results-body").inner_text())

    def search(self, criteria: LoanSearchCriteria, save: bool = False) -> tuple[int, list[LoanRecord]]:

        def norm(value: Optional[str]) -> str:
            return " ".join((value or "").upper().split())

        self.page.click("#btn-reset")
        for name, value in asdict(criteria).items():
            # below criteria fields are not searchable    
            if name in ["primary_borrower","co_borrower"]:
                continue
            if value is None:
                continue
            control = self.page.locator(f'{self.FORM} [data-field="{name}"]')
            if control.evaluate("el => el.tagName.toLowerCase()") == "select":
                control.select_option(value=value)
            else:
                control.fill(value)

        self.page.click("#btn-save-search" if save else "#btn-search")
        self.wait_for_results()

        raw = self.page.locator(self.ROWS).evaluate_all(
            """rows => rows.map(tr => {
                const cells = {};
                tr.querySelectorAll('[data-col]').forEach(td => cells[td.dataset.col] = td.innerText.trim());
                return { row_index: Number(tr.dataset.rowIndex), cells };
            })"""
        )

        #-- scrape suggested items from web page 
        results = [
            LoanRecord(
                row_index=r["row_index"],
                loan_number=r["cells"].get("loan_number", ""),
                primary_borrower=r["cells"].get("primary_borrower", ""),
                co_borrower=r["cells"].get("co_borrower", ""),
                officer_code=r["cells"].get("officer_code", ""),
                investor=r["cells"].get("investor_code", ""),
                property_address=r["cells"].get("property_address", ""),
                closing_date=r["cells"].get("closing_date", ""),
                loan_type=r["cells"].get("loan_type", ""),
                closing_code=r["cells"].get("closing_code", ""),
                flood_zone=r["cells"].get("flood_zone", ""),
                lien_position=r["cells"].get("lien_position", ""),
                usage=r["cells"].get("property_usage", ""),
            )
            for r in raw
        ]

        names = [n for n in (criteria.primary_borrower, criteria.co_borrower) if n and n.strip()]
        # Todo: enhance address matching 
        address = norm(criteria.property_address_1)

        matched = []
        for record in results:
            record_names = [n for n in (record.primary_borrower, record.co_borrower) if n and n.strip()]
            name_match = any(match_insurance_names(n, rn) for n in names for rn in record_names)
            # LoanRecord.property_address holds the full address, so match on address line 1 within it
            address_match = bool(address) and address in norm(record.property_address)
            if name_match or address_match:
                matched.append(record)

        return len(matched), matched    

    # -- Page Level Actions -----------------------------------------------------------
    # data = {
    #     status: ""
    #     csr: "",
    #     document_type: "",
    #     comment: ""
    # }

    def _action_todo_Edit(self, data):
        pass

    def _action_todo_Done(self, data):
        pass

    def _action_todo_Discard(self, data):
        pass

    def _action_todo_Automate(self, data):
        pass

    # -- Page Document Actions -----------------------------------------------------------
    def _action_document_ChangeDocumentClient():
        pass

    def _action_document_ReassignDocument():
        pass

    def _action_document_ReleaseDocument():
        pass

    def _acttion_document_ReleaseDocumentAndGetNext():
        pass

    def _action_document_GetNextDOcument():
        pass

    def action(self, data):
        pass

    # async def goto(self, loan_id: str):
    #     await self.page.goto(f"https://example.com/loans/{loan_id}")

    # async def get_data(self) -> dict[str, Any]:

    #     header_data, details_data = await asyncio.gather(
    #         self.header.data(),
    #         self.details.get_loan_data()
    #     )
    #     # Merge both dictionaries into one result
    #     return {**header_data, **details_data}

    # async def handle_workspace_actions(self, action: str, data: Any): 

    #     match action:
    #         case "goto":
    #             self.goto(data.loan_id)
    #         case "todo_edit":   
    #             pass
    #         case "todo_done":
    #             pass
    #         case "todo_discard":
    #             pass
    #         case _:
    #             pass

    #     return "ok"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the Workspace loan search via Playwright and scrape the results.")
    p.add_argument("--url", required=True, help="URL of document-workspace.html")
    for f in fields(LoanSearchCriteria):
        p.add_argument(f"--{f.name.replace('_', '-')}", dest=f.name, default=None)
    p.add_argument("--save", action="store_true", help="Use Save + Search instead of Search")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--out")
    p.add_argument("--storage-state", help="Playwright storage state JSON (saved login session)")
    p.add_argument("--timeout", type=int, default=15_000, help="Per-action timeout in ms")    
    return p

def main(argv: Optional[list[str]] = None) -> int:
    
    args = build_parser().parse_args(argv)
    criteria = LoanSearchCriteria(**{f.name: getattr(args, f.name) for f in fields(LoanSearchCriteria)})

    criteria.primary_borrower = "BILL & DIANA WEXFORD"
        
    with LoanSearchPage(url=args.url, headless=not args.headed, timeout_ms=args.timeout,
                                storage_state=args.storage_state) as scraper:
       count, records = scraper.search(criteria, save=args.save)
    
    print(f"Scraped {len(records)} loans.", file=sys.stderr)
    data = [r.to_dict() for r in records]
    
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    else:
        json.dump(data, sys.stdout, indent=2)
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())



"""
# Name Match rules

- Match first name and last name of borrower or co-borrower. 
- Generation I, II, III or Jr. Sr. missing in the borrower’s name is acceptable
- Nicknames are acceptable. Example: Richardson – Richy, Rishi, Rich, Richard etc. Use website to check nicknames – https://datayze.com/nickname-finder
- For EDI and List Bill documents, accept if First name and Last name on the document interchanged 
- For EDI and List Bill documents, accept if the names are partial match
- Acceptable if borrower name is matching with additional insured on the loan.
- Borrower’s name is an “Estate of ” the policy name will be accepted as the borrower is deceased. Example: GEORGE ASHLEY matches Estate of JAMES AD
- If borrower name mismatch and loan-type is Commercial then only address need to match. If address matches then we can process without marking name defficiency.
- If first name is not match from current document to IIM, need to refer previous documents, however carrier should match in both documents
- Name mismatch is Acceptable if there is a Loan Comment that name mismatch is acceptable

RESULT: Result of the matching can be either of the following   
- ACCEPTABLE
- NOT-ACCEPTABLE

ACTION:  
- If RESULT IS NOT ACCEPTABLE then issue name discrepancy letter and Status is “Policy not Accepted.”

# Address Match rules

- Street Number: Mandatory. Must match 
- Unit#: Missing acceptable but mismatch is not accepted 
- Street Directions: Missing acceptable but mismatch is not accepted
- Street Name: Mandatory. Must match
- Street Type: Missing or missmatch is accepted
- City or Zipcode: Mandatory. Either city or zipcode Must match
- State Code: Mandatory. Must match 

RESULT: Address match result can be either of the following   
- ACCEPTABLE
- NOT-ACCEPTABLE

ACTION:  
- If RESULT IS NOT ACCEPTABLE then issue address discrepancy letter and Status is “Policy not Accepted.”
"""