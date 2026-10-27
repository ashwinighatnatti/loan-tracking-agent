app_sections = [
    loan-details
    transaction-history
    insurance-documents
    correspondence
    calls
    lender-placed-claims
    tab-comments
    collateral-info
    insurance-line
    deficiencies
]
app_actions = [
    select

]


Structure
[{
    section: "",       action: "",
    data: {

    }
},
{    
    section: "",       action: "",
    data: {

    }
},
{    
    section: "",       action: "",
    data: {

    }
}]

###############

Document Search
Get PDF/Image, Document Type
Extract pdf -> DocJSON
Store extracted JSON to DB (with Loan#, Document Number, )
 
 ==# gap 

Agent picksup READY records
Find Loan (do Suggested Item Search, Advanced Search)
Add to ToDo list    // what happens if we dont add to ToDo list

Goto Loan Details page
Extract LoanDetails -> LoanJSON





###############




ROUTINE: RULE-CHECK()
{
    If Diff( _a.closing_date, _d.effective_date ) < 60 Days Then 
        Do Not prepare Payment
  
}

"""
ACTIONS-TODO() 
"""
ROUTINE: ACTIONS-TODO(status, document_type, comment = "", csr = "")
{
    WITH SCREEN 

    CASE $Action

    WHEN DONE
        Set-Combobox("Status", status)
        Set-Combobox("CSR", csr)
        Set-Text("Document Type", document_type)
        Set-Text("Comment", comment)
    
    WHEN EDIT
        Set-Combobox("Status", status)
        Set-Combobox("CSR", csr)
        Set-Text("Document Type", document_type)
        Set-Text("Comment", comment)
        Permitted ACTIONS("RELESAE DOCUMENT AND GET NEXT" || "RELEASE DOCUMENT")
    
    WHEN DISCARD
        pass

}

"""
ACTIONS-DOCUMENT() 
"""
ROUTINE: ACTIONS-DOCUMENT(status, document_type, comment = "", csr = "")
{
    WITH SCREEN 

    CASE $Action
    WHEN "CHANGE DOCUMENT CLIENT"
    
    WHEN "REASSIGN DOCUMENT"
    
    WHEN "FINISH DOCUMENT"

    WHEN "FINISH DOCUMENT AND GET NEXT"

    WHEN "GET NEXT DOCUMENT"
}


ROUTINE: ANALYZE-COMMENTS()
{
    Set-Flags
    {
        #do-not-pay,
        #special-handling,
        #name,
        #address,
        #current-term-cancellation,
        #previous-term-cancellation,
        #current-term-reinstatement,
        #previoius-term-reinstatement
    }
}

ROUTINE: ACTION-ADD-NEW-LINE
{
    App (_a):
        Escrow-Status
       
    Select Line-Type
    Click "Add New line to Property"
    Update Escrow-status
}

ROUTINE: ACTION-SEARCH-CARRIER(_d.Carrier-Name, _d.Address)
{

    If Carrier is (Sample Carrier 35, Sample Carrier 36 etc) Then
        Search Carrier Address State wise Property address, state code. 

    Goto field(Carrier) 
    Press Enter
    Opens Search Box
        Search By _d.Address
        Select "Use Names Check box"
        Search By _d.Carrier-Name

    //# ?? HOW
    From Results, Select Carrier

    If Carrier is "Sample Carrier 31" Then
        Always Pick ACH EDI carrier irrespective of any document. 

    If Carrier in ( Sample Carrier 30, Sample Carrier 31, Sample Carrier 32 Insurance, Sample Carrier 33, Sample Carrier 28 Insurance) Then 
        Always pick ACH EDI carrier 

    If Carrier is "Sample Carrier 32 Insurance" AND Underwritten-by = "Sample Carrier 34" Then
        Always Pick "– PO BOX 0915"

    Return Carrier
}

ROUTINE: ACTION-SEARCH-AGENT-PAY(_d.Agent-Name, _d.Address)
{
    //# TODO
}

ROUTINE: ACTION-MARK-DEFICIENCY(_mark)
{
    //# Mark/Unmark Deficiency on a page
}

"""
Find loan# from the received document in NextGen Page
"""
ROUTINE: ACTION-FIND-LOAN( _d: LoanDocument)
{
    Document (_d)
        Loan-Number
        Borrower-name
        Property-address
        Borrower-mailing-address
        Policy-Number (except last 2 digits)
        Loan-Status

    WITH SCREEN "NEXTGEN-PAGE" READ-SCREEN()

    Suggested-Items 
    CASE: "No Loans found"
    {
        WITH SCREEN "NEXTGEN-PAGE"

        DO Suggested-Items-Search
            With ZipCode    Click "save+search"         CheckResults    ||
            With City       Click "save+search"         CheckResults    ||
            With Loan       Click "save+search"         CheckResults    ||
            With Policy     Click "save+search"         CheckResults    ||

        If No Loan-Found Then 
        
            WITH SCREEN "IIM MENU > LOAN-SEARCH"
            
            DO Loan-Search 
                With Loan-Number
                With Insured-name
                With Property-address
                With Insured-mailing-address
                With Policy-Number (except last 2 digits)
            
            CheckResults    

        End If
    
        If No Loan-Found Then 
            GOTO #NOID
        Else    
            Select Loan and Continue    
    }

    CASE: "1 Loan found"
    {    
        Select Loan and Continue
    }
    
    CASE: ">1 Loans found"
    {
        //#?? WHAT-TO-DO
        Select **CORRECT** Loan and Continue
    }



    RETURN 

        #NOID:
        {    

            ADD COMMENT "CANNOT ID"
            ACTIONS-TODO( DONE )
            RETURN
        }            
}

ROUTINE: RESOLVE-CASE-MIDTERM-NEWBIZ(dates)
{
    a =  cur.effective_date
    b = cur.expiration_date

    c = doc.effective_date
    d = doc.expiration_date

    If (c > b) AND (c - b) = 0 or 1 Then NewBiz

    If (c < b) AND (c > a) Then 
        current policy is not cancelled
        MidTerm update with Payment
        send Letter, 
        update midterm comment

    Else 
        //# Cancellation-Date and Reason?
        NewBiz
        current policy is cancelled
        Update and make Payment
        Update newbiz comments
    End If    

    If a = c AND b = d Then 
        MidTerm update with Payment
        send Letter, 
        update midterm comment
    End If

}

Stage 1: Check-Policy-Number
{
   App (_a)	
        Document-type
        Policy-Number	

    Document (_d)
        Policy-Number

    If Policy-Number has suffix (MLR, FLR, ALR) Then   
        ?Status = Not Tracked
        ?Note: Prior Servicer LP on file

    policy_number = Trim_Policy_Number( _d.Policy-Number )

}

Stage 2: Match-NAD
{
    App (_a)	
        Document-type	
        Borrowers’ name & address	
        Loan-type
        Comments	
        Carrier

    Document (_d)
        Document-type
        Borrowers’ name & address
        Coborrower, Additional Insured []
        Carrier, 
        _prev_doc.Carrier

    Try:

        name_match  = MATCH-NAME( _d.document-type, _a.borrowers, _d. borrowers )
        address_match = MATCH-ADDRESS ( _a.address, _d.address )

        chk_comments_name = ANALYZZE-COMMENTS(#name)
        chk_comments_addr = ANALYZE-COMMENTS(#address)

        If chk_comments_name = Yes Then  
            name_match = Yes

        If chk_comments_addr = Yes Then
            addr_match = Yes    
    
    Action:
        
        If name_match = No AND Loan-Type = ‘Commercial’ AND address-match = No Then 
            Add_Action("ERROR", “S1.A1”, “Commercial Loan Must match address”)

        If chk_comments_name = No AND name_match = No Then
            Add_Action("ERROR" "S1.A2", "SEND_NAME_DISC_LETTER_MARK_PNA")    

        If chk_comments_addr = No AND addr_match = No Then
            Add_Action("ERROR" "S1.A3", "SEND_ADDR_DISC_LETTER_MARK_PNA")    

        If name_match = No Then  
            Add_Action("ERROR", "S1.A4", "SEND_TO_MISC_INQUIRY_QUEUE")

        If addr_match = No Then  
            Add_Action("ERROR", "S1.A5", "SEND_TO_MISC_INQUIRY_QUEUE")

    Exception:
}

Stage 2: Add-To-ToDo
{
    Click '+' link next to Todo Actions to open Loan Details page

    Add Loan to SEND_TO_MISC_INQUIRY_QUEUE
    Click on the Loannumber hyperlink
}

Stage 3: Check-COI
{
    If Document is COI Then 
        Check AND Update Association name
}

Stage 4: Select-Collateral
{
    Document (_d)
        Lien-Position
        Borrower Name 
        Borrower Address

    Check If Single Or Multiple Property

    When multiple Property
        Select Correct Property 
        as per _d.Property-Address

    Validate Mortgagee Claue
        Validate _d.Lien Position
        If Mismatch Then   
            Action-MarkDeficiency (MCC)
            Exit?
    
    //# Check Link Properties

    If "!" on Link Properties Then  
        Match Borrower Name AND Address with Document#
        Attach Loan with Active Loan
        Click Save Collateral Button

    When Line Position Match with Active Loan Then
        Update

    //# Check if property is correctly attached or linked

    //# Check Property is already Attached     
    If (Linked Loan is 'Paid in full' or 'Sold Loan' ) AND Property is Attached   
        //# Donot Attach Collateral to Active Loan
        If Attached Then Detach
}

Stage 5: Insurance-Lines
{
    App (_a)
        Policy-Type
        Policy-Number
        Line-Number

    Document (_d)
        Policy-Type

    Policy is Hazard: Home, Dwelling Fire, Mobile Owner Policy, Condominium Units
    Policy is Wind: Wind Only, Hurricane Policy, Dwelling DW-2 Wind Only, Wind & Hail Only
    Policy is Flood: ??

    Select _d.Line-Type 
    Case Hazard, Wind, Flood: 
        //# Point to the right Policy-Type AND Line-number
    Case None:
        ADD-NEW-LINE (_d)
}

Stage 6: Carrier-NAD
{
    App (_a)
        Policy-Type
        Policy-Number
        Line-Number
        Carrier-Name
        Carrier-Address

    Document (_d)
        Policy-Type
        Policy-Number
        Carrier-Name
        Carrier-Address

    Select Line-Type (from Step 5)

    Mathing = Match (_d.Carrier-Name, _a.Carrier-Name)

    carrier, found = SEARCH-CARRIER(_d.Carrier-Name)
    Carrier-Address = AnyOf (
        Make Cheque Payable ||
        Billing Address ||
        Payment Addres ||
        Remit To Address
    )

    If _a.Carrier-Name = _d.Carrier-Name Then 
        _d.Carrier-Global-Payee-Address

    //# ?? What is Payment-Address

    Carrier-Global-Payee-Regular-Mail-Address = SEARCH-CARRIER(NAME, ADDRESS)    
    Carrier-Global-Payee-Overnight-Mail-Address = SEARCH-CARRIER(NAME, ADDRESS)
    
    Case Matching = No:
        Check case of Mid or New Biz

    Case found = No:
        //# Raise Exception - Put in Pending - Send Address to Add Payee team 
        //# End

    Action:
        Update carrier
        Update Carrier-Address
        Update Carrier-Global-Payee-Regular-Mail-Address
        Update Carrier-Global-Payee-Overnight-Mail-Address
}

Stage 7: Agent-Pay-Details
{
    App (_a)
        Agent-info

    Document (_d)
        Agent-info

    remit = From Document# AnyOf (
        Make Check Payable to,
        Make Check Payment to,
        Mail Payment to,
        Remit To,
        Remittance Address
    ) || From App (//#??)

    pay-agent = Yes
    remit-to-address, found = SEARCH-AGENT-PAY()

    If found = No AND _d.Document-Type = 'Renewal' Then Ok
    If found = No AND MidTerm or NewBiz Then agent-info = Agent (as per document)

    If found = No Then 
        agent-info = carrier-info
        Mark Deficiency
    End if

    Action:
        Pay Agent CheckBox = Yes
        Mark-Deficiency
}

Stage 8: Term-Dates 
{

    If Escrow = Yes Then
        Update Expiration-Date
        Update Policy-Term = 12 Months
    Else
        Update Expiration-Date
        Update Effective-Date
        Update Policy-Term = 12 Months
    End If    

    Select Policy
    Case OldPolicy:
        Action: DONE
        PNA 
        Comment OldPolicy
    
    Case SameYearPolicy:

        Update Term-Dates as per Document
        Payment Not Required

        If _a.Payment-Check-Box = Yes Then
            //# Renewal policy already received
            Action: DONE
            PNA
            Comment OldPolicy

    Case RewritePolicy:

        If RULE-60-120() = Yes Then 
            Update dates as per document
            Rollback year //# ??
        Else
            Donot Prepare Payment   //# ??
            Update dates as per document
        End If
}

Stage 9: Cancellation
{

    App (_a)
        Cancellation-Date
        Cancellation-Reason
        
    Document (_d)
        Document-Type
        Expiration-Date
        Effective-Date
        Print-Date
    
    If _d.Document-Type <> 'Cancellation' AND Term = IsCurrentTerm(_d.Effective-Date, _d.Expiration-Date) Then
        //# What does Remove means?
        Cancellation-Date = Blank
        Cancellation-Reason = Blank

    cancellation_reason = CHECK-COMMENTS()
    cancellation_audit  = CHECK-AUDIT-HISTORY()

    If Policy-Type = 'Renewal' with SameCarrier OR MidTerm OR NewBusiness Then   
        Cancellation-Reason = Blank
        
    When SameCarrier, SameYear Then 
        Validate Cancellation Print-Date (in comments) AND _d.Print-Date        //#??
        If _d.Print-Date > Print-Date (from comments) Then  
            Remove reason AND work //#??
        If Print-Date(from comments) > _d.Print-Date Then
            Move Loan to PNA-Cancellation as on file                            //#??
    
    If Escrow = Yes AND _d.Cancellation-Reason is 'Non Payment / Unknown reasons' Then
        Action: > Edit > HELOC (Cancellation Calls) > Comment > Call Needed
    
    If _d.Cancellation-Reason = 'Reinstatement - No Lapse/ with Lapse' AND Date Then    
        Cancellation-Date = Blank
        Cancellation-Reason = Blank
}

Step 10: Coverage
{

    App (_a)
        UPB
    
    Document (_d)
        Coverage-Amount

    Different terms: 
        Coverage A, 
        Coverage A – Residence, 
        Building Coverage, 
        Dwelling Coverages, 
        Building Property Coverage, 
        Building Property Protection, 
        Additions AND Alterations
    	Will not include Personal Property Protection in Property Coverage Amt.

    If _d.Coverage-Amount is Missing Then
        coverage = Blank
    
    If _d.Coverage-Amount is Missing AND Guranteed-Replacement-Cost is Yes Then   //#?? Guranteed-Replacement-Cost
        coverage = _a.UPB

    Action:
        Update _a.Coverage = coverage
}

Step 11: Deductibles
{

    Document (_d)
        [(Deductible-Type, Deductible-Amount)]
        Wind-Excluded
        Coverage-Amount
        Replacement-Cost-Coverage        

    //# Deductible := AOP (All Other Peril), Peril Deductible, Clause 1 Deductible, Basic deductible
    deductible-amount = _d.Deductible-Amount

    //# Wind-Deductible := Windstorm, Clause 2 deductible, Tornado, Hurricane, Wind/Hail (W/H), Tropical Cyclone/ Tropical Occurrence
    If there are multiple _d.Wind-Deductible in Document# Then
        wind-deductible = max(_d.Wind-Deductible) 

    //# Ded. Clause 1&2: 500 500
    //# Implies deductibe-amount = 500 AND wind-deductible = 500

    //# Below all indicate -> Wind-Excluded = Yes
    //# Wind/Hail Exclusion Yes
    //# Hurricane NOT COVERED or $0 
    //# Wind Coverage: No

    Case _d.Wind-Excluded = Yes Then  
        _a.Wind-Excluded = Yes //# Update checkbox on

        If Carrier = 'California Fair Plan' AND State(Borrow-Property-Address) = 'CA' Then 
            _a.Wind-Excluded = No //# means Wind Included

    //# Below all indicate -> Wind-Excluded = No
    //# Wind Coverage Yes
    //# Wind/Hail Exclusion No
    //# Hurricane Deductible $9999.99 
    
    Case _d.Wind-Excluded = No AND _d.Wind-Deductible > 0 Then
        If _a.Wind-Excluded = Yes Then _a.Wind-Excluded = No 

    If _a.Wind-Excluded = Yes AND _d.Wind-Excluded = NoInfo Then
        //#? Refer Previous Document (Which Document / How to do?)
        If _prev.d.Wind-Excluded = No Then _a.Wind-Excluded = No

    If _d.Coverage-Amount is Empty AND _d.Deductible is Empty Then
        If _a.Policy-Type = 'Renewal' Then
            Do Nothing
            Dont Change any thing in App
        Else If _a.Policy-Type = 'New Policy' Then  //#?? MT and NB ?
            Keep Coverage
            Remove Deductible 
        End If
    End If

    If Replacement-Cost-Coverage = Yes Then
        _a.No-Replacement-Coverage = No
}

Step 12: Premium Amount
{
    If _a.Escrow = No Then
        Update Premium
        Payment is not required
        Roll dates as per doc //# ??

    If _a.Escrow = Yes Then

        If Policy-Term-Year is Same AND Payment-Made = True 
            AND _d.Premium-Amount > _a.Premium-Amount Then
            v.additional_amount_due = _d.Premium-Amount - _a.Premium-Amount

        //# Incomplete    
        If _d.Payment-Due-Immediately Then

            chk_premium_amount 
            chk_overnight_for_premium_amount

            chk_additional_amount_due
            chk_overnight_for_additional_amount_due      
            chk_additional_payment_manual_check
            
            chk_funding_only
            funding_only_comment
}



