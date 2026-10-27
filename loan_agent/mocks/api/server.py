"""
Mock API Server
---------------
Serves mock loan-tracking data from disk (see README.md / openapi.yaml).

Endpoints:
  GET /search                       -> rows of <data-dir>/doc-search-results.csv as JSON
  GET /properties                   -> rows of <data-dir>/properties.csv as JSON
  GET /carriers                     -> rows of <data-dir>/carriers.csv as JSON
  GET /agents                       -> rows of <data-dir>/agents.csv as JSON
  GET /payees                       -> rows of <data-dir>/payees.csv as JSON
  GET /pdf/<document_number>       -> <data-dir>/<document_number>/case.pdf
  GET /loan/<loan_number>           -> <data-dir>/loan-<loan_number>.json
  GET /case/<document_number>       -> <data-dir>/<document_number>/case.json
  GET /ocr/<document_number>        -> <data-dir>/<document_number>/case.ocr as a JSON object (keys renamed via OCR_KEYS)
  GET /openapi.yaml                 -> this API's OpenAPI spec

.csv files are returned as a JSON array of row objects; rows whose first field
is empty are skipped. doc-search-results.csv is comma-delimited, the others are
pipe-delimited. On the CSV list endpoints (/search, /properties, /carriers,
/agents, /payees) any query parameter named after a column filters rows by
case-insensitive exact match, e.g. /properties?loan_number=97894.

Run:
  pip install flask
  python server.py                        # http://localhost:9191
  python server.py --port 8080 --data-dir /path/to/data
"""
import argparse
import csv
import json
import os
import re

from flask import Flask, jsonify, request, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEARCH_FILE = "doc-search-results.csv"

# Resource name -> candidate file names in <data-dir>/<document_number>/, in
# order of preference. Alternates cover singular/plural naming on disk.
RESOURCE_FILES = {
    "case": ["case.json"],
}

# Pipe-delimited lists shared by all documents, read directly from <data-dir>.
PROPERTIES_FILE = "properties.csv"
CARRIERS_FILE = "carriers.csv"
AGENTS_FILE = "agents.csv"
PAYEES_FILE = "payees.csv"

OCR_KEYS = {
  "activitystatuscode": "activity_status_code",
  "agentaddressline1": "agent_address_line1",
  "agentcity": "agent_city",
  "agentcontactsignatureblock": "agent_contact_signature_block",
  "agentname1": "agent_name1",
  "agentstate": "agent_state",
  "agentzipcode": "agent_zipcode",
  "balancedueamount": "balance_due_amount",
  "basepolicynumber": "hzwg_kkkilb_fottoj",
  "carriername": "carrier_name",
  "created_by": "created_by",
  "created_date": "created_date",
  "documentdetailid": "document_detail_id",
  "documentid": "document_id",
  "earthquakeexcludedflag": "earthquake_excluded_flag",
  "insurancecompanyaddressline1": "insurance_company_address_line1",
  "insurancecompanycity": "insurance_company_city",
  "insurancecompanycontactsignatureblock": "insurance_company_contact_signature_block",
  "insurancecompanyname1": "insurance_company_name1",
  "insurancecompanyname2": "insurance_company_name2",
  "insurancecompanystate": "insurance_company_state",
  "insurancecompanyzipcode": "insurance_company_zipcode",
  "insuredname1": "insured_name1",
  "insuredname2": "insured_name2",
  "mortgagee1addressline1": "mortgagee1_address_line1",
  "mortgagee1city": "mortgagee1_city",
  "mortgagee1loannumber": "mortgagee1_loan_number",
  "mortgagee1name1": "mortgagee1_name1",
  "mortgagee1name2": "mortgagee1_name2",
  "mortgagee1state": "mortgagee1_state",
  "mortgagee1zipcode": "mortgagee1_zipcode",
  "noticetypecode": "notice_type_code",
  "originalloannumber": "original_loan_number",
  "paymentduedate": "payment_duedate",
  "pfi_client_id": "pfi_client_id",
  "policyeffectivedate": "policy_effective_date",
  "policyexpirationdate": "policy_expiration_date",
  "policyinsuranceformtype": "policy_insurance_form_type",
  "policynumbers": "policy_numbers",
  "propertyaddressline1": "property_address_line1",
  "propertyaddresssignatureblock": "property_address_signature_block",
  "propertycity": "property_city",
  "propertystate": "property_state",
  "propertyzipcode": "property_zipcode",
  "windexcludedflag": "wind_excluded_flag"
}

SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]+$")

app = Flask(__name__)
app.config["DATA_DIR"] = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def error(status, message):
    response = jsonify({"error": message, "status": status})
    response.status_code = status
    return response


def detect_encoding(path):
    """Mock files may be saved as UTF-16 (e.g. by Windows editors); sniff the BOM."""
    with open(path, "rb") as fh:
        head = fh.read(4)
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    return "utf-8-sig"


def load_json(path):
    with open(path, "r", encoding=detect_encoding(path)) as fh:
        return json.load(fh)


def read_rows(reader):
    """Return the reader's rows, skipping any whose first field is empty."""
    if not reader.fieldnames:
        return []
    first = reader.fieldnames[0]
    return [row for row in reader if (row.get(first) or "").strip()]


def load_csv(path, delimiter="|"):
    """Return each row of a delimited CSV file as a dict keyed by header."""
    with open(path, "r", encoding=detect_encoding(path), newline="") as fh:
        return read_rows(csv.DictReader(fh, delimiter=delimiter))


def load_ocr(path, delimiter="|"):
    """Return a pipe-delimited key|value OCR file as a dict, renaming each key
    via OCR_KEYS (unknown keys are kept as-is). The header row is skipped."""
    with open(path, "r", encoding=detect_encoding(path), newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        next(reader, None)
        result = {}
        for row in reader:
            if not row or not row[0].strip():
                continue
            key = row[0].strip()
            value = row[1].strip() if len(row) > 1 else ""
            result[OCR_KEYS.get(key.lower(), key)] = value
        return result


def document_dir(document_number):
    return os.path.join(app.config["DATA_DIR"], document_number)


def find_file(document_number, candidates):
    folder = document_dir(document_number)
    for name in candidates:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None


def serve_json(resource, document_number):
    if not SAFE_ID.match(document_number):
        return error(400, "Invalid document number")
    if not os.path.isdir(document_dir(document_number)):
        return error(404, f"Document '{document_number}' not found")
    path = find_file(document_number, RESOURCE_FILES[resource])
    if path is None:
        return error(404, f"No {resource} data for document '{document_number}'")
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".csv":
            return jsonify(load_csv(path))
        if ext == ".json":
            return jsonify(load_json(path))
    except (json.JSONDecodeError, csv.Error, UnicodeDecodeError) as exc:
        return error(500, f"{os.path.basename(path)} for '{document_number}' could not be parsed: {exc}")
    return error(500, f"Unsupported file type '{ext}' for {resource}")


def serve_csv(filename, delimiter="|"):
    """Return each row of <data-dir>/<filename> as a JSON object. Any query
    parameter whose name is a CSV column filters rows by case-insensitive
    exact match on that column."""
    path = os.path.join(app.config["DATA_DIR"], filename)
    if not os.path.isfile(path):
        return error(404, f"{filename} not found")
    try:
        with open(path, "r", encoding=detect_encoding(path), newline="") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            columns = set(reader.fieldnames or [])
            rows = read_rows(reader)
    except (csv.Error, UnicodeDecodeError) as exc:
        return error(500, f"{filename} could not be parsed: {exc}")

    filters = {k: v.strip().lower() for k, v in request.args.items()
               if k in columns and v.strip()}
    if filters:
        rows = [row for row in rows
                if all((row.get(k) or "").strip().lower() == v for k, v in filters.items())]
    return jsonify(rows)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/search", methods=["GET"])
def search():
    return serve_csv(SEARCH_FILE, delimiter=",")


@app.route("/loan/<loan_number>", methods=["GET"])
def get_loan(loan_number):
    """Loan files sit directly in <data-dir>, named loan-<loan_number>.json."""
    if not SAFE_ID.match(loan_number):
        return error(400, "Invalid loan number")
    name = f"loan-{loan_number}.json"
    path = os.path.join(app.config["DATA_DIR"], name)
    if not os.path.isfile(path):
        return error(404, f"No loan data for loan '{loan_number}'")
    try:
        return jsonify(load_json(path))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return error(500, f"{name} for '{loan_number}' could not be parsed: {exc}")


@app.route("/properties", methods=["GET"])
def get_properties():
    return serve_csv(PROPERTIES_FILE)


@app.route("/carriers", methods=["GET"])
def get_carrier():
    return serve_csv(CARRIERS_FILE)


@app.route("/agents", methods=["GET"])
def get_agent():
    return serve_csv(AGENTS_FILE)


@app.route("/payees", methods=["GET"])
def get_payee():
    return serve_csv(PAYEES_FILE)


@app.route("/case/<document_number>", methods=["GET"])
def get_case(document_number):
    return serve_json("case", document_number)


@app.route("/pdf/<document_number>", methods=["GET"])
def get_pdf(document_number):
    if not SAFE_ID.match(document_number):
        return error(400, "Invalid document number")
    path = find_file(document_number, ["case.pdf"])
    if path is None:
        return error(404, f"No case.pdf for document '{document_number}'")
    return send_file(path, mimetype="application/pdf",
                     download_name=f"{document_number}.pdf")


@app.route("/ocr/<document_number>", methods=["GET"])
def get_ocr(document_number):
    if not SAFE_ID.match(document_number):
        return error(400, "Invalid document number")
    path = find_file(document_number, ["case.ocr"])
    if path is None:
        return error(404, f"No case.ocr for document '{document_number}'")
    try:
        return jsonify(load_ocr(path))
    except (csv.Error, UnicodeDecodeError) as exc:
        return error(500, f"case.ocr for '{document_number}' could not be parsed: {exc}")


@app.route("/openapi.yaml", methods=["GET"])
def openapi_spec():
    return send_file(os.path.join(BASE_DIR, "openapi.yaml"), mimetype="application/yaml")


# --------------------------------------------------------------------------- #
# CORS (mock HTML pages are opened from another origin) and error handlers
# --------------------------------------------------------------------------- #
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


@app.errorhandler(404)
def not_found(_):
    return error(404, "Resource not found")


@app.errorhandler(405)
def method_not_allowed(_):
    return error(405, "Method not allowed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Loan tracking mock API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 9191)))
    parser.add_argument("--data-dir", default=app.config["DATA_DIR"])
    args = parser.parse_args()
    app.config["DATA_DIR"] = os.path.abspath(args.data_dir)
    print(f"Serving data from {app.config['DATA_DIR']}")
    app.run(host=args.host, port=args.port, debug=True)
