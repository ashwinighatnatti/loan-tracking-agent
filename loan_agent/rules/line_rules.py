"""Rules that compare the insurance line on file (iim) with the one on an incoming document (doc)."""
from __future__ import annotations

import logging
from dataclasses import InitVar, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loan_agent.loan_schema.loan import LoanModel, Loan, Collateral, InsuranceLine, Comment, Deficiency
from loan_agent.loan_schema.loan_docinfo import LoanDocInfo, RenewalDocInfo, INSURANCE_DOCUMENT_SOURCE, INSURANCE_DOCUMENT_TYPE, INSURANCE_POLICY_TYPE

from loan_agent.tools import utils
from loan_agent.tools.tools import Term, within_60_120_threshold

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Action(LoanModel):
    case: str
    status: str
    comment: str = ""


#=== Closing action for a document, keyed by ( case, status, default comment)

FINAL_ACTIONS: Dict[Tuple[str, str], Action] = {
    ("done", "aof"):                 Action("Done", "Complete", "Already On File"),
    ("done", "complete"):            Action("Done", "Complete", "Processed"),
    ("done", "not-tracked"):         Action("Done", "Not Tracked", "Not tracked"),
    ("done", "paid-in-full"):        Action("Done", "Paid In full", "Paid in full"),
    ("done", "policy-not-accepted"): Action("Done", "Policy Not Accepted", "Old policy"),
    ("done", "sold"):                Action("Done", "Sold", "sold"),
    ("edit", "tbp"):                 Action("Edit", "To Be Processed", "reason"),
}

# Used when the case is known but the status is not.
FINAL_DEFAULTS: Dict[str, Action] = {
    "done": Action("Done", "Complete", "unknown reason"),
    "edit": Action("Edit", "To Be Processed", "unknown reason"),
}


def make_action(verdict: Tuple[str, str, str]) -> Optional[Action]:
    """Takes final_result as (case, status, reason) and returns the closing action for (case, status), the case default
    for an unknown status, or None for an unknown case. Case and status are FINAL_ACTIONS keys, e.g. ("done", "not-tracked").
    A non-empty `reason` replaces the action's default comment."""
    case, status, reason = verdict
    action = FINAL_ACTIONS.get((case, status), FINAL_DEFAULTS.get(case))
    if action and reason:
        return replace(action, comment=reason)     # copy: table actions are shared and frozen
    return action


@dataclass
class LineResult(LoanModel):
    line: InsuranceLine
    execid: str = ""
    comments: List[Comment] = field(default_factory=list)
    deficiencies: List[Deficiency] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    flags: Dict[str, Any] = field(default_factory=dict)
    doc: InitVar[Optional[LoanDocInfo]] = None

    def __post_init__(self, doc: Optional[LoanDocInfo]) -> None:
        if not self.execid:
            self.execid = utils.generate_uniq_id(doc.document_number if doc else "0000")

    def save_json(self, path: str) -> None:
        """Writes the result (line, comments, deficiencies, actions and flags) to `path` as JSON."""
        Path(path).write_text(self.to_json(), encoding="utf-8")


def find_collateral(loan: Loan, property_address: str) -> Optional[Collateral]:
    """Returns the first collateral whose property_address matches (ignoring case, spacing and punctuation), or None."""

    for collateral in loan.collateral:
        if utils.same_address(collateral.property_address, property_address):
            return collateral
    return None


def find_insurance_line(collateral: Collateral, policy_type: str) -> Optional[InsuranceLine]:
    """Returns the first insurance line on the collateral whose policy_type matches (ignoring case and spacing), or None."""
    for line in collateral.insurance_lines:
        if utils.safe_compare(line.policy_type, policy_type):
            return line
    return None


def make_new_insurance_line(doc: LoanDocInfo, escrow: str, result: LineResult) -> None:
    """when collateral does not have an insurance line of the policy_type, we make a new insurance line by copying the information from document into the line property in result"""
    line = result.line

    #- fill in all the values from the document
    line.line_id="#06#"
    if isinstance(doc, RenewalDocInfo):
        # policy
        line.policy_number = doc.policy_number
        line.policy_type = doc.policy_type
        # carrier
        line.carrier_name = doc.carrier_name
        line.carrier_address = doc.carrier_address
        line.carrier_phone = doc.carrier_phone
        # agent payee (carrier)
        if len(doc.payee_name) > 0:
            line.chk_pay_agent = doc.chk_pay_agent
            line.chk_mail_payment_to_agent = doc.chk_mail_payment_to_agent
            line.payee_name = doc.payee_name
            line.remit_to_name = doc.remit_to_name
            line.remit_to_name_2 = doc.remit_to_name_2
            line.remit_to_address = doc.remit_to_address
        # agent 
        line.agent_name = doc.agent_name
        line.agent_name_2 = doc.agent_name_2
        line.agent_address_1 = doc.agent_address_1
        line.agent_address_2 = doc.agent_address_2
        line.agent_address = doc.agent_address
        line.agent_city = doc.agent_city
        line.agent_state = doc.agent_state
        line.agent_zip = doc.agent_zip
        line.agent_country = doc.agent_country
        line.agent_email = doc.agent_email
        line.agent_phone = doc.agent_phone
        line.agent_fax = doc.agent_fax

        # dates
        line.escrow_status = escrow  # v.imp
        line.effective_date = doc.effective_date
        line.expiration_date = doc.expiration_date
        line.premium_due_date = doc.premium_due_date
        line.policy_term = doc.policy_term
        line.earliest_cancellation_date = doc.expiration_date

        # amounts
        line.coverage_amount = doc.coverage_amount
        line.deductible_amount = doc.deductible_amount
        line.deductible_percentage = doc.deductible_percentage

        line.wind_excluded = doc.wind_excluded
        if not doc.wind_excluded: 
            line.wind_deductible_amount = doc.wind_deductible_amount
            line.wind_deductible_percentage = doc.wind_deductible_percentage

        # premiums & dues
        line.premium_amount = doc.premium_amount
        line.additional_amount_due = 0

    return None


def process_line(line: InsuranceLine, doc: LoanDocInfo, result: LineResult) -> None:
    """Compares the line on file with the doc and records the scenario flags (JSON-ready dict) on `result`."""

    #=== start processing line

    same_carrier = utils.safe_compare(line.carrier_name, doc.carrier_name)
    same_policy = utils.safe_compare(line.policy_number, doc.policy_number)

    doc_term = Term(doc.effective_date, doc.expiration_date)
    same_renewal_term = line.term.is_renewal_term(doc_term)
    term_relation = line.term.compare(doc_term)

    case_same_year = Term.Relation.EQUAL == term_relation and same_carrier and same_policy      # case: Already On File (AOF)
    case_old_policy = Term.Relation.FUTURE == term_relation                                     # case: PNA - Old Policy

    #=== Determine processing scenario
    
    case_renewal = same_renewal_term and same_carrier and same_policy
    case_rewrite = same_renewal_term and same_carrier and not same_policy
    case_extended_rewrite = Term.Relation.REXTEND == term_relation and same_carrier and not same_policy

    case_nubiz = same_renewal_term and not same_carrier and not same_policy
    case_midterm = Term.Relation.REXTEND == term_relation and not same_carrier and not same_policy


    resline = result.line

    resline.line_id = "#08#"
    resline.effective_date = "12/24/2026"  #= tmp fix

    if case_renewal:
        pass

    if case_rewrite:
        pass

    if case_extended_rewrite:
        pass

    if case_midterm:
        pass

    if case_nubiz:
        pass 


    result.flags = {
        "same_carrier": same_carrier,
        "same_policy": same_policy,
        "same_renewal_term": same_renewal_term,
        "term_relation": term_relation.value,
        "case_same_year": case_same_year,
        "case_old_policy": case_old_policy,
        "case_renewal": case_renewal,
        "case_rewrite": case_rewrite,
        "case_extended_rewrite": case_extended_rewrite,
        "case_nubiz": case_nubiz,
        "case_midterm": case_midterm,
    }


def process_document(iim: Loan, doc: LoanDocInfo) -> LineResult:
    """ 
    process_document takes two parameters 1. Loan information as a Loan object and 2. LoanDocInfo object representing 
    information extracted from the policy pdf document.
    
    Returns a LineResult object containing
        - New Insurance Line
        - Comments to be added to the Loan
        - Deficiencies to be marked or unmarked
        - Action to be done with status and comment
        - Flags indicating various scenario
    """

    #=== global status and result of processing

    result = LineResult(InsuranceLine(), doc=doc)           # create a LineResult. pass and empty InsuranceLine and doc
    
    #=== first checks before processing 

    if utils.has_lender_placed_suffix(doc.policy_number):
        result.actions.append(make_action(("done", "not-tracked", "Prior servicer LP on file")))
        return result

    #=== Loan and Document level checks

        #- todo:
        #- check california fair plan
        #- make a new Hazard line for such renewals
        #- summarize comments on Loan

    #=== find the exact collateral and insurance line type (wind, hazard etc) as per doc
    
    collateral = find_collateral(iim, doc.property_address)
    if collateral is None:
        raise ValueError(f"No collateral matches property address {doc.property_address!r}")

    collateral_line = find_insurance_line(collateral, doc.policy_type)


    #=== result.line always contains the line to be `merged` into Loan

    if collateral_line is None:
        make_new_insurance_line(doc, iim.escrow_status, result)
    else:
        process_line(collateral_line, doc, result)


    line = result.line      #= the line we created



    #=== prepare payment

    just_closed = 0 <= utils.days_between(iim.closing_date, doc.effective_date) < 60
    threshold_60_120 = within_60_120_threshold(line.effective_date)
    escrow = line.escrow_status == "Yes"

    if just_closed:
        result.actions.append(make_action("done", "complete", "Less than 60 days since closing date"))

    if escrow and threshold_60_120:
        result.line.chk_make_payment = True

        #=== check deficiency

        # MCC Deficiency
        # MidTerm Deficiency
        # Deductible Deficiency

    #=== complete the document
    


    return result
