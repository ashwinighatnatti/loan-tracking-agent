"""
Run rules

1. get a loan json by invoking api endpoint /loan/<loan_number> with a loan_number
2. load the returned json in to Loan object
3. get a case json by invoking the api endpoint /case/<doc-number> with a document_number
4. load the returned json into a RenewalDocInfo object
5. with Loan and RenewalDocInfo objects run the method process_document in the file line_rules.py
6. caputure the returned LineResult instance
7. save its ouput to a file. take filename as the unique execid from the LineResult object. save with extension .txt

Not a pytest module (needs the mock API running), so it is not collected by pytest.

python loan_agent/mocks/api/server.py --port 9191
python tests/run_rules.py <loan_number> <document_number> [--base-url URL] [--out-dir DIR]

# -- RUN this script from loan-tracking-agent
python tests/run_rules.py 0520359554 8202026950003648249
python -m tests.run_rules 0520359554 8202026950003648249
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote

# Make the project root importable when this file is run directly as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from loan_agent.loan_schema.loan import Loan
from loan_agent.loan_schema.loan_docinfo import RenewalDocInfo
from loan_agent.rules.line_rules import LineResult, process_document

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:9191"      # mock API server (loan_agent/mocks/api/server.py)


def get_json(base_url: str, path: str, timeout: float = 30) -> Dict[str, Any]:
    """GETs <base_url>/<path> and returns the decoded JSON body. Raises urllib.error.HTTPError on a non-2xx status."""
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    log.info("GET %s", url)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_loan(base_url: str, loan_number: str) -> Loan:
    """Steps 1-2: GET /loan/<loan_number> and load it into a Loan."""
    return Loan.from_dict(get_json(base_url, f"/loan/{quote(loan_number)}"))


def fetch_case(base_url: str, document_number: str) -> RenewalDocInfo:
    """Steps 3-4: GET /case/<document_number> and load it into a RenewalDocInfo."""
    doc = RenewalDocInfo.from_dict(get_json(base_url, f"/case/{quote(document_number)}"))
    if not doc.document_number:
        doc.document_number = document_number        # case.json may leave it blank; execid is derived from it
    return doc


def run_rules(loan_number: str, document_number: str, base_url: str = DEFAULT_BASE_URL,
              out_dir: str = ".") -> Path:
    """Runs process_document for the loan and case and saves the LineResult to <out_dir>/<execid>.txt.
    Returns the path written."""
    loan = fetch_loan(base_url, loan_number)
    doc = fetch_case(base_url, document_number)

    result: LineResult = process_document(loan, doc)    # steps 5-6

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{result.execid}.txt"                  # step 7
    result.save_json(str(path))
    log.info("Saved result to %s", path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run line rules for a loan and a case document.")
    parser.add_argument("loan_number", help="loan number, used for /loan/<loan_number>")
    parser.add_argument("document_number", help="document number, used for /case/<document_number>")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base url (default {DEFAULT_BASE_URL})")
    parser.add_argument("--out-dir", default=".", help="directory for the <execid>.txt output (default: cwd)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(run_rules(args.loan_number, args.document_number, args.base_url, args.out_dir))


if __name__ == "__main__":
    main()
