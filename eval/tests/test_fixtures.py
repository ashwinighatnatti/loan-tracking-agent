"""The clean and bait fixtures must actually be correct, or the false-positive metric is meaningless."""
import importlib.util
import sys
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def load(rel):
    spec = importlib.util.spec_from_file_location(Path(rel).stem, FIX / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve string annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_escrow_fixed():
    m = load("clean/escrow_fixed.py")
    assert [m.is_escrow(v) for v in ("Y", "yes", " N ", "", None, "maybe")] == [True, True, False, None, None, None]
    assert m.payment_decision("Y", 90) == "prepare_payment"
    assert m.payment_decision("Yes", 90) == "prepare_payment"
    assert m.payment_decision("N", 90) == "no_payment"
    assert m.payment_decision("Y", 30) == "no_payment"
    assert m.payment_decision("", 90) == "needs_human"


def test_closing_rule_fixed():
    f = load("clean/closing_rule_fixed.py").payment_blocked_by_closing
    assert f("01/01/2026", "01/11/2026") is True      # 10 days after closing
    assert f("01/01/2026", "03/01/2026") is True      # 59 days
    assert f("01/01/2026", "03/02/2026") is False     # 60 days
    assert f("01/31/2026", "01/01/2026") is False     # effective BEFORE closing is not "just closed"
    assert f("", "01/01/2026") is None and f("01/01/2026", "2/30/2026") is None


def test_loan_link_fixed():
    m = load("clean/loan_link_fixed.py")
    recs = [m.LoanRecord("1", "A SMITH", "10 MAIN ST"), m.LoanRecord("2", "A SMITH", "110 MAIN ST")]
    same = lambda a, b: a == b
    assert m.link("A SMITH", "10 MAIN ST", recs, same, same)[0] == "matched"
    assert m.link("A SMITH", "9 MAIN ST", recs, same, same)[0] == "no_match"
    assert m.link("A SMITH", "x", recs, same, lambda a, b: True)[0] == "ambiguous"


def test_intake_getout():
    m = load("clean/intake_getout.py")
    ok = {"property_address": "1 A St", "effective_date": "1/1/2026", "expiration_date": "1/1/2027"}
    assert m.intake(ok).status == "proceed"
    out = m.intake({"property_address": "", "effective_date": "1/1/2026"})
    assert out.status == "edit" and "property_address" in out.reason and "expiration_date" in out.reason


def test_bait_fixtures_behave():
    s = load("bait/style_only.py")
    assert s.prem_close_enough(10.0, 10.9) and s.prem_close_enough(10.9, 10.0) and not s.prem_close_enough(10, 12)
    assert s.fmt(123) == "123"
    u = load("bait/validated_upstream.py")
    assert u.intake_policy({"policy_number": " ab-12 "}) == "AB12"
    assert u.intake_policy({"policy_number": ""}) is None and u.intake_policy({}) is None
    assert u.intake_policy({"policy_number": "---"}) is None and u.intake_policy({"policy_number": "/ /"}) is None
