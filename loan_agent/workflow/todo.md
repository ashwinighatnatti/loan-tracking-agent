# Mocks

## Screens HTML

LoanDetails page 
2. Carrier Search
3. Agent Search
4. Payee Search
5. Full Loan Details
6. Adance Loan Search
7. MCC screen

Find Loan
- Make Loan number clickable (similar to load button)
- Load button should load the document to todo list


## Data

End to end mock data

1. Loans
2. Properties
3. OCR
4. PDF file
5. PDF extract (renewals)
6. Full Loan Details link
7. Advance Loan Search Data

# Page functions

## Screen: Loan Details

1. Read LoanDetails 
2. Read Comments
3. Read specific Property
4. Read specific Insurance Line
5. Read Full Loan Details 
6. Read MCC screen

## Document Extraction

Extract EDI Renewals
- ocr pdf reader
- llm 

## Screen: Find Loan 

Given the document, find Loan to work 
- pass DocumentSearch (Page1 screen data) to this screen, (work_url)
- access ocr data from screen to get required data (names, address, loan_type, ...)
- fallback to document extraction from pdf (names, address, loan_type, ...)
- search with various combinations 
- name and address scenarios
- verify address match (sop rules)
- fall back to llm for verification of name, adddress
- corner cases (Estate of ..., listbill and other misc name / address rules)
- Actions.Done {status: CannotID, comment: '' }
- Actions.Edit {status: Inquiry, comment: 'Name Disc'}
- Actions.Edit {status: Inquiry, comment: 'Address Disc'}
- Last step: pass the loan to the LoanDetails page (click on loan number after clicking load button)

### Not Impl:

- verify comment section for Name
- verify comment section for Address 
- issue discrepency letter after verifying comment section for Name, Address 
- verify previous documents (for name and carrier match)
- verify loan_type = commercial
- verify name match with additional insured
- Advance Loan Search

## Screen: Process Document

Processing Orchestration 
- invoke read LoanDetails screen to get loan.json
- invoke document extraction (case.json and/or case.ocr)
- check early exit conditions and close
- verify mcc and mark deficiency
- verify lien position
- verify escrow position
- compose { Output-Packet: insurance_line, comments, deficiencies }
- check existing line or new line
- if no line then, create new insurance_line (with case.json)
- check prepare payment (60-120 day rule), expedite
- check additional due, expedite 

- mark/unmark deficiencies (mid-term, deductible, others)
- process_complete: Done/Complete
- process_complete: Edit/TBP 

- handle mid-term, nubiz, old policy, same year, rewrite, renewal (Ecrow/Non Escrow)
- check comments when handling mid-term, nubiz
- hanlde mid-term, nubiz comments
- cancellation reason/date
- handle (hazard, wind, earthquake, flood)
- handle status (PNA, AOF, Not Tracked, Sold, Paid In full)


### Not Impl:
- link properties feature
- check lender placed policies
- check lender placed for new line creation

## Technical stuff

- handle login into app
- each execution should work one browser instance (tabs: login, next-doc, find-loan, proces-doc)
- each execution should have a unique execution id of format :- yyyymmdd-docnum-charstr[:6]-randint(1,10)
- collect tracking context for each execution
- persist tracking context with execution id under output_dir/  <yyyymmdd>/<docnum>/<part3-part4>
