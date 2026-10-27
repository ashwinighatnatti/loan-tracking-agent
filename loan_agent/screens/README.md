# Screen List

IIM App
\ 
 + 0. login_page.py                - Handle Login
 + 1. document_search_page.py      - Handle Document Search
 + 2. loan_search_page.py          - Handle NextGen page+ 
 + 3. loan_detail_page.py          - Handle Loan Details page

# Screen Analysis

Following screens need to be scraped.

    x-x-x                                   => Readonly-Interaction-ReadWrite
- DocumentSearch                                           x-0-0
- LoanSearch >                                             x-x-0
- LoanDetails                                              x-0-0
- LoanDetails > Comments                                   x-0-x
- LoanDetails > MCC                                        x-0-0
- LoanDetails > Audit                                      x-0-0
- LoanDetails > Condos                                     0-0-x
- LoanDetails > Full Loan Details                          x-0-0
- LoanDetails > Contact Summary                            x-0-0
- LoanDetails > Collateral Information                     0-x-x
- LoanDetails > Linked Properties                          0-x-x
- LoanDetails > Insurance Lines                            0-x-x
- LoanDetails > Insurance Lines > Carrier                  0-x-x
- LoanDetails > Insurance Lines > Agent                    0-x-x
- LoanDetails > Deficiency                                 0-0-x

# Actions to be performed on a section of screen 

Browser
    goto    (url#)

InsuranceLine
    select_line ( type, policy, line_id )
    add_comment
    save_line
    save_line_and_done_todo_item

Collateral
    select_collateral
    save_colalteral

Deficiency
    mark_deficiency (name, true/false)

Comment
    add_comment (comment_type, text)

Condos
    update_association

LoanDetails
    search_loan (loan#)

Workspace
    todo_edit   ()
    todo_done   ()
    todo_discard()

    option_finish_document
    option_finish_document_and_get_next
    option_get_next_document

== Action data structure

[{   
    section: "InsuranceLine", 
    action: "select_line", 
    data: {}
},
{   section: "InsuranceLine", 
    action: "select_line", 
    data: {}
},
{
    section: "InsuranceLine", 
    action: "select_line", 
    data: {}
}]


=========


# Data Extraction from pdf/image

Following fields are common for every document

document_type        = type of document 
                        (Auto, Binder, Certificate of Insurance(COI), Flood Insurance, 
                        Invoice, Renewal, NLSU, Reinstatement, Cancellation, List/Strip bill)

print_date          = date when the document was printed

borrower
co-borrower
additional_insured  = [] | Optional
property_address    (aka. insured location, )

agent_name
agent_address
agent_fax
agent_email

carrier_name        (insurance company)
carrier_address

mortgagee 1st
mortgagee 2nd

Renewal#
    policy_number
    effective_date
    expiration_date
    effective_cancellation_date
    reinstatement_date

    premium_amount
    balance_due
    deductible




## Screen functions setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Point it at the app

The scraper works against any URL that serves mock `document-search.html`:

```bash
# local file
python document_search.py --url "file:///path/to/document-search.html" --loan-number 0442051999
python document_search.py --url "http://localhost:9090/document-search.html" --status "To Be Processed"

# local web server
python -m http.server 9090          # in the folder holding document-search.html
python document_search.py --url http://localhost:9090/document-search.html --status "To Be Processed" --out results.csv
```

If you run it against the hosted claude.ai artifact you must be signed in, so pass
`--headed` and log in once, or use `--storage-state state.json` to reuse a saved session.

## Use as a library

```python
from document_search import DocumentSearchScraper, SearchCriteria

with DocumentSearchScraper(url="http://localhost:9090/document-search.html") as scraper:
    records = scraper.search(SearchCriteria(type="Renewal", status="To Be Processed"))

for r in records:
    print(r.document_number, r.loan_number, r.status)

```

`records` is a `list[DocumentRecord]`; `r.to_dict()` gives a plain dict per row.

## Options

| Flag | Filter field |
|---|---|
| `--client` | Client (select value, e.g. `41207`) |
| `--number` | Document number (contains) |
| `--import-from` / `--import-to` | Import date range `MM/DD/YY` |
| `--type` | Doc type |
| `--source` | Doc source |
| `--loan-number` | Loan number (contains) |
| `--status` | Status |
| `--csr` | CSR code |
| `--update-from` / `--update-to` | Last update range |
| `--comments` | Comments (contains) |
| `--sort COL --desc` | Sort column before scraping (`import_date`, `loan_number`, ...) |
| `--max-pages N` | Stop after N pages (default: all) |
| `--out FILE` | Write `.json` or `.csv` |
| `--headed` | Show the browser |
