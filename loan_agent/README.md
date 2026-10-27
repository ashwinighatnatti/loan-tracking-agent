# DOCUMENT PROCESING

Following process applicable for RENEWALS

0. Login (Page_0)
    with user_name/password

1. Search Documents (Page_1)
    (Criteria: To Be Processed, EDI, RENEWAL, Blank Comments)
    Pick 1 document (type: DocumentRecord)

2. With document: DocumentRecord  
        pdf_url     = link to document pdf

3.  With document: DocumentRecord  
        work_url    -> nextgen page

    Find Loan (Page_2)
    Goto work_url

    ocr_extract = data from ocr (mock: case.ocr)
    If ocr_extract:
        has property_address
        has borrower_name
        has co_borrower_name

    If not:     
        doc_extract = data from pdf_url (type: RenewalDocInfo, mock: case.json)

    Build criteria: LoanSearchCriteria
        criteria.borrower           = *_extract.borrower 
        criteria.co_borrower        = *_extract.co_borrower
        criteria.property_address   = *_extract.property_address 
        { address has its components }

    LoanSearchPage:
        Match: Borrower, Co-Borrower, Property Address
    
    If Not Found Loan Then
    AdvanceLoanSearchPage:
        Match: Borrower, Co-Borrower, Property Address

    If Not-Found Loan Then
        Status = EDIT > "Cannot ID"
        GOTO :END
    
    On Page_2:  
        Add Matching Loan to ToDo list
        Click on Loan# (from suggested item)
        Goto Page_3

4. Process Loan (Page_3)

    Check if On Page_3 (LoanDetails)
        loan_extract    = data from LoanDetails screen (type: Loan, mock: loan.json) 

    Check Full Loan Detail:  Escrow / Non-Escrow

    Select Property (matching property address)
    Select Property Line (matching policy type)
    (

    )
    #Line Found
        #Capture Carrier
        (
            Carrier Not Matching
            (
                Case# Mid Term
                Case# New Business
            )
            Carrier Not Available
            (
                ##? 
            )
        )
        #Capture Agent, 
        (

        )
        #RemitTo/Payee Agent
        (

        )

    #Line NotFound
        Create New Insurance Line
    
    #Capture Status
    (
        policy number
        coverage
        dates
        Escrow
    )    
    #Capture Coverage 
    (

    )
    #Capture Premium
    (
        premium
        additional due
        
        make payment
        expedite
    )
    #Capture Deficiencies
    (

    )
    
6.  END: Complete Loan# 
    STATUS > EDIT
    (
        INQUIRY = "Borrower Name does not match or Borrower Address does not match"
        BOA_HAZARD
        CALL
        DISBURSEMENT
        HELOC
        LENDER_PLACED
        LIFE_OF_LOAN
        MANAGER_REVIEW
        MID_TERMS
        MISC
        PENDING
        RESEARCH_QUEUE
        RETURN_TO_CLIENT
        RETURN_TO_EXAMPLECO
        TO_BE_PROCESSED
    )

    STATUS > DONE
    (
        ALREADY_ON_FILE     = "Loan was not updated as information received is Already On File (AOF)"
        ARCHIVE_AOF         = "" 
        COMPLETE            = "Loan was updated with the policy information (even if it was just a deficiency)."
        NOT_TRACKED         = "Earthquake policy (Escrow/Non-Escrow Verify address and name & do not process)- if policy is non-escrow, then - Action > Done > Not Tracked > Comment ‘’Earthquake Policy’’"
        PAID_IN_FULL        = "The loan is fully paid off."
        POLICY_NOT_ACCEPTED = "Policy Not Accepted – Old Policy - if a previous policy is received and not updated or used to cancel an LP policy"
        SOLD                = "Sold – the loan has been sold to another servicer."
    )

    STATUS > DISCARD
    (
        DISCARD
    )



#============== Psuedo python code.. not real. (discard)


# app = information retrieved from application (api/screens)
# doc = information retrieved from pdf/tiff through OCR/LLM
# ocr = information retrieved from application ocr data

#======== Goal 1: Find Document 
 
doc_criteria = DocumentSearchCriteria("Renewal", "EDI", "To Be Processed")
with DocumentSearchPage(url=args.url, headless=True, timeout_ms=args.timeout,storage_state=args.storage_state) as scraper:
        docs = scraper.search(doc_criteria, sort=args.sort, descending=args.desc, max_pages=args.max_pages)
        total, pages = scraper.total_items(), scraper.page_count()

doc = docs[0]    # type DocumentRecord

#======== Goal 2: Find Loan

loan_criteria = LoanSearchCriteria( doc.>>>>> )
with LoanSearchPage(url=doc.work_url, headless=True, timeout_ms=timeout, storage_state=storage_state) as scraper:
    loans = scraper.search(loan_criteria, save=save)       

loan = loans[0]

doc_info = extract_document(from_pdf = doc.link)
app_info = extract_(from_screen = "Workspace")

if Not match_nad(doc_info, app_info):
    action add_coment ("Name Disc")
    action document close

add Loan to ToDo List

#======== Goal 3: Process Line

app = LoadJSON( extract_loan(from_api, doc.loan_number) if API_FLAG else extract_loan(from_screen, doc.loan_number) )

goto screen LoanDetails
app_info = extract_info(from_screen = "LoanDetails")

if app_info is None:
    app_info = extract_info(from_api = doc.loan_number)

with doc_info, app_info
    anaylyze information
    apply rules
    generate decisions
    generate actions

generate outputs

   

"""