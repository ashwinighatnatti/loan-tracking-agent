import logging
from pathlib import Path

import pytest

from loan_agent.loan_schema.loan import Collateral, Loan

LOAN_JSON = Path(__file__).resolve().parent.parent / "loan_agent" / "loan_schema" / "loan.json"


@pytest.mark.parametrize("raw, expected", [
    ("1,234.50", 1234.5),
    ("$500", 500.0),
    ("", 0.0),
    (7, 7.0),
])
def test_float_fields_accept_numeric_strings(raw, expected):
    assert Loan.from_dict({"upb": raw}).upb == expected


def test_bad_number_names_the_field():
    with pytest.raises(ValueError, match="Loan.upb"):
        Loan.from_dict({"upb": "N/A"})


@pytest.mark.parametrize("raw, expected", [
    ("false", False), ("N", False), ("", False), (0, False),
    ("true", True), ("Yes", True), ("y", True), (1, True),
])
def test_bool_fields_accept_strings(raw, expected):
    assert Collateral.from_dict({"grandfathered": raw}).grandfathered is expected


def test_bad_bool_names_the_field():
    with pytest.raises(ValueError, match="Collateral.grandfathered"):
        Collateral.from_dict({"grandfathered": "maybe"})


def test_null_uses_the_default():
    assert Loan.from_dict({"loan_number": None, "upb": None}).loan_number == ""


def test_unknown_keys_are_logged(caplog):
    with caplog.at_level(logging.WARNING):
        Loan.from_dict({"loan_numbr": "123"})
    assert "loan_numbr" in caplog.text


def test_misspelled_source_key_is_aliased():
    loan = Loan.from_dict({"committment_amount": "250000"})
    assert loan.commitment_amount == 250000.0
    assert "commitment_amount" in loan.to_dict()


def test_collateral_state_and_zip():
    c = Collateral(state="NJ", zip="07002")
    assert (c.state, c.zip) == ("NJ", "07002")
    assert (Collateral().state, Collateral().zip) == ("", "")


def test_loan_json_round_trip():
    loan = Loan.from_json(LOAN_JSON.read_text())
    assert Loan.from_dict(loan.to_dict()) == loan
    assert loan.collateral[0].insurance_lines[0].term is not None
