from loan_agent.screens.loan_search_page import LoanRecord, LoanSearchCriteria, LoanSearchPage
from loan_agent.screens.document_search_page import DocumentRecord, DocumentSearchCriteria, DocumentSearchPage
from loan_agent.rules.line_rules import process_document

from google.adk.agents.llm_agent import Agent
from .prompt import LOAN_TRACKING_INSTRUCTION

#================================================
# Agent definition
#================================================

MODEL = "google.gemini..."

root_agent = Agent(
    model=MODEL,
    name='loan-tracking-agent',
    description='Process policy documents into app',
    instruction=LOAN_TRACKING_INSTRUCTION,
    tools = [
            process_document,
        ]
)

