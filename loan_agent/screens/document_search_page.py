"""
Playwright automation for the Document Search web app.

Fills the search filters, clicks Submit, then pages through every results page,
scraping each table row from the screen into a DocumentRecord. All rows across
all pages are returned as a single list.

Run `python document_search_page.py --help` for the CLI, or import
DocumentSearch / DocumentSearchCriteria to use it as a library.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import Iterator, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PWTimeout, sync_playwright

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class DocumentSearchCriteria:
    """Values typed into the filter bar. Empty string / None leaves a filter untouched."""
    client: Optional[str] = None            # select value, e.g. "41207"; "" = All
    number: Optional[str] = None
    import_from: Optional[str] = None       # MM/DD/YY
    import_to: Optional[str] = None
    type: Optional[str] = None              # "Renewal", "New Policy", ...; "" = All
    source: Optional[str] = None            # "E-mail/Fax", ...
    loan_number: Optional[str] = None
    status: Optional[str] = None            # "To Be Processed", ...
    csr: Optional[str] = None
    update_from: Optional[str] = None
    update_to: Optional[str] = None
    comments: Optional[str] = None

    def items(self):
        return {k: v for k, v in asdict(self).items() if v is not None}.items()

@dataclass
class DocumentRecord:
    """One row of the results table, exactly as displayed on screen."""
    page: int
    row_index: int
    client: str
    document_number: str
    import_date: str
    doc_type: str
    doc_source: str
    loan_number: str
    status: str
    csr: str
    last_update: str
    comments: str
    view_url: str = ""
    work_url: str = ""
    assign_url: str = ""
    pdf_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

# ---------------------------------------------------------------------------
# Screen Handler class
# ---------------------------------------------------------------------------
class DocumentSearchPage:
    """
    Drives the Document Search page.

    Selectors rely on the stable hooks the app exposes:
      #filters [data-field=...]      filter inputs / selects
      #btn-submit, #btn-reset        buttons
      #search-results[data-status]   idle | loading | done | error
      #result-count[data-total|data-pages|data-page]
      #results-body tr[data-document-number] > td[data-col]
      #pager a[data-page]
    """

    FILTERS = "#filters"
    SUBMIT = "#btn-submit"
    RESET = "#btn-reset"
    RESULTS = "#search-results"
    COUNT = "#result-count"
    ROWS = "#results-body tr[data-document-number]"
    PAGER = "#pager"

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
    def __enter__(self) -> "DocumentSearch":
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
        self.page.locator(self.FILTERS).wait_for()

    def close(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()

    # -- public API ----------------------------------------------------------
    def search(self, criteria: DocumentSearchCriteria | None = None, sort: Optional[str] = None,
               descending: bool = False, max_pages: Optional[int] = None) -> list[DocumentRecord]:
        """Fill filters, submit, scrape every page, return all records as one list."""
        return list(self.iter_search(criteria, sort=sort, descending=descending, max_pages=max_pages))

    def iter_search(self, criteria: DocumentSearchCriteria | None = None, sort: Optional[str] = None,
                    descending: bool = False, max_pages: Optional[int] = None) -> Iterator[DocumentRecord]:
        """Same as search() but yields records page by page as they are scraped."""
        self.reset()
        self.fill_filters(criteria or DocumentSearchCriteria())
        self.submit()
        if sort:
            self.sort_by(sort, descending)

        total_pages = self.page_count()
        last_page = total_pages if max_pages is None else min(total_pages, max_pages)
        for page_no in range(1, last_page + 1):
            if page_no > 1:
                self.go_to_page(page_no)
            yield from self.scrape_current_page()

    def total_items(self) -> int:
        return int(self.page.locator(self.COUNT).get_attribute("data-total") or 0)

    def page_count(self) -> int:
        return int(self.page.locator(self.COUNT).get_attribute("data-pages") or 0)

    def current_page(self) -> int:
        return int(self.page.locator(self.COUNT).get_attribute("data-page") or 0)

    # -- interactions --------------------------------------------------------
    def reset(self) -> None:
        self.page.click(self.RESET)
        #-- deprecated
        # self.page.wait_for_selector(f'{self.RESULTS}[data-status="idle"]')
        self.page.locator(f'{self.RESULTS}[data-status="idle"]').wait_for()

    def fill_filters(self, criteria: DocumentSearchCriteria) -> None:
        for name, value in criteria.items():
            control = self.page.locator(f'{self.FILTERS} [data-field="{name}"]')
            tag = control.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                # Try value first, then visible label, so "41207" and "Renewal" both work.
                try:
                    control.select_option(value=value)
                except PWTimeout:
                    control.select_option(label=value)
            else:
                control.fill(value)

    def submit(self) -> None:
        self.page.click(self.SUBMIT)
        self._wait_for_results()

    def sort_by(self, column: str, descending: bool = False) -> None:
        header_btn = self.page.locator(f'#results-table th[data-col="{column}"] button')
        if header_btn.count() == 0:
            raise ValueError(f"Column '{column}' is not sortable or does not exist")
        header_btn.click()
        self._wait_for_results()
        if descending:
            header_btn.click()
            self._wait_for_results()

    def go_to_page(self, page_no: int) -> None:
        """Navigate through the pager to `page_no`, following '>' when it is out of the visible window."""
        for _ in range(50):  # safety bound
            if self.current_page() == page_no:
                return
            link = self.page.locator(f'{self.PAGER} a[data-page="{page_no}"]')
            if link.count():
                link.first.click()
            else:
                direction = ">" if page_no > self.current_page() else "<"
                self.page.locator(self.PAGER).get_by_text(direction, exact=True).first.click()
            self._wait_for_results()
        raise RuntimeError(f"Could not reach page {page_no}")

    # -- scraping ------------------------------------------------------------
    def scrape_current_page(self) -> list[DocumentRecord]:
        """Read every visible row of the table from the DOM and build records."""
        page_no = self.current_page()
        rows = self.page.locator(self.ROWS)
        raw = rows.evaluate_all(
            """rows => rows.map(tr => {
                 const cells = {};
                 tr.querySelectorAll('td[data-col]').forEach(td => cells[td.dataset.col] = td.innerText.trim());
                 const href = sel => { const a = tr.querySelector(sel); return a ? a.href : ''; };
                 return {
                   row_index: Number(tr.dataset.rowIndex),
                   cells,
                   view_url: href('a[data-action="view"]'),
                   work_url: href('a[data-action="work"]'),
                   assign_url: href('a[data-action="assign"]'),
                   pdf_url: href('a[data-action="open-pdf"]'),
                 };
               })"""
        )
        records = []
        for r in raw:
            c = r["cells"]
            records.append(DocumentRecord(
                page=page_no,
                row_index=r["row_index"],
                client=c.get("client", ""),
                document_number=c.get("document_number", ""),
                import_date=c.get("import_date", ""),
                doc_type=c.get("doc_type", ""),
                doc_source=c.get("doc_source", ""),
                loan_number=c.get("loan_number", ""),
                status=c.get("status", ""),
                csr=c.get("csr", ""),
                last_update=c.get("last_update", ""),
                comments=c.get("comments", ""),
                view_url=r["view_url"],
                work_url=r["work_url"],
                assign_url=r["assign_url"],
                pdf_url=r["pdf_url"],
            ))
        return records

    # -- internals -----------------------------------------------------------
    def _wait_for_results(self) -> None:
        results = self.page.locator(self.RESULTS)
        # The app flips data-status to "loading" then "done"/"error"; wait for a settled state.
        try:
            self.page.locator(f'{self.RESULTS}[data-status="loading"]').wait_for(timeout=1_000)
        except PWTimeout:
            pass  # response was fast enough that we never saw "loading"
        
        self.page.locator(f'{self.RESULTS}[data-status="done"], {self.RESULTS}[data-status="error"]').wait_for()
        if results.get_attribute("data-status") == "error":
            msg = self.page.locator("#results-empty").inner_text()
            raise RuntimeError(f"Search failed on page: {msg}")

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def write_records(records: list[DocumentRecord], path: str) -> None:
    if path.lower().endswith(".csv"):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=[f.name for f in fields(DocumentRecord)])
            writer.writeheader()
            writer.writerows(r.to_dict() for r in records)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([r.to_dict() for r in records], fh, indent=2)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    
    p = argparse.ArgumentParser(description="Run a Document Search via Playwright and scrape all result rows.")
    p.add_argument("--url", required=True, help="URL of document-search.html (file://, http://, or hosted)")

    for name in [f.name for f in fields(DocumentSearchCriteria)]:
        p.add_argument(f"--{name.replace('_', '-')}", dest=name, default=None)
    
    p.add_argument("--sort", help="Column to sort by before scraping, e.g. import_date")
    p.add_argument("--desc", action="store_true", help="Sort descending")
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--out", help="Write results to this .json or .csv file")
    p.add_argument("--headed", action="store_true", help="Show the browser window")
    p.add_argument("--storage-state", help="Playwright storage state JSON (saved login session)")
    p.add_argument("--timeout", type=int, default=15_000, help="Per-action timeout in ms")
    return p

def main(argv: Optional[list[str]] = None) -> int:
    
    args = build_parser().parse_args(argv)
    criteria = DocumentSearchCriteria(**{f.name: getattr(args, f.name) for f in fields(DocumentSearchCriteria)})

    with DocumentSearchPage(url=args.url, headless=not args.headed, timeout_ms=args.timeout,
                               storage_state=args.storage_state) as scraper:
        records = scraper.search(criteria, sort=args.sort, descending=args.desc, max_pages=args.max_pages)
        total, pages = scraper.total_items(), scraper.page_count()

    print(f"Scraped {len(records)} of {total} documents across {pages} page(s).", file=sys.stderr)
    if args.out:
        write_records(records, args.out)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        json.dump([r.to_dict() for r in records], sys.stdout, indent=2)
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
