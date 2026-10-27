import pytest

from loan_agent.loan_schema.loan import Collateral, InsuranceLine, Loan
from loan_agent.loan_schema.loan_docinfo import INSURANCE_DOCUMENT_TYPE, RenewalDocInfo
from loan_agent.rules.line_rules import process_document

# iim line ; doc line ; expected
# Each line is "policy | carrier | effective | expiration" (see InsuranceLine.STRING_FIELDS).
# Expected is the status of each action process_document returns, joined with " + ", "none" when it returns
# no actions, or "error" when the line should be rejected. Lines starting with # are skipped.
PROCESS_LINES = """
# --- AOF (closes as Complete): same carrier, same policy, same term ---
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; Complete
# spaces and case don't matter
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; abc1234 | abc  carrier | 01/01/2025 | 12/31/2025 ; Complete

# --- Policy Not Accepted: doc term ends before the one on file starts ---
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; ABC1234 | ABC Carrier | 1/1/2024 | 12/31/2024 ; Policy Not Accepted

# --- Not Tracked: doc policy has a lender placed suffix ---
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; ABC-1234 MLR | ABC Carrier | 1/1/2026 | 12/31/2026 ; Not Tracked
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; ABC1234#FLR | XYZ Carrier | 1/1/2026 | 12/31/2026 ; Not Tracked

# --- no actions yet: renewal, rewrite, new business, mid term ---
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; ABC1234 | ABC Carrier | 1/1/2026 | 12/31/2026 ; none
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; ABC9999 | ABC Carrier | 1/1/2026 | 12/31/2026 ; none
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; XYZ5678 | XYZ Carrier | 1/1/2026 | 12/31/2026 ; none
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; XYZ5678 | XYZ Carrier | 7/1/2025 | 6/30/2026 ; none

# --- error: invalid input is rejected ---
ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; ABC1234 | ABC Carrier | 2/30/2025 | 12/31/2025 ; error
ABC1234 | ABC Carrier | 1/1/2025 ; ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025 ; error
"""

CASES = [line.strip() for line in PROCESS_LINES.strip().splitlines()
         if line.strip() and not line.lstrip().startswith("#")]


def run_document(iim_text, doc_text):
    """Wraps the iim line in a one-collateral loan and runs the doc through process_document."""
    line = InsuranceLine.from_string(iim_text)
    doc = RenewalDocInfo.from_string(doc_text)
    line.policy_type = doc.policy_type = "hazard"
    doc.property_address = "1 Main St"
    doc.document_type = INSURANCE_DOCUMENT_TYPE.RENEWAL
    loan = Loan(collateral=[Collateral(property_address="1 Main St", insurance_lines=[line])])
    return process_document(loan, doc)


@pytest.mark.parametrize("case", CASES)
def test_process_document(case):
    iim_text, doc_text, expected = [p.strip() for p in case.split(";")]

    if expected.lower() == "error":
        with pytest.raises(ValueError):
            run_document(iim_text, doc_text)
        return

    actions = run_document(iim_text, doc_text).actions
    actual = " + ".join(a.status for a in actions) or "none"
    assert actual.casefold() == expected.casefold()
