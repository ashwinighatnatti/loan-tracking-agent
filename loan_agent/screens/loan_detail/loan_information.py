"""Loan Information (header) section: read-only loan-level fields, plus the loan bar above it."""
from __future__ import annotations

from typing import Any, Dict

from .base import Section


class LoanInformation(Section):
    ROOT = '[data-section="loan-information"]'

    FIELD_MAP = {
        "primary_borrower": "primary_borrower",
        "co_borrower": "co_borrower",
        "maturity_date": "maturity_date",
        "closing_date": "closing_date",
        "created_date": "created_date",
        "date_of_note": "date_of_note",
        "loan_origination_method": "loan_origination_method",
        "original_balance": "original_balance",
        "upb": "upb",
        "commitment_amount": "commitment_amount",
        "branch_number": "branch",
        "investor_code": "investor_code",
        "govt_loan_type": "govt_loan_type",
        "organization": "organization",
        "officer_code": "officer_code",
        "client_system": "client_system",
        "asset_manager": "asset_manager",
        "loan_type": "loan_type",
    }
    DATE_FIELDS = frozenset({"maturity_date", "closing_date", "created_date", "date_of_note"})

    LOAN_BAR = '[data-section="loan-bar"]'

    def read(self) -> Dict[str, Any]:
        """Loan-level schema fields (no collections), including loan_number from the loan bar."""
        data = self.read_mapped()
        bar = self.page.locator(self.LOAN_BAR)
        data["loan_number"] = (bar.get_by_test_id("loan-number-display").inner_text().strip()
                               or bar.get_by_test_id("loan-number-input").input_value().strip())
        return data
