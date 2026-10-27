"""Insurance Lines section: one tab + div.linepanel per line on the selected collateral.

Every panel repeats the same data-field names, so each InsuranceLineSection is scoped to its own panel.
Inactive panels are [hidden] but stay in the DOM, so all lines can be read without switching tabs.
"""
from __future__ import annotations

from typing import List, Tuple

from playwright.sync_api import Locator, Page

from loan_agent.loan_schema.loan import InsuranceLine

from .base import Section, join_lines
from .deficiencies import Deficiencies

# Mirrors LINE_ALIASES in loan-detail-page.html, inverted (page data-field -> schema field).
LINE_FIELD_MAP = {
    "carrier_name": "carrier_name",
    "carrier_address": "carrier_address",
    "carrier_global_payee_regular_mail_address": "carrier_global_payee_regular_mail_address",
    "carrier_global_payee_overnight_mail_address": "carrier_global_payee_overnight_mail_address",
    "pay_agent": "chk_pay_agent",
    "mail_payment_to_agent": "chk_mail_payment_to_agent",

    "agent_name": "agent_name",
    "agent_address1": "agent_address_1",
    "agent_address2": "agent_address_2",
    "agent_city": "agent_city",
    "agent_state": "agent_state",
    "agent_zip": "agent_zip",
    "agent_country": "agent_country",
    "agent_email": "agent_email",
    "agent_phone": "agent_phone",
    "agent_fax": "agent_fax",

    "policy_number": "policy_number",
    "effective_date": "effective_date",
    "expiration_date": "expiration_date",
    "premium_due_date": "premium_due_date",
    "policy_term": "policy_term",

    "escrow_status": "escrow_status",
    "earliest_cancellation_date": "earliest_cancellation_date",
    "earliest_cancellation_reinstate_reason": "earliest_cancellation_or_reinstatement_reason",
    "cancel_reinstate_date": "cancel_or_reinstate_date",
    "cancel_reinstate_reason": "cancel_or_reinstate_reason",

    "coverage_amount": "coverage_amount",
    "cert_flood_zone": "cert_flood_zone",
    "deductible_amount": "deductible_amount",
    "deductible_percentage": "deductible_percentage",
    "no_replacement_coverage": "no_replacement_coverage",
    "wind_deductible_amount": "wind_deductible_amount",
    "wind_deductible_percentage": "wind_deductible_percentage",
    "wind_excluded": "wind_excluded",

    "last_payment_date": "last_payment_date",
    "last_payment_amount": "last_premium_amount",
    "last_payment_payee": "last_payee",
    "last_payment_check_number": "last_cheque_info",

    "premium_amount": "premium_amount",
    "premium_amount_make_payment": "chk_make_payment",
    "premium_amount_expedite": "chk_expedite_payment",
    "premium_amount_funding_only": "chk_funding_only",
    "premium_amount_funding_only_comment": "funding_only_comment",
    "additional_amt_due": "additional_amount_due",
    "additional_amt_due_make_payment": "chk_additional_amount_due",
    "additional_amt_due_expedite": "chk_expedite_additional_amount_due",
}

ESCROW_CODES = {"yes": "Y", "no": "N"}


def split_carrier_address(text: str) -> Tuple[str, str]:
    """The Carrier box holds address lines, then "Phone: ..." and "Email:" lines.
    Returns (address on one line, phone)."""
    address, phone = [], ""
    for line in (l.strip() for l in (text or "").splitlines()):
        if not line:
            continue
        label = line.split(":", 1)[0].casefold()
        if label == "phone":
            phone = line.split(":", 1)[1].strip()
        elif label == "email":
            break       # no schema field for the carrier e-mail
        else:
            address.append(line)
    return ", ".join(address), phone


class InsuranceLineSection(Section):
    """One insurance line panel (div.linepanel)."""

    FIELD_MAP = LINE_FIELD_MAP
    DATE_FIELDS = frozenset({"effective_date", "expiration_date", "premium_due_date",
                             "earliest_cancellation_date", "cancel_or_reinstate_date", "last_payment_date"})
    SKIP_PANELS = False

    def __init__(self, page: Page, root: Locator):
        super().__init__(page, root)
        self.deficiencies = Deficiencies(page, root.locator(Deficiencies.ROOT))

    @property
    def line_type(self) -> str:
        return self.root.get_attribute("data-line-type") or ""

    @property
    def line_id(self) -> str:
        return self.root.get_attribute("data-line-id") or ""

    def read(self, linked_property_id: str = "") -> InsuranceLine:
        data = self.read_mapped()
        data["carrier_address"], data["carrier_phone"] = split_carrier_address(data.get("carrier_address", ""))
        for key in ("carrier_global_payee_regular_mail_address", "carrier_global_payee_overnight_mail_address"):
            data[key] = join_lines(data.get(key, ""))
        data["escrow_status"] = ESCROW_CODES.get(str(data.get("escrow_status", "")).casefold(), data.get("escrow_status", ""))

        line = InsuranceLine.from_dict(data)
        line.line_id = self.line_id
        line.line_type = line.policy_type = self.line_type      # rules look lines up by policy_type
        line.linked_property_id = linked_property_id
        line.warnings = self.warnings()
        line.deficiencies = self.deficiencies.read()
        return line

    def warnings(self) -> List[str]:
        return [t.strip() for t in self.root.locator('[data-section="warnings-block"] li').all_text_contents()]

    # -- actions -------------------------------------------------------------
    def select(self) -> None:
        """Make this line the active tab."""
        self.page.locator(f'#{self.root.get_attribute("aria-labelledby")}').click()
        self.root.wait_for(state="visible")

    def add_comment(self, text: str, comment_type: str = "") -> None:
        self.select()
        if comment_type:
            self.set_field("comment_type", comment_type)
        self.set_field("loan_comment", text)

    def save(self) -> None:
        self.select()
        self.click("btn-save-insurance-line")

    def save_and_done_todo(self) -> None:
        self.select()
        self.click("btn-save-line-and-done-todo")


class InsuranceLines(Section):
    """The Insurance Lines section: the line tabs and their panels."""

    ROOT = '[data-section="insurance-lines"]'
    PANELS = '[data-section="insurance-line"]'

    def lines(self) -> List[InsuranceLineSection]:
        panels = self.root.locator(self.PANELS)
        return [InsuranceLineSection(self.page, panels.nth(i)) for i in range(panels.count())]

    def read(self, linked_property_id: str = "") -> List[InsuranceLine]:
        return [line.read(linked_property_id) for line in self.lines()]

    def find(self, line_type: str = "", policy_number: str = "", line_id: str = "") -> InsuranceLineSection:
        """The panel matching every criterion given (line type ignores case)."""
        for line in self.lines():
            attrs = line.root
            if line_type and (attrs.get_attribute("data-line-type") or "").casefold() != line_type.casefold():
                continue
            if policy_number and attrs.get_attribute("data-policy-number") != policy_number:
                continue
            if line_id and attrs.get_attribute("data-line-id") != line_id:
                continue
            return line
        raise ValueError(f"No insurance line matching type={line_type!r} policy={policy_number!r} id={line_id!r}")

    def select_line(self, line_type: str = "", policy_number: str = "", line_id: str = "") -> InsuranceLineSection:
        line = self.find(line_type, policy_number, line_id)
        line.select()
        return line
