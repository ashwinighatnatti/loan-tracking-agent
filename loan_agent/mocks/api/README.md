# Mock Data Design 

Data is to be mocked at these areas

1. document-search.html     - list of cases available to be picked up
2. loan-search.html         - with a document number, get a list of matching properties
3. carrier search           - search carrier name and address
4. agent search             - search agent details
5. agent payee search       - agent payee search 

# API Design

<base-url>/search:
Returns contents of the file 'doc-search.results.csv' where each line is converted to JSON and returned

<base-url>/loan/<loan-number>:
Returns the contents of the file 'loan-<loan-number>.json' directly under <data-dir>

<base-url>/properties
Returns the rows of the file 'properties.csv' directly under <data-dir> as JSON

<base-url>/carriers
Returns the rows of the file 'carriers.csv' directly under <data-dir> as JSON

<base-url>/agents
Returns the rows of the file 'agents.csv' directly under <data-dir> as JSON

<base-url>/payees
Returns the rows of the file 'payees.csv' directly under <data-dir> as JSON

Like /search, these accept query parameters named after a CSV column to filter rows
(case-insensitive exact match), e.g. <base-url>/properties?loan_number=97894

<base-url>/pdf/<document-number>
Returns the contents of the file 'case.pdf' under the physical folder <data-dir>/<document-number>

<base-url>/case/<document-number>
Returns the contents of the file 'case.json' under the physical folder <data-dir>/<document-number>


# File structure on disk

<base-url>        - url on which the mockserver listens  (http://localhost:9191/)
               
<base-dir>        - disk directory contains mockserver, its openapi spec, README.md, and <data-dir>
 - server.py      - Server implementation in python (Flask)
 - openapi.yaml   - OpenAPI spec
 - README.md      - this file
 - ocr.keys.json  - 
 - ocr.keys.json  -
 - json_to_csv.py - 
 - create-foldes-ps1 - 
 - dat.txt
 - <data-dir>     - directory containing various test data folders

<data-dir>                    -   folder
 - doc-search-results.csv     -   contains the results of each 'case' to be returned in document-search.html
 - loan-<loan-number>.json    -  contains loan details
 - properties.csv             -   contains list of properties for loan-search.html
 - carriers.csv               -   contains carriers
 - agents.csv                 -   contains agents
 - payees.csv                 -   contains payees
 + <document-number>          -   folder        
    - case.pdf                  - contains the document to be processed for the loan
    - case.json                 - contains the extracted document fields from the case.pdf
    - case.ocr                  - contains the ocr fields extracted from the document through roping process

# How to run API Server

python server.py -port 9191

# Test data creation script

Creates folders under <data-dir> with contents of the templatedir .\data\DEFAULT_DOC
Read each line of the file `dat.txt` and create a folder by that number. 

```
[Powershell]
.\create-folders.ps1 -TemplateDir .\data\DEFAULT_DOC  
```