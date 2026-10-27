#!/usr/bin/env python3
"""
General Document Processing Multi-Agent System

Domain-independent document processing pipeline with configurable validation rules.
Each agent produces intermediate artifacts stored in output/{document_id}/

Version: 1.0.0

Usage:
    python general_acting_agent.py --base-dir path/to/documents
    python general_acting_agent.py --case path/to/single/case
    python general_acting_agent.py --base-dir path/to/documents --config config.json

Output:
    All outputs are saved in the SCRIPT DIRECTORY (not current working directory):
    general-acting-agent/
    └── output/
        └── {document_id}/
            ├── 01_classification.json
            ├── 02_extraction.json
            ├── ...
            └── Postprocessing_Data.json

Note:
    - Outputs go to script's folder regardless of where you run it from
    - Config files are resolved relative to script directory if not absolute
    - .env file is loaded from script directory first
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from loan_agent.loan_schema.loan import LoanDocInfo

# Third-party imports
try:
    import pdfplumber
    from dotenv import load_dotenv

except ImportError:
    print("Error: Missing required package. Install with:")
    print(
        "pip install  pydantic pdfplumber python-dotenv"
    )
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Resolve paths: acting/ -> libs/ -> loan_agent/ (package root with data/ inside)
SCRIPT_DIR = Path(__file__).resolve().parent
AGENT_PKG_DIR = SCRIPT_DIR.parent.parent
OUTPUT_BASE_DIR = AGENT_PKG_DIR / "data" / "agent_output"

_PHASE_OUTPUT_LOG: dict[str: Any] = {
   "BASE": {
        "total_stages": 0
    }
}

# Project root for .env resolution
PROJECT_ROOT = AGENT_PKG_DIR.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()  # Fallback to default behavior

# Magic-value constants
_MIN_PDF_CONTENT_LENGTH = 50

# ============================================================================
# Helper functions
# ============================================================================

def append_phase_output_log(phase: str, values: Any):
    _PHASE_OUTPUT_LOG[phase] = values


def _call_model(prompt: str, model_name: str, output_schema: LoanDocInfo) -> tuple[LoanDocInfo, Any]:
    """Call the model and parse output into the specified Pydantic schema"""

    # Placeholder for actual model call logic
    # This function should implement the logic to call the model
    # and return the parsed output as an instance of output_schema.

    raise NotImplementedError("Model call logic is not implemented.")


# ============================================================================
# BASE AGENT CLASS
# ============================================================================

class BaseAgent(ABC):
    """Base class for all agents"""

    def __init__(self, name: str, version: str = "1.0"):
        self.name = name
        self.version = version

    def create_output(
        self, data: dict, input_refs: list[str] | None = None
    ) -> dict:
        """Wrap agent output with metadata"""
        return {
            "agent": self.name,
            "version": self.version,
            "timestamp": datetime.now().isoformat(),
            "input_refs": input_refs or [],
            **data,
        }

    def save_artifact(
        self, output_folder: Path, filename: str, data: dict
    ) -> Path:
        """Save artifact to output folder"""
        output_file = output_folder / filename
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  => Saved: {filename}")
        return output_file

    @abstractmethod
    def run(self, *args, **kwargs) -> dict:
        """Execute the agent logic"""
        pass

# ============================================================================
# AGENT 1: CLASSIFIER
# ============================================================================

class ClassifierAgent(BaseAgent):
    """Document Classification Agent"""

    def __init__(self):
        super().__init__("classifier")

    def run(self, source_folder: Path, output_folder: Path) -> dict:

        if file_path.suffix.lower() == ".pdf":
            content, method = extract_pdf_with_fallback(file_path)

            # Analyze content
            doc_info = self._analyze_document(content, file_path.name)

        elif file_path.suffix.lower() == ".json":
            files_info[file_path.name] = {"type": "json"}
        else file_path.suffix.lower() == ".jpeg":
            # Analyze content
            doc_info = self._analyze_document(content, file_path.name)

        return output

    def _analyze_document(self, content: str, filename: str) -> LoanDocInfo:
        """Analyze document content to identify type"""
        prompt = f"""Analyze this document and identify what types are present.

DOCUMENT CONTENT:
{content[:8000]}

INVOICE INDICATORS:
- Invoice number field
- Line items table with amounts
- Total amounts (subtotal, tax, total)
- Vendor business details and tax ID

RENEWAL INDICATORS:
- xx
- yy

CANCELLATION INDICATORS:
- xx
- yy

Return ONLY this JSON:
{{
  "has_renewal": true/false,
  "has_renewal": true/false,
  "has_cancellation": true/false,
}}"""

        try:
            result, _ = call_model( prompt, MODEL, DocumentContent )
            )
            return result
        except Exception as e:
            print(f"    Warning: Document analysis failed: {e}")
            # Fallback to keyword detection
            content_lower = content.lower()
            return DocumentContent(
                has_invoice="invoice" in content_lower,
                has_renewal="renewal" in content_lower,
                has_cancellation="cancellation" in content_lower,
                reasoning="Keyword fallback",
            )


# ============================================================================
# AGENT 2: EXTRACTOR
# ============================================================================

class ExtractorAgent(BaseAgent):
    """Document Extraction Agent"""

    def __init__(self):
        super().__init__("extractor")

    def run(
        self, source_folder: Path, output_folder: Path, classification: dict
    ) -> dict:

        document_type = classification.get("document_type", {})
        document_sources = classification.get("document_url", [])


        
        if document_type = "RENEWAL":
            
            try:
                invoice_data = self._extract_r(Path(source["full_path"]))

                print(
                    f"   Extracted invoice: {invoice_data.get('invoice_number', 'N/A')}"
                )
            except Exception as e:
                extraction_failed = True
                extraction_error = str(e)
                invoice_data = self._empty_invoice()
            else:
                extraction_failed = True
                extraction_error = "No invoice found"
                invoice_data = self._empty_invoice()
        elif document_type = "INVOICE":
            pass
        else:    
            pass

        return output

    def _extract_renewal(self, pdf_path: Path) -> RenewalDocInfo:
        """Extract structured renewal data from PDF"""
        prompt = """Extract structured data from this invoice PDF.

Return ONLY valid JSON with these fields:
{
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "invoice_total_inc_tax": decimal,
  "invoice_total_ex_tax": decimal,
  "tax_amount": decimal,
  "vendor_tax_id": "string (tax ID/ABN)",
  "vendor_name": "string",
  "customer_name": "string (who invoice is addressed to)",
  "currency": "AUD/USD/EUR/etc",
  "line_items": [
    {
      "description": "string",
      "quantity": decimal or null,
      "unit_price": decimal or null,
      "amount_ex_tax": decimal,
      "tax_code": "TAX/GST/NA",
      "tax_amount": decimal or null
    }
  ]
}

Extract ALL line items. Use null for missing optional fields."""

        result, _ = call_model_with_pdf(
            pdf_path, prompt, _llm_config.PRO_MODEL, RenewalDocInfo
        )
        return result.model_dump()

    def _extract_invoice(self, pdf_path: Path) -> InvoiceDocInfo:
        """Extract work authorization data from PDF"""
        prompt = """Extract work authorization data from this PDF.

Return ONLY valid JSON:
{
  "reference_number": "string or null",
  "site_name": "string or null",
  "authorized_hours": decimal or null,
  "work_description": "string or null",
  "technician_name": "string or null",
  "date": "YYYY-MM-DD or null"
}"""

        result, _ = _call_model_with_pdf(
            pdf_path,
            prompt,
            _llm_config.PRO_MODEL,
            InvoiceDocInfo,
        )
        return result.model_dump()


# ============================================================================
# AGENT 3: PHASE1 VALIDATOR
# ============================================================================
class Phase1ValidatorAgent(BaseAgent):

    """
    Goto LoanSearchPage
    
    With LoanSearchPage 
        Do Match Name and Address
        Do Advanced Search
    """


# ============================================================================
# AGENT 4: PHASE2 VALIDATOR
# ============================================================================
class Phase2ValidatorAgent(BaseAgent):

    """
    Goto LoanPage
    
    With LoanDetailsPage
        Retrieve Informaton  from LoanPage
    """

    def run():
        
        loanpage = LoanPage()

        loanpage.gotopage("")

        app = loanpage.get_data()



    