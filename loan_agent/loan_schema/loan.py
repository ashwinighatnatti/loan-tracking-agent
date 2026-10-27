"""Dataclass model for loan insurance documents (loan.json schema).

Usage:
    doc = Loan.from_json(open("loanv1.json").read())
    doc = Loan.from_dict(some_dict)
    print(doc.to_json(indent=2))
"""
from __future__ import annotations

import sys
import json
import types
import typing
import logging
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, ClassVar, Dict, List, Optional, Type, TypeVar, get_args, get_origin
from pathlib import Path

PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT_DIR) not in sys.path:
    sys.path.append(str(PROJECT_ROOT_DIR))

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper models
# --------------------------------------------------------------------------- #

T = TypeVar("T", bound="LoanModel")

class LoanModel:
    """Mixin giving every dataclass recursive from_dict / to_dict / JSON helpers."""

    # Source JSON key -> field name, for keys whose spelling differs from the field.
    KEY_ALIASES: ClassVar[Dict[str, str]] = {}

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Recursively build an instance from a dict. Unknown keys are logged and ignored,
        missing or null keys fall back to the dataclass default."""
        if data is None:
            data = {}
        data = {cls.KEY_ALIASES.get(k, k): v for k, v in data.items()}
        hints = typing.get_type_hints(cls)
        names = {f.name for f in fields(cls)}

        unknown = sorted(set(data) - names)
        if unknown:
            log.warning("%s: ignoring unknown keys %s", cls.__name__, unknown)

        kwargs: Dict[str, Any] = {}
        for f in fields(cls):
            if data.get(f.name) is not None:
                try:
                    kwargs[f.name] = _convert(hints[f.name], data[f.name])
                except ValueError as exc:
                    raise ValueError(f"{cls.__name__}.{f.name}: {exc}") from exc
        return cls(**kwargs)

    @classmethod
    def from_json(cls: Type[T], text: str) -> T:
        return cls.from_dict(json.loads(text))

    def to_dict(self) -> Dict[str, Any]:
        return {f.name: _to_plain(getattr(self, f.name)) for f in fields(self)}

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

_TRUE_STRINGS = {"true", "t", "yes", "y", "1", "on"}
_FALSE_STRINGS = {"false", "f", "no", "n", "0", "off", ""}

def _to_float(value: Any) -> float:
    """Accepts numbers and strings such as "$1,234.50" or "2%"; an empty string is 0.0."""
    if isinstance(value, str):
        text = value.replace(",", "").replace("$", "").replace("%", "").strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"not a number: {value!r}") from None
    return float(value)

def _to_bool(value: Any) -> bool:
    """Accepts bools, numbers and strings such as "Yes" / "N"."""
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in _TRUE_STRINGS:
            return True
        if text in _FALSE_STRINGS:
            return False
        raise ValueError(f"not a boolean: {value!r}")
    return bool(value)

def _convert(hint: Any, value: Any) -> Any:
    """Coerce a raw JSON value into the type described by `hint`."""
    if value is None:
        return None
    origin = get_origin(hint)
    if origin in (typing.Union, types.UnionType):  # Optional[X] or X | None
        inner = [a for a in get_args(hint) if a is not type(None)]
        return _convert(inner[0], value) if len(inner) == 1 else value
    if origin in (list, List):
        (item_type,) = get_args(hint) or (Any,)
        return [_convert(item_type, v) for v in value]
    if origin in (dict, Dict):
        return dict(value)
    if is_dataclass(hint) and isinstance(value, dict):
        return hint.from_dict(value)
    if hint is bool:
        return _to_bool(value)
    if hint is float:
        return _to_float(value)
    if hint is int and not isinstance(value, bool):
        return int(_to_float(value))
    if hint is str and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value

def _to_plain(value: Any) -> Any:
    if isinstance(value, LoanModel):
        return value.to_dict()
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_plain(v) for k, v in value.items()}
    return value

# --------------------------------------------------------------------------- #
# Data models representing information extracted from app for a Loan
# --------------------------------------------------------------------------- #

@dataclass
class Contact(LoanModel):
    type: str = ""
    name: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""

@dataclass
class Comment(LoanModel):
    datetime: str = ""
    type: str = ""
    text: str = ""

@dataclass
class Mortgagee(LoanModel):
    name: str = ""
    address_1: str = ""
    address_2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    other_names: List[str] = field(default_factory=list)

@dataclass
class Deficiency(LoanModel):
    title: str = ""
    flag: bool = False
    corrected: bool = False
    waived: bool = False

@dataclass
class InsuranceLine(LoanModel):
    line_id: str = ""
    line_type: str = ""
    policy_number: str = ""
    policy_type: str = ""
    linked_property_id: str = ""
    is_lender_placed: bool = False

    carrier_name: str = ""
    carrier_address: str = ""
    carrier_phone: str = ""
    carrier_global_payee_regular_mail_address: str = ""
    carrier_global_payee_overnight_mail_address: str = ""

    payee_name: str = ""
    remit_to_name: str = ""
    remit_to_name_2: str = ""
    remit_to_address: str = ""
    chk_pay_agent: bool = False
    chk_mail_payment_to_agent: bool = False

    agent_name: str = ""
    agent_name_2: str = ""
    agent_address_1: str = ""
    agent_address_2: str = ""
    agent_address: str = ""
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
    policy_term: str = ""

    escrow_status: str = ""
    earliest_cancellation_date: str = ""
    earliest_cancellation_or_reinstatement_reason: str = ""
    cancel_or_reinstate_date: str = ""
    cancel_or_reinstate_reason: str = ""

    coverage_amount: float = 0.0
    cert_flood_zone: str = ""
    no_replacement_coverage: bool = False
    deductible_amount: float = 0.0
    deductible_percentage: float = 0.0

    premium_amount: float = 0.0
    additional_amount_due: float = 0.0

    wind_excluded: bool = False
    wind_deductible_amount: float = 0.0
    wind_deductible_percentage: float = 0.0

    earthquake_excluded: bool = False
    earthquake_deductible: float = 0.0
    earthquake_deductible_percentage: float = 0.0

    last_payment_date: str = ""
    last_premium_amount: float = 0.0
    last_payee: str = ""
    last_cheque_info: str = ""
  
    chk_make_payment: bool = False
    chk_expedite_payment: bool = False
    chk_additional_amount_due: bool = False   
    chk_expedite_additional_amount_due: bool = False
    
    chk_funding_only: bool = False
    chk_issue_manual_check_for_additional_due: str = ""
    funding_only_comment: str = ""

    note_comments: List[Comment] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    deficiencies: List[Deficiency] = field(default_factory=list)    # the Loan Details page shows them per line

    # Order of the values in an instance string, e.g. "ABC1234 | ABC Carrier | 1/1/2025 | 12/31/2025"
    STRING_FIELDS: ClassVar[tuple[str, ...]] = ("policy_number", "carrier_name", "effective_date", "expiration_date")

    @classmethod
    def from_string(cls, text: str) -> InsuranceLine:
        """Build an instance from "policy | carrier | effective | expiration" (see STRING_FIELDS)."""
        values = [v.strip() for v in text.split("|")]
        if len(values) != len(cls.STRING_FIELDS):
            raise ValueError(f"expected {len(cls.STRING_FIELDS)} values, got {len(values)}: {text.strip()}")
        return cls(**dict(zip(cls.STRING_FIELDS, values)))

    @property
    def term(self):
        """The policy term from effective_date / expiration_date, as a tools.Term."""
        from loan_agent.tools.tools import Term   # imported here so the schema loads without the tools dependencies
        return Term(self.effective_date, self.expiration_date)

@dataclass
class Collateral(LoanModel):
    property_id: str = ""
    property_line_type: str = ""
    property_info: str = ""
    property_description: str = ""
    property_type: str = ""
    property_usage: str = ""
    occupancy_status: str = ""
    property_status: str = ""
    number_of_property: str = ""
    property_address_1: str = ""
    city: str = ""
    state: str = ""
    zip: str =""
    property_address: str = ""
    appraised_value: float = 0.0
    lien_position: str = ""
    flood_zone: str = ""
    flood_waiver: str = ""
    flood_required: str = ""
    loma_on_file: str = ""
    flood_determination_date: str = ""
    insurable_value: float = 0.0
    actual_cash_value: float = 0.0
    required_hazard_coverage: float = 0.0
    required_flood_coverage: float = 0.0
    required_earthquake_coverage: float = 0.0
    grandfathered: bool = False
    chk_track_only: bool = False
    insurance_lines: List[InsuranceLine] = field(default_factory=list)

@dataclass
class Loan(LoanModel):

    KEY_ALIASES: ClassVar[Dict[str, str]] = {"committment_amount": "commitment_amount"}   # misspelled in the source JSON

    loan_number: str = ""
    primary_borrower: str = ""
    co_borrower: str = ""

    loan_type: str = ""
    govt_loan_type: str = ""
    escrow_status: str = ""
    loan_origination_method: str = ""
    original_balance: float = 0.0
    upb: float = 0.0
    commitment_amount: float = 0.0

    closing_date: str = ""
    created_date: str = ""
    date_of_note: str = ""
    loan_originated: str = ""
    loan_reported_to_app: str = ""
    maturity_date: str = ""

    branch: str = ""
    investor_code: str = ""
    organization: str = ""
    officer_code: str = ""
    client_system: str = ""
    asset_manager: str = ""

    contacts: List[Contact] = field(default_factory=list)
    comments: List[Comment] = field(default_factory=list)
    mortgagee: List[Mortgagee] = field(default_factory=list)
    collateral: List[Collateral] = field(default_factory=list)
    deficiencies: List[Deficiency] = field(default_factory=list)

def _run_load_json_test():

    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "loan.json"
    with open(path) as fh:
        doc = Loan.from_json(fh.read())
    # print(doc.to_json())
    print(f"Collateral lines {len(doc.collateral[0].insurance_lines)}")


# --------------------------------------------------------------------------- #
# Main for testing
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    _run_load_json_test()
