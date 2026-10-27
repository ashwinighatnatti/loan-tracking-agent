# Processing Rules for Document

Insurance tracking rules when procesing a document are described as follows.

```
Step# 1 - Pick 1 outstanding Document from queue (status: "TBP")
Step# 2 - Pick correct Loan to process
        - Between App and Document, Match Borrower, Co-Borrower 
        - Between App and Document, Match Property Address
Step# 3 -   If Number of Property: 1 of 1
                Pick default Collateral
            Else
                Pick correct Collateral in App based on Document Property address
Step# 4 - Pick correct Insurance Line (Hazard, Windstorm, Flood, Earthquake...) based on Document Policy Type
            If Line Not Found
                Create New Line
            If LenderPlaced Line Found and Hazard Policy received
                Create New Hazard Line (for ClientCo Only)
                
Example:

Document-Type: Renewal
Document-Source: EDI
Policy-Type: Hazard
Insurance-Line-Type: Hazard
```

# Functions

fn: create_new_line()
fn: 

# Early Exit Checks

Verify all conditions that may not result in successful record of document in App.


policy-suffix = MLR, ALR, FLR 
Action-Done {Status: Not Tracked, Comment: Prior servicer LP on file}

old-policy: 
Action-Done {Status: PNA ... }

name-disc: or  address-disc:
Action-Edit> Misc Inq 
if Comments say not acceptable then Action-Done { status: PNA, comment: }

# No

# Rules for Processing an Insurance Line

## Policy Number

Policy Number
- Remove spaces, special characters such as hyphen, hash.
- If Policy Suffix in (MLR, FLR, ALR) Then
  ToDo-Actions: Done { Status: Not Tracked, Comment: Prior servicer LP on file }  


## Escrow Status

Escrow Status = Yes or Y indicates loan is Escrowed
Escrow Status = No or N indicates loan is not Escrowed

## Term Dates

Determine the Policy Term dates from the document

Policy Term is defined as a period between two dates. 
An Insurance Policy Term, has a start date and an end date.
- the start date is called Effective-Date and 
- the end date is called Expiration-Date

Renewal Policy documents MUST have information for the below dates 
1. Effective-Date  = Date when the policy in the document is Effective from
2. Expiration-Date = Date when the policy in the document is Effective upto, or Expires.
   It is also known as Renewal-Date
3. Premium-Due-Date = Date when the Premium for the policy is due by

When Policy or Loan is Escrow = Yes
- Update only the Expiration Date 
- Update the policy term (12 Months, 1 Year etc) 

When Policy or Loan is Escrow = No
- Update Effective Date
- Update Expiration Date
- Update the policy term (12 Months, 1 Year etc) 

Compare Document Term Dates vs App Term Dates. Three scenarios

1. Old-Policy:
- When Document Term Dates are OLDER than App Term Dates

2. Same-Year-Policy:
- When Document Term year same as App Term year

3. Rewrite-Policy:
- When Document Term year and App Term year is same
- When Document Carrier and App Carrier is same
- When Document Policy# and App Policy# is different

4. Renewal-Policy:
- When Document-Term = Renewal-Term
- Current-Term is the term availabe from the App 
- Renewal-Term = Date range between Current-Term's Expiration-Date and 12 Months


For Renewal-Policy case: 
    When 60-120 day threshold rule is met Then
        - With Document-Term dates make a new term 
        - Rollback the term
        - Update the term in the App
        - Prepare the Payment

    When 60-120 day threshold rule is NOT met Then
        - With Document-Term dates make a new term
        - Update the term in the App
        - Do NOT prepare the payment

### Term Year Rollback 

During a Term year rollback procedure, Term years are rolled back by 1 year

Effective-Date = Effective-Date with Previous year
Expirtation-Date = Expiration-Date with Previous year
Premium-Due-Date = Premium Due Date with Previous year

## Cacellation Date& Reason

When Document Type is RENEWAL (with same carrier) with either Mid-Term or NewBiz scenario
 - Remove cancellation reason
 


## Coverage

Coverage Amount is amount against any of the below terms
- Coverage A
- Coverage A - Residence
- Building Property
- Building Property Coverage
- Building Coverage
- Dwelling Coverage
- Building Property Protection
- Additions and Alterations

If Coverage Amount NOT found AND Guranteed Replacement Cost is available Then
    Coverage Amount = UPB

Does NOT include below Coverages
- Personal Property 
- Personal Property Protection
- Loss of Rents
- Loss Assessement
- Any other coverage that does not concern with the collateral

Do NOT update App
- If Coverage Amount is NOT found in Document

## Deductibles

Determine Deductible Amount or Deductible Percentage

Deductible can be abbreviated as- Ded.
Read all instructions in the document to determine Deductible

Deductible (either Amount or Percentage) can be represented by any of the following
- All Other Peril (AOP)
- Peril Deductible
- Clause 1 Deductible
- Basic Deductible

Wind Deductible (either Amount or Percentage) can be represented by any of the following
- Windstorm
- Clause 2 deductible
- Tornado
- Hurricane
- Wind/Hail (W/H)
- Tropical Cyclone
- Tropical Occurrence

Eg. "Ded. Clause1&2" -indicates: Clause 1 Deductible & Clause 2 Deductible

When there are multiple Wind Deductible amounts in the document, choose the highest amount

## Exclusions

Wind Exclusion indicates that Wind/Hail damaages are excluded from the policy

When Wind Deductible Amount or percentage is NOT found  
- Wind Excluded = Yes

When Carrier is "California Fair Plan" AND Borrower property state is CA (California)
- Wind Exclusion = NO

For RENEWAL Document
- If Coverage and Deductibles amount is missing, keep the amount in App
For New policies (Mid-Term and NewBiz) 
- If the coverage and Deductibles amount is missing, keep coverage and remove deductibles in App 

## Replacement Cost Coverage

From document Check Replacement Cost Coverage 
    No Replacement Coverage = NOT ( Replacement Cost Coverage)

## Premium Amount

When Policy Term is the same AND 
When payment is already made for current term THEN 
    Additional Amount Due = Diff of (New Amount and Payment already made)

When Loan is Escrow
    Capture premium amount or additional due amount 
    Prepare payment if the 60-120 day threshold rule is met

When Loan is Non-Escrow 
    Capture premium amount or additional due amount
    Do NOT prepare payment even if the 60-120 day threshold is met

Overnight Payment Check:
    From Document Check if Premium Amount and/or Additional Due Amount should be paid overnight
    If Yes Then
        Mark the respective payments as Overnight

## Payment Preparation

Prepare payment in the following case
 - When Loan is Escrow 
 - When policy term-dates are within the 60-120 days threshold rule 
 
Do NOT prepare payment in the following case
 - When Loan is NOT Escrow
 - When difference between Closing-Date & Document-Effective-Date is less than 60 days
 - When policy term-dates are outside of the 60-120 days threshold rule 

### 60-120 day threshold rule:

Effective-Date is a date in mm/dd/yyyy
Current-Date or Processing-Date is Today's date in mm/dd/yyyy

 - Check Policy Effective-Date with Current-Date (or Processing-Date)
 - Check if Effective-Date is 60 days prior to Processing-Date or Effective-Date is 120 days after Processing-Date
 - Rule matches if Effective-Date is within the bounds
 - Rule does NOT match if Effective-Date is beyond the bounds

## Deficiencies

Turn Around time for Deficiencies
- 30 days  - for Mortgagee Claue (MCC), Name Insured, Property Address
- 24 hours - for Mid-Term

### MCC Deficiency: 

Mark a MCC deficiency in the following cases
- Lien position is different in the App and received Document
- When App report Lien position as 1st where as Document says Lien position is 2nd
- When the Mortgagee in document is different from the Mortgagee in the App
- Mortgagee details (MCC) mismatch in document
- Mortgagee Clause not updated in the document (not applicable for documents of type Invoice)
- For Email Fax and Scan - Full MCC clause is required (1st line and address). If not then mark deficiency

Do NOT mark a MCC deficiency in the following cases
- When a existing MCC deficiency is marked within past 30 days
- When App report Lien position as 2nd where as Document says Lien position is 1st
- For EDI and List Bill document types, Mortgagee, One line, is acceptable

Unmark an existing MCC deficiency
- When received a correct Mortgagee on document
- For Scan and Emai/Fax sources ISAOA/ATIMA line is mandatory to correct an existing MCC deficiency
- For Document types EDI and List Bill, One Line Mortgagee 

### Mid-Term Deficiency:
1. Mark Mid-Term deficiency when we have a Mid-Term policy scenario

### Deductible Deficiency: 
1. Hazard or Any Other Peril(AOP) or Wind: A Wind Deductible of 5% is acceptable. When deficiency is more than 5% of the coverage amount, a deficiency is marked
2. Earthquake: A 15% deficiency is acceptable. When deficiency is more than 15% of the coverage amount, a deficiency is marked 

## Status

### DONE

| Status                     | Scenario                                                        |  Comment                                                |
|----------------------------|-----------------------------------------------------------------|---------------------------------------------------------|
| COMPLETE                   | Loan updated with the policy information even if it was just a deficiency)| |
| ALREADY_ON_FILE            | Information recevied in the document is Already On File (AOF)| |
| ARCHIVE_AOF                | | |
| NOT_TRACKED                | | |
| PAID_IN_FULL               | Loan is fully paid off.|| 
| POLICY_NOT_ACCEPTED        | "Policy Not Accepted – Old Policy" - if a previous policy is received and not updated or used to cancel an Lender Placed policy||
| SOLD                       | Loan has been sold to another servicer| |


### EDIT

| Status                     | Scenario                                                        |  Comment                                                |
|----------------------------|-----------------------------------------------------------------|---------------------------------------------------------|
| INQUIRY                    | Borrower Name does not match or Borrower Address does not match |                                                         |
| BOA_HAZARD                 |||     
| CALL                 |||
| DISBURSEMENT                 |||
| HELOC                 |||
| LENDER_PLACED                 |||
| LIFE_OF_LOAN                 |||
| MANAGER_REVIEW                 |||
| MID_TERMS                 |||
| MISC                 |||
| PENDING                 |||
| RESEARCH_QUEUE                 |||
| RETURN_TO_CLIENT                 |||
| RETURN_TO_EXAMPLECO                 |||
| TO_BE_PROCESSED                 |||


### REJECT

| Status                     | Scenario                                                        |  Comment                                                |
|----------------------------|-----------------------------------------------------------------|---------------------------------------------------------|
| REJECT                     | Document is rejected |                                                         |
