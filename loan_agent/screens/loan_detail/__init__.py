"""Section handlers for the Loan Details page (loan-detail-page.html); LoanDetailPage in
screens/loan_detail_page.py composes them.

    LoanInformation          loan-level header fields
    CollateralInformation    one per property, each with
      InsuranceLines           the line tabs, one InsuranceLineSection per line, each with
        Deficiencies             the line's deficiency table
    TransactionHistory, InsuranceDocument, Correspondence, Calls, LenderPlacedClaims, Comments   top tabs
"""
from .base import Section
from .collateral import CollateralInformation
from .deficiencies import Deficiencies, merge_deficiencies
from .insurance_line import InsuranceLines, InsuranceLineSection
from .loan_information import LoanInformation
from .tabs import (Calls, Comments, Correspondence, InsuranceDocument, LenderPlacedClaims, LoanTab,
                   TransactionHistory)

__all__ = [
    "Section", "LoanInformation", "CollateralInformation", "InsuranceLines", "InsuranceLineSection",
    "Deficiencies", "merge_deficiencies", "LoanTab", "TransactionHistory", "InsuranceDocument",
    "Correspondence", "Calls", "LenderPlacedClaims", "Comments",
]
