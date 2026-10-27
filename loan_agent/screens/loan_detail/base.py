"""Shared plumbing for the Loan Details screen sections.

Every value on the page carries a snake_case data-field, and every region a data-section. A Section wraps
one region (a Playwright Locator), reads all of its data-field values in one round trip and maps them onto
the loan_schema field names. Write actions go through set_field / click so subclasses stay small.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, ClassVar, Dict, Optional

from playwright.sync_api import Locator, Page

# Reads every [data-field] under the scope element into {data_field: value}, the same way the page's own
# getLoanDetail() does: checkbox -> bool, radio group -> checked value, select -> selected text,
# input/textarea -> value, display element -> trimmed text. Suggested-value chips (document values, not
# loan data) are skipped, and so are fields inside insurance-line panels unless the scope is the panel.
READ_FIELDS_JS = """(scope, skipPanels) => {
  const out = {};
  scope.querySelectorAll('[data-field]').forEach(el => {
    if (el.matches('[data-target][data-value]')) return;
    if (skipPanels && el.closest('.linepanel')) return;
    const f = el.dataset.field;
    if (el.type === 'checkbox') out[f] = el.checked;
    else if (el.type === 'radio') { if (el.checked) out[f] = el.value; else if (!(f in out)) out[f] = ''; }
    else if (el.tagName === 'SELECT') out[f] = el.selectedIndex < 0 ? '' : el.options[el.selectedIndex].text.trim();
    else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') out[f] = el.value;
    else out[f] = el.textContent.replace(/\\s+/g, ' ').trim();
  });
  return out;
}"""

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def to_us_date(value: str) -> str:
    """"2025-09-13" or "9/13/2025" -> "09/13/2025", the format loan.json uses. Anything else passes through."""
    text = (value or "").strip()
    if m := _ISO_DATE.match(text):
        return f"{m[2]}/{m[3]}/{m[1]}"
    if m := _US_DATE.match(text):
        return f"{int(m[1]):02d}/{int(m[2]):02d}/{m[3]}"
    return text


def to_iso_date(value: str) -> str:
    """"09/13/2025" -> "2025-09-13", the value an <input type=date> takes. ISO dates pass through."""
    text = (value or "").strip()
    if m := _US_DATE.match(text):
        return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"
    return text


def to_us_datetime(iso: str) -> str:
    """"2024-06-28T14:47" -> "06/28/2024 2:47 PM", the comment datetime format in loan.json."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{dt:%m/%d/%Y} {dt.hour % 12 or 12}:{dt:%M %p}"


def join_lines(text: str, sep: str = ", ") -> str:
    """Multi-line textarea value -> one line, dropping the indentation and blank lines."""
    return sep.join(line.strip() for line in (text or "").splitlines() if line.strip())


class Section:
    """One region of the Loan Details page.

    Subclasses set ROOT (css selector of the region) or are handed a root Locator, and describe how page
    fields map onto schema fields:
      FIELD_MAP   - page data-field -> schema field; page fields not listed here are not scraped
      DATE_FIELDS - schema fields holding dates, normalised to MM/DD/YYYY
    """

    ROOT: ClassVar[str] = ""
    FIELD_MAP: ClassVar[Dict[str, str]] = {}
    DATE_FIELDS: ClassVar[frozenset[str]] = frozenset()
    SKIP_PANELS: ClassVar[bool] = True

    def __init__(self, page: Page, root: Optional[Locator] = None):
        self.page = page
        self.root = root if root is not None else page.locator(self.ROOT)

    # -- reading -------------------------------------------------------------
    def read_raw(self) -> Dict[str, Any]:
        """All data-field values in the region, keyed by the page's data-field names."""
        return self.root.evaluate(READ_FIELDS_JS, self.SKIP_PANELS)

    def read_mapped(self) -> Dict[str, Any]:
        """The region's values keyed by schema field names, ready for <Model>.from_dict()."""
        raw = self.read_raw()
        out: Dict[str, Any] = {}
        for page_field, schema_field in self.FIELD_MAP.items():
            if page_field not in raw:
                continue
            value = raw[page_field]
            out[schema_field] = to_us_date(value) if schema_field in self.DATE_FIELDS else value
        return out

    # -- writing -------------------------------------------------------------
    def field(self, name: str) -> Locator:
        """Locator for a field by its page data-field name or its schema field name."""
        return self.root.locator(f'[data-field="{self._page_field(name)}"]:not([data-target])')

    def set_field(self, name: str, value: Any) -> None:
        """Write `value` to a field, picking the right interaction for its control type."""
        control = self.field(name)
        kind = control.first.evaluate("el => el.tagName === 'SELECT' ? 'select' : (el.type || el.tagName).toLowerCase()")
        if kind == "radio":
            self.root.locator(f'[data-field="{self._page_field(name)}"][value="{value}"]').check()
        elif kind == "checkbox":
            control.set_checked(bool(value))
        elif kind == "select":
            control.select_option(label=str(value))
        elif kind == "date":
            control.fill(to_iso_date(str(value)))
        else:
            control.fill("" if value is None else str(value))

    def set_fields(self, values: Dict[str, Any]) -> None:
        for name, value in values.items():
            self.set_field(name, value)

    def click(self, testid: str) -> None:
        """Click a control in the region by test id. Matched as a suffix, since insurance-line panels after the
        first prefix their test ids ("wind-line-btn-save-insurance-line")."""
        self.root.locator(f'[data-testid$="{testid}"]').click()

    def _page_field(self, name: str) -> str:
        reverse = {schema: page for page, schema in self.FIELD_MAP.items()}
        return reverse.get(name, name)
