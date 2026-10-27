"""Scrapes mocks/loan-detail-page.html with Playwright: the built-in sample loan, and a two-collateral loan
served to the page's Loan API through a Playwright route (no mock server needed)."""
import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import Error as PlaywrightError, sync_playwright

from loan_agent.screens.loan_detail_page import LoanDetailPage

ROOT = Path(__file__).resolve().parent.parent / "loan_agent"
PAGE_URL = (ROOT / "mocks" / "loan-detail-page.html").as_uri()
LOAN_JSON = ROOT / "loan_schema" / "loan.json"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def screen(browser):
    context = browser.new_context()
    page = context.new_page()
    s = LoanDetailPage(url=PAGE_URL)
    s.attach(page)
    yield s
    context.close()


def open_page(screen, url=PAGE_URL):
    screen.page.goto(url)
    screen.page.wait_for_selector(screen.PAGE)


def two_collateral_loan():
    loan = json.loads(LOAN_JSON.read_text())
    second = copy.deepcopy(loan["collateral"][0])
    second.update(property_id="99999999", property_info="22 SECOND ST", property_address_1="22 SECOND ST",
                  city="JERSEY CITY", zip="07304")
    second["insurance_lines"] = [dict(second["insurance_lines"][0], line_id="11111111", line_type="Flood")]
    loan["collateral"].append(second)
    loan["deficiencies"] = [{"title": "Name Insured", "flag": True, "corrected": False, "waived": False}]
    return loan


def test_scrapes_sample_loan(screen):
    open_page(screen)
    loan = screen.scrape()

    assert loan.loan_number == "7750646441"
    assert loan.primary_borrower == "OWEN C ASHBY"
    assert loan.branch == "PQ"
    assert loan.original_balance == 319999.0
    assert loan.maturity_date == "10/01/2049"

    (collateral,) = loan.collateral
    assert collateral.property_address == "21 BIRCHWOOD CT BAYONNE, NJ 07002"
    assert collateral.appraised_value == 399999.0

    hazard, wind = collateral.insurance_lines
    assert (hazard.line_type, hazard.line_id, hazard.policy_number) == ("Hazard", "85160742", "KAUY290374")
    assert hazard.policy_type == "Hazard"
    assert hazard.linked_property_id == collateral.property_id
    assert hazard.carrier_address == "PO Box 44000, Dayton, OH 45401-4400 US"
    assert hazard.carrier_phone == "(800) 555-0142"
    assert hazard.effective_date == "09/13/2025"
    assert hazard.escrow_status == "Y"
    assert len(hazard.warnings) == 3

    # The Wind panel is hidden behind its tab but still read
    assert (wind.line_type, wind.policy_number) == ("Wind", "LEWD660169")
    assert wind.wind_deductible_percentage == 2.0
    assert {d.title for d in wind.deficiencies if d.flag} == {"Deductible"}

    assert {d.title for d in loan.deficiencies if d.flag} == {"Deductible"}
    assert len(loan.comments) == 9
    assert loan.comments[0].datetime == "06/28/2024 2:47 PM"
    assert loan.comments[2].type == "Call"


def test_scrapes_every_collateral_from_api(screen):
    screen.page.route("**/loan/1111111111", lambda route: route.fulfill(json=two_collateral_loan()))
    open_page(screen, PAGE_URL + "?loan-number=1111111111")
    screen.wait_for_loan()
    loan = screen.scrape()

    assert [c.property_id for c in loan.collateral] == ["21433117", "99999999"]
    first, second = loan.collateral
    assert [l.line_id for l in first.insurance_lines] == ["85160742", "16052182"]
    assert [(l.line_type, l.linked_property_id) for l in second.insurance_lines] == [("Flood", "99999999")]
    assert second.city == "JERSEY CITY"
    assert {d.title for d in loan.deficiencies if d.flag} == {"Name Insured"}
    assert loan.comments[0].text.startswith("Insurance paymnet for line id 40524685")


def test_writes_back_to_an_insurance_line(screen):
    open_page(screen)
    wind = screen.collateral.insurance_lines.select_line(line_type="wind")
    wind.set_fields({"policy_number": "NEW123", "effective_date": "10/01/2026", "chk_pay_agent": True})
    wind.deficiencies.mark("Mortgagee Clause", True, status="Waived")
    wind.add_comment("Renewal received", comment_type="Payment")

    line = wind.read()
    assert (line.policy_number, line.effective_date, line.chk_pay_agent) == ("NEW123", "10/01/2026", True)
    mortgagee = next(d for d in line.deficiencies if d.title == "Mortgagee Clause")
    assert (mortgagee.flag, mortgagee.waived, mortgagee.corrected) == (True, True, False)
    assert wind.field("loan_comment").input_value() == "Renewal received"

    wind.save()
    assert screen.page.locator("body").get_attribute("data-last-action") == "wind-line-btn-save-insurance-line"
