# Mocks for Loan Processing Application

Contains mocks for web pages and api. Preferred option for retrieving loan data

1. API 
2. Webpage Scraping

## Webpages

document-search.html    - mock for document search
loan-search.html        - mock for loan-search in workspace

# Launch Mock 

## Launch API mock server

Open a new Terminal window

1. cd /mocks/api
2. python server.py --port 9191

## Launch Webpage server

Open a new Terminal window

1. cd /mocks
2. python -m http.server 9090

## Launch browser

goto localhost:9090/document-search.html

## Sample PDFs

The sample PDFs referenced by the mock API (`mocks/pdf/` and the `case.pdf` files under `mocks/api/data/`) are not included in this repository. The API serves them if present; the tests do not need them.
