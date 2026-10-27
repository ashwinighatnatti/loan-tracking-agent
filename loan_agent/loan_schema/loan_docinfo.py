from __future__ import annotations

import json
import typing
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type, TypeVar, get_args, get_origin
from enum import Enum

try:
    from .loan import LoanModel
except ImportError:  # run directly as a script
    from loan import LoanModel

# """
# Classifier for Document Content Types
# Valid types are 

# 1. Renewal
# 2. Cancellation
# 3. Invoice
# 
# """

class INSURANCE_DOCUMENT_TYPE(str, Enum):
    RENEWAL = "renewal"         # Renewal document type

class INSURANCE_POLICY_TYPE(str, Enum):
    WIND = "wind"
    HAZARD = "hazard"
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"

class INSURANCE_DOCUMENT_SOURCE(str, Enum):
    SOURCE_EDI  = "edi"
    SOURCE_EMAIL = "email"
    SOURCE_SCAN = "scan"

# --------------------------------------------------------------------------- #
# Root model for Information from various Documents (Renewal, Invoice, etc.)
# --------------------------------------------------------------------------- #

@dataclass
class LoanDocInfo(LoanModel):
    """
    Infoset representing information typically extracted from any Loan document.
    """
    document_number: str = ""
    document_type: str = ""
    document_print_date: str = ""
    
    borrower: str = ""
    co_borrower: str = ""
    loan_number: str = ""

    property_address: str = "" 
    property_address_1: str = ""
    property_address_2: str = ""
    property_city: str = ""
    property_state: str = ""
    property_zip: str = ""

    property_type: str = ""
    property_usage: str = ""

    policy_number: str = ""
    policy_type: str = ""

    # Order of the values in an instance string, e.g. "1298868 | John Doe | ABC1234 | hazard"
    STRING_FIELDS: ClassVar[tuple[str, ...]] = ("loan_number", "borrower", "policy_number", "policy_type")

    @classmethod
    def from_string(cls: Type[D], text: str) -> D:
        """Build an instance from a "|"-separated string whose values follow cls.STRING_FIELDS."""
        values = [v.strip() for v in text.split("|")]
        if len(values) != len(cls.STRING_FIELDS):
            raise ValueError(f"expected {len(cls.STRING_FIELDS)} values, got {len(values)}: {text.strip()}")
        return cls(**dict(zip(cls.STRING_FIELDS, values)))

D = TypeVar("D", bound=LoanDocInfo)

@dataclass
class RenewalDocInfo(LoanDocInfo):
    """
    Infoset representing information extracted from a policy Renewal document.
    Sample: renewal_doc_info.json
    """
    carrier_name: str = ""
    carrier_address: str = ""
    carrier_phone: str = ""
    carrier_email: str = ""

    payee_name: str = ""
    remit_to_name: str = ""
    remit_to_name_2: str = ""
    remit_to_address: str = ""
    chk_pay_agent: bool = False
    chk_mail_payment_to_agent: bool = False

    agent_name: str = ""
    agent_name_2: str = ""
    agent_address: str = ""
    agent_address_1: str = ""
    agent_address_2: str = ""
    agent_city: str = ""
    agent_state: str = ""
    agent_zip: str = ""
    agent_country: str = ""
    agent_email: str = ""
    agent_phone: str = ""
    agent_fax: str = ""

    effective_date: str = ""
    expiration_date: str = ""
    premium_due_date: str = ""
    earliest_cancellation_date: str = ""
    cancel_or_reinstate_date: str = ""
    policy_term: str = ""

    escrow_status: str = ""
    earliest_cancellation_or_reinstatement_reason: str = ""
    cancel_or_reinstate_reason: str = ""

    coverage_amount: float = 0.0
    premium_amount: float = 0.0
    additional_amount_due: float = 0.0
    deductible_amount: float = 0.0
    deductible_percentage: float = 0.0

    wind_excluded: bool = False
    wind_deductible_amount: float = 0.0
    wind_deductible_percentage: float = 0.0

    # Order of the values in an instance string, e.g. "ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025"
    STRING_FIELDS: ClassVar[tuple[str, ...]] = ("policy_number", "carrier_name", "effective_date", "expiration_date")

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def test_read_renewal_doc_info(path: Path = Path(__file__).parent / "renewal_docinfo.json") -> RenewalDocInfo:
    """Read renewal_doc_info.json into a RenewalDocInfo and verify every field round-trips."""
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text)
    doc = RenewalDocInfo.from_json(text)

    assert isinstance(doc, RenewalDocInfo)
    assert isinstance(doc, LoanDocInfo)

    field_names = {f.name for f in fields(RenewalDocInfo)}
    missing = set(raw) - field_names
    assert not missing, f"JSON keys not in RenewalDocInfo: {sorted(missing)}"

    for key, value in raw.items():
        assert getattr(doc, key) == value, f"{key}: expected {value!r}, got {getattr(doc, key)!r}"

    assert doc.to_dict() == raw
    print(f"PASS: {path.name} -> RenewalDocInfo ({len(raw)} fields)")
    return doc

def main() -> None:
    doc = test_read_renewal_doc_info()
    print(doc.to_json(indent=2))

if __name__ == "__main__":
    main()
