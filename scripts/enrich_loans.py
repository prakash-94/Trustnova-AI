"""
Loan Data Enrichment Script
============================
Fixes two problems in the loans table:
  1. Zero rejected loans — unrealistic for any bank portfolio
  2. Empty notes field — no approval/rejection reasoning anywhere

What this script does:
  - Adds ~90 rejected loan records (realistic 25-30% rejection rate)
  - Writes detailed notes to ALL loans:
      active  → "Approved: [specific criteria met]"
      pending → "Under Review: [what's being evaluated]"
      closed  → "Closed: [repaid / refinanced / etc.]"
      rejected→ "Declined: [specific reason]"
  - Updates purpose fields with more specific descriptions

Applies changes to BOTH:
  - Local SQLite (banking.db) for dev
  - Render PostgreSQL (via DATABASE_URL env var) for production

Usage:
    python scripts/enrich_loans.py
    python scripts/enrich_loans.py --pg-only    # skip SQLite
    python scripts/enrich_loans.py --sqlite-only # skip PostgreSQL
"""

import os, sys, random, uuid
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parent.parent
_candidate = ROOT / "data" / "banking.db"
SQLITE_PATH = _candidate if _candidate.exists() else ROOT / "banking.db"

PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://trusnova_ai_db_user:d67OeJyggmJnozW49ScKBykUMyVPqUsC"
    "@dpg-d8ovslkvikkc7393sipg-a.oregon-postgres.render.com/trusnova_ai_db",
)

random.seed(42)

# ── Approval notes by loan type ───────────────────────────────────────────────

APPROVAL_NOTES = {
    "auto": [
        ("Approval Decision — Application Approved Following Full Credit Committee Review. "
         "The Credit Committee has completed a thorough evaluation of this auto loan application and is pleased to confirm approval of financing in the requested amount. "
         "The applicant's credit score of {cs} exceeds TrustNova's minimum threshold of 660 for standard auto lending and falls within the prime credit tier, indicating a strong and consistent repayment history. "
         "The applicant's debt-to-income ratio of {dti}% is comfortably within the allowable guideline of 50%, confirming that existing monthly obligations remain manageable alongside the proposed new payment. "
         "An independent vehicle appraisal has been completed and confirms a fair market value of ${val:,}, producing an LTV ratio of {ltv}% — within the bank's maximum collateral threshold. "
         "Employment at the current employer has been verified and confirmed at {emp}+ years, establishing the income stability required to service a {term}-month obligation. "
         "The loan has been originated at a fixed interest rate of {rate}% for the approved term. All closing documents are ready for execution."),

        ("Approval Decision — Auto Loan Approved; Strong Credit File and Co-Applicant Support. "
         "Following a comprehensive review of the application, supporting financial documentation, and vehicle details, the Credit Committee has approved this auto loan application. "
         "The applicant presents a strong credit profile with no delinquencies recorded in the past 36 months across all open trade lines, demonstrating a reliable and consistent repayment pattern that satisfies TrustNova's underwriting standards. "
         "The debt-to-income ratio of {dti}% is within acceptable parameters, and the inclusion of a co-applicant's verified income provides additional repayment capacity that further strengthens the overall risk profile. "
         "The dealership invoice has been reviewed and the vehicle identification number has been verified and cross-referenced against lien records, confirming no pre-existing encumbrances on the collateral. "
         "Financing has been approved on a {term}-month term at a fixed rate of {rate}%. "
         "The Credit Committee thanks the applicant for their business and looks forward to a successful lending relationship."),

        ("Approval Decision — Auto Loan Approved; All Prime Lending Criteria Satisfied. "
         "After a detailed review of all submitted documentation, the Credit Committee has determined that this application meets all criteria established under TrustNova Auto Lending Policy for standard prime loan origination. "
         "The applicant's credit score of {cs} positions the application firmly in the prime borrower tier, supported by a clean payment history and a manageable existing debt profile. "
         "Employment with the current employer has been independently verified at {emp}+ years of continuous service, with confirmed annual gross income of ${income:,}, which comfortably supports the proposed monthly obligation. "
         "The requested loan amount falls within the approved financing range relative to the independently confirmed vehicle value, ensuring adequate collateral coverage throughout the loan term. "
         "The loan has been approved at a fixed interest rate of {rate}% for the agreed term, with monthly payments structured to remain within the applicant's demonstrated repayment capacity. "
         "All required disclosures have been provided and the loan is ready to fund upon receipt of signed documentation."),

        ("Approval Decision — Certified Pre-Owned Vehicle Financing Approved. "
         "The Credit Committee has completed its review of this auto loan application and is pleased to confirm full approval for the financing of the stated certified pre-owned vehicle. "
         "A comprehensive vehicle history report has been obtained and reviewed, confirming a clean title history with no reported accidents, odometer rollback concerns, or unresolved salvage designations. "
         "The vehicle's age and condition fall within TrustNova's certified pre-owned financing eligibility criteria, and the LTV ratio of {ltv}% is within the 110% maximum permitted for this vehicle classification. "
         "The applicant's established banking relationship of 3+ years with TrustNova has been reviewed and reflects consistent deposit activity with no non-sufficient funds incidents, which provides additional confidence in the applicant's financial management habits. "
         "Relationship pricing has been applied where applicable. The loan has been originated at {rate}% for a {term}-month term."),
    ],
    "home": [
        ("Approval Decision — Mortgage Application Approved; Excellent Qualifying Profile. "
         "Following a comprehensive underwriting review conducted in accordance with TrustNova Mortgage Policy and applicable conforming loan guidelines, the Credit Committee is pleased to confirm approval of this home loan application. "
         "The applicant presents an outstanding credit profile with a score of {cs} and a verified history of on-time mortgage and installment payments spanning seven or more consecutive years — well in excess of the depth and consistency required for prime mortgage origination. "
         "An independent appraisal has confirmed the subject property's fair market value at ${val:,}, producing an LTV ratio of {ltv}% at the requested loan amount — comfortably within conforming guidelines. "
         "Verified W-2 income of ${income:,} annually has been confirmed via tax transcripts and employer records, and the applicant's back-end DTI of {dti}% is within FNMA conforming limits. "
         "The down payment has been verified via three months of bank statements, confirming that all funds to close are sourced and seasoned. "
         "The loan has been approved at a fixed rate of {rate}% for the approved term. Estimated closing timeline is within standard parameters."),

        ("Approval Decision — Conforming Mortgage Approved; All FNMA Eligibility Criteria Met. "
         "The Credit Committee has completed its review and confirmed that this mortgage application satisfies all eligibility requirements for a conforming loan under current Fannie Mae guidelines and TrustNova Mortgage Underwriting Standards. "
         "The applicant's credit score of {cs} reflects a disciplined borrowing history, and all existing debt obligations produce a back-end DTI of {dti}% — within the conforming 43% back-end limit and reflecting strong overall debt management. "
         "A title search has been completed and returned clear, with no outstanding liens, encumbrances, or ownership disputes identified against the subject property. "
         "Homeowner's insurance binder has been received and reviewed, confirming adequate coverage effective from the anticipated closing date. "
         "A flood zone determination has been completed per federal requirements. "
         "The loan is approved at a fixed rate of {rate}% and the estimated closing date has been communicated to all parties. All required federal disclosures have been provided within regulatory timeframes."),

        ("Approval Decision — FHA-Eligible Mortgage Approved; Minimum Down Payment Program Utilized. "
         "Following review under TrustNova's FHA-eligible loan program guidelines and applicable HUD underwriting requirements, the Credit Committee has approved this mortgage application. "
         "The applicant's credit score of {cs} exceeds the 580-point floor required for the 3.5% minimum down payment program, and the down payment has been verified in the applicant's deposit accounts with sufficient seasoning to confirm the funds are not borrowed. "
         "An FHA-approved appraisal has been ordered and completed; the appraiser has confirmed that the subject property meets HUD Minimum Property Standards with no required repairs identified that would prevent closing. "
         "The applicant's employment history reflects continuous employment within the same industry for two or more years, satisfying FHA's employment stability requirements. "
         "Upfront and annual mortgage insurance premium obligations have been fully disclosed and the applicant has acknowledged receipt of all required disclosures. "
         "The loan is approved and is ready to proceed to closing upon satisfaction of all standard pre-closing conditions."),

        ("Approval Decision — Jumbo Mortgage Approved; Enhanced Underwriting Standards Satisfied. "
         "The Credit Committee has completed an enhanced underwriting review appropriate for a jumbo loan origination and is pleased to confirm approval of this application. "
         "Jumbo loan origination requires a more stringent qualification profile than conforming products, and the applicant has satisfied all heightened criteria. "
         "The applicant's credit score of {cs} exceeds the 720-point minimum required for jumbo eligibility, and the credit file reflects a long and unblemished repayment history consistent with the premier borrower classification. "
         "Liquid post-closing reserves have been verified at {emp}+ months of principal, interest, taxes, and insurance — well above the minimum reserve requirement of six months established under TrustNova's jumbo underwriting guidelines. "
         "The applicant's back-end DTI of {dti}% is below the 38% cap applied to jumbo originations, providing a meaningful buffer against income variability. "
         "Two independent appraisals have been obtained per jumbo policy; both values are within 2% of each other, confirming the integrity of the collateral valuation. The loan is approved."),

        ("Approval Decision — Rate-and-Term Refinance Approved; Strong Equity Position Confirmed. "
         "The Credit Committee has reviewed this refinance application and confirmed approval for a rate-and-term refinance of the existing mortgage obligation. "
         "The applicant's existing loan is in excellent standing, with {emp} consecutive on-time payments recorded without a single delinquency — a payment history that speaks to the applicant's commitment to the current obligation. "
         "An independent appraisal of the subject property has confirmed sufficient equity to support the refinance at an LTV of {ltv}%, well within the maximum threshold for a rate-and-term refinance without mortgage insurance. "
         "The new loan is being originated at a fixed rate of {rate}%, which will reduce the applicant's estimated monthly payment by approximately ${val:,} relative to the existing loan — resulting in meaningful long-term interest savings over the remaining amortisation period. "
         "No cash proceeds are being extracted in this transaction; the refinance is strictly a rate improvement. All required closing cost disclosures have been provided and the loan is ready to proceed."),
    ],
    "personal": [
        ("Approval Decision — Unsecured Personal Loan Approved; Strong Creditworthiness Confirmed. "
         "Following a thorough review of the applicant's credit profile, verified income documentation, and loan purpose, the Credit Committee has approved this unsecured personal loan application. "
         "The applicant's credit score of {cs} falls within the strong credit tier and is supported by a history of consistent on-time payments across all open accounts, with no bankruptcies filed in the past seven years and no accounts currently in collections. "
         "Verified annual income of ${income:,} has been confirmed via recent pay stubs and the most recent filed tax return, and the applicant's debt-to-income ratio of {dti}% is comfortably within TrustNova's 45% maximum for unsecured personal lending. "
         "The stated purpose of debt consolidation has been reviewed and is consistent with responsible financial management — consolidating higher-rate obligations into a single, lower-rate personal loan is expected to reduce the applicant's overall monthly debt burden. "
         "The loan has been originated at a fixed rate of {rate}%, with all required TILA disclosures provided prior to final execution."),

        ("Approval Decision — Personal Loan Approved; Consistent Payment History and Adequate Income Verified. "
         "The Credit Committee has completed its review of this personal loan application and is pleased to confirm approval in the requested amount. "
         "The applicant's credit score of {cs} reflects a responsible credit history with consistent, on-time payment activity maintained across {emp} open trade lines, demonstrating the applicant's reliability in meeting existing financial obligations. "
         "The requested amount of ${val:,} is within the maximum unsecured limit applicable to the applicant's verified income bracket, ensuring that the proposed obligation remains proportionate to demonstrated repayment capacity. "
         "The selected loan term produces a monthly payment that is well within the applicant's capacity based on current income and existing obligations, providing a meaningful buffer against unexpected financial variability. "
         "The loan has been approved at a fixed rate of {rate}% for the agreed term. All required disclosures have been provided and the applicant has acknowledged receipt. Funds will be disbursed within two business days of final documentation execution."),

        ("Approval Decision — Personal Loan Approved; Existing Customer Relationship Pricing Applied. "
         "The Credit Committee has approved this personal loan application and has applied relationship-based preferential pricing in recognition of the applicant's longstanding and positive deposit relationship with TrustNova. "
         "The applicant has maintained an active deposit account with TrustNova for {emp}+ years, reflecting consistent account management and no non-sufficient funds incidents throughout the relationship tenure. "
         "The applicant's credit score of {cs} confirms creditworthiness within the approved tier, with no current delinquencies and no adverse credit events in the review period. "
         "The stated loan purpose of debt consolidation has been verified; payoff letters from the creditors being consolidated are on file and confirm that the loan proceeds will be directed exclusively to the retirement of existing high-rate obligations. "
         "A preferential rate of {rate}% has been applied in accordance with TrustNova's Relationship Pricing Policy, resulting in a lower effective rate than the standard grid for this credit tier. The loan is ready to fund."),

        ("Approval Decision — Personal Loan Approved on Expedited Basis; Medical Hardship Criteria Met. "
         "Pursuant to TrustNova's Medical Hardship Lending Policy, this personal loan application has been reviewed on an expedited basis and the Credit Committee has confirmed approval. "
         "The applicant has presented documented evidence of a qualifying medical expense — specifically, a hospital invoice confirming services rendered — which satisfies the hardship threshold for expedited processing and consideration of the maximum available term. "
         "The applicant's credit score of {cs} meets the minimum eligibility requirements for participation in the expedited review program, and income has been independently verified through two recent pay stubs, confirming adequate repayment capacity. "
         "A 60-month repayment term has been approved to reduce the monthly payment burden and improve affordability during what may be a period of financial strain. "
         "The approved rate of {rate}% reflects the applicant's current credit tier. All required disclosures, including the full cost-of-credit summary and right-to-rescind notice, have been provided. Funds will disburse upon completion of final execution."),
    ],
    "education": [
        ("Approval Decision — Education Loan Approved; Enrollment and Program Eligibility Confirmed. "
         "The Credit Committee has completed a review of this student loan application and is pleased to confirm approval for the requested education financing. "
         "Enrollment verification has been received directly from the institution's Registrar's Office, confirming that the applicant is actively registered in the stated program for the applicable academic term, as required for loan disbursement under TrustNova's Student Lending Policy. "
         "The co-signer's credit profile has been evaluated independently and satisfies all minimum creditworthiness standards applicable to private student lending, providing the secondary repayment assurance required under the program. "
         "The combined income of the applicant and co-signer has been assessed against the projected post-graduation repayment obligation, and the analysis supports a reasonable expectation of repayment capacity at anticipated graduation. "
         "A deferment period has been approved through the applicant's expected graduation date, during which no principal or interest payments are required. "
         "The loan is approved at a fixed rate of {rate}%. All required student loan disclosures, including the Loan Disclosure Statement and Borrower's Rights and Responsibilities, have been provided."),

        ("Approval Decision — Graduate Education Loan Approved; Extended Repayment Term Applied. "
         "After a thorough review of this graduate education loan application, the Credit Committee has confirmed approval and has authorised an extended repayment term based on the applicant's program type and projected post-graduation income. "
         "The applicant is enrolled in a graduate-level professional program at an accredited institution that qualifies for extended repayment terms of up to 180 months under TrustNova's Graduate Lending Policy, which recognises the higher earning potential typically associated with advanced professional degrees. "
         "The co-signer presents a strong credit profile with a score of {cs} and {emp}+ years of verified stable employment, providing robust secondary repayment assurance throughout the life of the loan. "
         "In-school interest capitalisation terms have been fully disclosed and the applicant and co-signer have both confirmed their understanding of the total cost-of-credit implications. "
         "The loan is originated at a fixed rate of {rate}%, and disbursement has been scheduled in accordance with the institution's tuition billing timeline."),

        ("Approval Decision — Student Loan Refinance Approved; Favourable Rate Reduction Achieved. "
         "The Credit Committee has reviewed this education loan refinance application and confirmed approval, resulting in a materially improved interest rate relative to the applicant's existing federal loan portfolio. "
         "The applicant holds {emp} existing federal student loan accounts, which will be fully consolidated into a single private refinance loan. Payoff instructions have been transmitted to each servicer and the full outstanding principal balance will be retired on the disbursement date. "
         "The new loan has been originated at a fixed rate of {rate}%, compared to a weighted average rate of {val}% across the existing portfolio — representing a meaningful reduction in the applicant's effective borrowing cost. "
         "Over the remaining repayment horizon, the rate reduction is projected to produce cumulative interest savings of approximately ${income:,}, significantly reducing the total cost of the applicant's education financing. "
         "All required refinance disclosures have been provided. The applicant has been informed that refinancing federal loans into a private loan results in the loss of federal borrower protections, including income-driven repayment options."),

        ("Approval Decision — Continuing Education Loan Approved; Employer Reimbursement Documentation Received. "
         "Following review of this application under TrustNova's Continuing Education Lending Policy, the Credit Committee has approved financing for the stated professional certification program. "
         "The program has been assessed and confirmed as eligible under TrustNova's continuing education guidelines, which extend to accredited bootcamps and professional certification programs designed to enhance the applicant's existing professional competencies. "
         "A partial employer tuition reimbursement commitment letter has been received and reviewed; the employer has confirmed in writing that a specified portion of the program cost will be reimbursed upon successful completion, providing partial secondary repayment assurance. "
         "The applicant's credit score of {cs} meets the minimum threshold for this program, and the applicant's full-time employment status has been confirmed, indicating that loan repayment will not depend entirely on the outcome of the certification. "
         "A 24-month repayment term has been structured to align with a short-term programme timeline. The loan is approved at {rate}%, with first payment due 30 days after disbursement."),
    ],
    "business": [
        ("Approval Decision — Business Term Loan Approved; All Commercial Underwriting Criteria Satisfied. "
         "Following a comprehensive review of the business financial statements, personal financial disclosures of the guarantor(s), business credit report, and supporting documentation, the Credit Committee has approved this business term loan application. "
         "The business has been in continuous operation for more than three years, exceeding the 24-month minimum operating history required under TrustNova Commercial Lending Policy §4.1, and has demonstrated consistent revenue growth over the review period. "
         "Gross annual revenue of ${income:,} and a net operating margin of {dti}% support a Debt Service Coverage Ratio of 1.{emp}x, which exceeds the required minimum of 1.25x and provides an adequate buffer against revenue variability. "
         "A personal guarantee has been provided by the majority owner, whose personal credit score of {cs} meets the guarantor creditworthiness standards required for business credit origination. "
         "The loan has been approved at a fixed commercial rate of {rate}% for a {term}-month term. All UCC-1 filings and guarantee documentation will be executed at closing."),

        ("Approval Decision — SBA 7(a) Guaranteed Business Loan Approved. "
         "The Credit Committee has completed its review of this SBA 7(a) loan application and is pleased to confirm approval, subject to final SBA authorisation. "
         "The submitted business plan has been reviewed by TrustNova's commercial lending team and the financial projections have been assessed against current market conditions; the analysis supports a reasonable expectation that projected revenues are achievable within the stated timeframe. "
         "The guarantor's personal credit score of {cs} meets SBA eligibility requirements and confirms no prior SBA loan defaults or unresolved federal delinquencies. "
         "The proposed collateral package — consisting of business equipment and accounts receivable — has been assessed and, in conjunction with the SBA guarantee covering 75% of the outstanding balance, is sufficient to satisfy the bank's collateral requirements under the programme. "
         "The SBA guarantee reduces the bank's net credit exposure to a level consistent with an acceptable risk tier for this loan size and industry. "
         "Loan proceeds will be disbursed within 5 business days of SBA authorisation and completion of all closing conditions. Rate: Prime + {val}%."),

        ("Approval Decision — Business Equipment Financing Loan Approved. "
         "Following a review of this equipment financing application, the Credit Committee has confirmed approval for a specific-purpose equipment loan in the requested amount. "
         "The loan proceeds are designated exclusively for the acquisition of the equipment items detailed in the attached vendor invoice, which has been reviewed and accepted as part of the credit file. "
         "The financed equipment will serve as the primary collateral for this obligation, and a UCC-1 financing statement will be filed against the specific equipment upon loan origination to perfect the bank's first-priority security interest. "
         "The business has been in operation for {emp}+ years and the reviewed financial statements support a Debt Service Coverage Ratio of 1.{cs}x, which exceeds the required minimum for equipment financing. "
         "The equipment financing has been cross-collateralised with the business deposit account maintained at TrustNova to provide additional security. "
         "The loan is approved at a fixed rate of {rate}% for the agreed term. First payment is due 30 days from disbursement."),

        ("Approval Decision — Revolving Line of Credit Converted to Term Loan; Approved Based on Demonstrated Performance. "
         "The Credit Committee has reviewed this request for conversion of the existing business revolving line of credit to a fixed-term loan and has approved the conversion based on the business's demonstrated performance under the line. "
         "The business has utilised the revolving line of credit responsibly over {emp} months, with all draws repaid within agreed terms and no overdraft incidents recorded during the review period — a performance record that provides direct evidence of the business's ability to service a structured term obligation. "
         "The business's Dun & Bradstreet Paydex score satisfies TrustNova's business credit standards, and the business has delivered year-over-year revenue growth of {dti}% across each of the two most recently completed fiscal years. "
         "The owners have confirmed an equity injection of {val}% of the loan amount, further strengthening the overall credit profile. "
         "The term loan is approved at a fixed commercial rate of {rate}%, with monthly principal and interest payments commencing on the first day of the month following disbursement."),
    ],
}

PENDING_NOTES = {
    "auto": [
        ("Application Under Review — Vehicle Verification and Employment Confirmation in Progress. "
         "This auto loan application has been received, logged, and assigned to an underwriter for full review. "
         "A preliminary credit assessment has been completed; the applicant's credit score of {cs} falls within the reviewable range and the credit file has been forwarded to the underwriting team for detailed analysis. "
         "An independent vehicle appraisal has been ordered and is expected to be returned within two to three business days; the dealership invoice is currently being cross-referenced against published NADA values to confirm adequate collateral coverage. "
         "Employment verification is underway — verbal confirmation of the applicant's employment status and income level has been obtained from the stated employer, and written verification in the form of a signed employer letter is currently pending receipt. "
         "A debt-to-income calculation will be finalised upon confirmation of all verified liabilities. "
         "The applicant can expect a final credit decision within 2 to 3 business days from receipt of all outstanding documentation. The assigned loan officer will be in contact with any further information requests."),

        ("Application Under Review — Additional Documentation Required; Review Temporarily Paused. "
         "This auto loan application has been received and an initial credit review has been completed. "
         "The applicant's credit score of {cs} places the application in a review tier that requires additional supporting documentation before the Credit Committee can render a final decision. "
         "Specifically, the underwriting team has requested two recent pay stubs covering the most recent 60-day period and a written employer contact reference to facilitate independent employment and income verification. "
         "Additionally, due to the marginal credit profile, the loan officer has presented the applicant with the option of including a creditworthy co-applicant, which would provide additional income support and potentially improve the overall qualifying profile. "
         "The application review has been temporarily paused pending receipt of the requested documents. "
         "Once all required documentation has been received and verified, the file will be advanced to the Credit Committee for a final lending determination. No adverse action has been taken at this stage."),

        ("Application Under Review — Vehicle History Report Ordered; Liability Verification Pending. "
         "This auto loan application is currently in active underwriting review. "
         "A vehicle history report has been ordered through a certified provider and is expected to be returned within one business day; this report will confirm the vehicle's accident history, title status, odometer reading record, and any open recall items relevant to the collateral assessment. "
         "A preliminary credit review of the applicant's file has returned a favourable result at a score of {cs}, indicating the applicant's general creditworthiness meets the initial threshold for further review. "
         "The debt-to-income calculation is currently in progress; the underwriter has identified several liabilities listed on the application that require third-party verification before the final DTI figure can be confirmed. "
         "The file has been scheduled for a loan committee review upon completion of all outstanding verification items. "
         "The applicant is advised to ensure that all listed debts and obligations are accurately reflected on the application to avoid delays in the final decision process."),
    ],
    "home": [
        ("Application Under Review — Appraisal Ordered; Title Search and Income Verification in Progress. "
         "This mortgage application has been received and assigned to a senior underwriter for full review. "
         "All income documentation submitted to date — including W-2 forms, recent pay stubs, and the prior year's tax return — has been reviewed and is consistent with the income stated on the application. "
         "A third-party licensed appraiser has been engaged and assigned to the subject property; the appraisal report is expected to be returned within seven business days, at which point the LTV calculation and final collateral review can be completed. "
         "A title search has been ordered with a licensed title company; results are expected within five business days and will be reviewed for any encumbrances, liens, or ownership defects. "
         "A flood zone determination has been requested for the subject property as required by federal law. "
         "The applicant's credit score of {cs} is within the conforming loan approval range and no material adverse credit events have been identified during the preliminary review. The loan officer will provide a status update upon receipt of the appraisal report."),

        ("Application Under Review — Full Underwriting Package Received; Awaiting Appraisal Report. "
         "This mortgage application is currently in the final stage of underwriting review. "
         "The complete underwriting package has been received, including all required income documentation, asset statements, employer verification letters, and identification documents; all submitted items have been reviewed and verified and are consistent with the information declared on the loan application. "
         "The applicant's credit score of {cs} has been confirmed through a tri-merge credit report and all existing liabilities have been validated against the information on file. "
         "The only outstanding item preventing a final credit decision is the return of the independent appraisal report, which was ordered {emp} days ago and is expected to be returned shortly. "
         "A property survey has also been requested by the applicant's attorney and is currently being reviewed alongside the title search results. "
         "The Credit Committee will render a final decision within two business days of receiving the completed appraisal report. The underwriter will notify the applicant and the loan officer upon receipt."),

        ("Application Under Review — Conditional Approval Issued; Three Outstanding Conditions Remain. "
         "Following an initial underwriting review, the Credit Committee has issued a Conditional Approval for this mortgage application, subject to satisfactory resolution of the following outstanding conditions prior to the final approval and clear-to-close determination. "
         "First, a fully executed and compliant gift letter is required to document the source of the down payment funds, as a portion of the verified funds to close appears to be sourced from a family member; the gift letter must satisfy FNMA documentation requirements and confirm that no repayment is expected. "
         "Second, a 12-month landlord reference letter from the applicant's current landlord is required to document rental payment history. "
         "Third, a written explanation letter addressing a credit inquiry that appeared on the tri-merge credit report approximately four months prior to this application is required; the letter must identify the creditor and explain the purpose of the inquiry. "
         "The applicant's credit score of {cs} is within the approved range. All three conditions must be satisfied before the loan can progress to closing."),
    ],
    "personal": [
        ("Application Under Review — DTI Verification in Progress; Applicant Clarification Requested. "
         "This personal loan application has been received and assigned to the personal lending underwriting team for review. "
         "An initial credit assessment has been completed; the applicant's credit score of {cs} places the application in a borderline review tier that requires a more detailed analysis of the full debt load before a final lending determination can be made. "
         "The underwriting team is currently in the process of calculating the applicant's total debt-to-income ratio based on all verified liabilities. "
         "During this review, two liabilities listed on the application were found to have discrepancies when compared against trade line data appearing on the credit report — specifically, the outstanding balances stated on the application appear to differ from the balances reported by the respective creditors. "
         "The applicant has been contacted and asked to provide clarification and, where applicable, recent account statements to reconcile the discrepancy. "
         "A review of the applicant's bank statements is also currently in progress. The file will be advanced to the Credit Committee upon resolution of the outstanding clarification items."),

        ("Application Under Review — Contractor Documentation Requested for Home Improvement Purpose. "
         "This personal loan application has been received and is currently under review by the personal lending underwriting team. "
         "The applicant's credit profile has been reviewed and the credit score of {cs} is within the satisfactory range for unsecured personal lending. Income has been verified via submitted pay stubs and employer records and is consistent with the figures stated on the application. "
         "The stated loan purpose is home improvement. TrustNova's personal lending policy requires that home improvement loans above a specified threshold be supported by a contractor estimate or scope-of-work documentation confirming that the requested amount is commensurate with the planned improvements. "
         "The underwriter has requested that the applicant provide a written contractor quote or scope-of-work description itemising the planned improvements and associated costs. "
         "The application review has been temporarily paused pending receipt of this supporting documentation. "
         "Once the contractor documentation has been received and reviewed, the underwriter will finalise the DTI assessment and advance the file to the Credit Committee for a final decision."),

        ("Application Under Review — Senior Underwriter Review Requested; Inquiry Pattern Under Assessment. "
         "This personal loan application is currently in underwriting review and has been escalated for senior underwriter assessment due to a credit inquiry pattern identified during the initial credit review. "
         "The applicant's credit score of {cs} is within the review range; however, the credit report reflects three personal loan-related credit inquiries within the preceding 60-day period, indicating that the applicant may have applied for personal financing at multiple institutions concurrently. "
         "This pattern raises the possibility that the applicant's total outstanding and pending unsecured debt obligations may be materially higher than what is currently reflected on the credit report, as newly approved loans may not yet appear as open trade lines. "
         "A senior underwriter has been assigned to complete a detailed assessment of the applicant's aggregate potential unsecured exposure before a final decision is rendered. "
         "Additionally, an enhanced income verification has been ordered to confirm that repayment capacity is adequate even if some or all of the pending applications have been approved. "
         "The applicant will be notified of the final decision within 3 to 5 business days."),
    ],
    "education": [
        ("Application Under Review — Enrollment Verification and Co-Signer Credit Review in Progress. "
         "This education loan application has been received and is currently in active review by the student lending team. "
         "An official enrollment verification letter has been requested from the institution's Registrar's Office to confirm that the applicant is actively registered in the stated program for the upcoming academic term; this verification is a mandatory prerequisite for any disbursement of education loan funds and typically requires 3 to 5 business days to process. "
         "The co-signer application has been received and the co-signer credit review is currently in progress; the preliminary credit check has returned a score of {cs}, which is being evaluated against TrustNova's co-signer eligibility criteria. "
         "Income and employment information provided by the co-signer is also being independently verified. "
         "The loan officer will notify both the applicant and co-signer of the outcome of the co-signer credit review within two business days. "
         "A final credit decision will be issued within 5 business days of receipt of all outstanding verification items, including the enrollment confirmation from the Registrar."),

        ("Application Under Review — Institution Eligibility and Cost of Attendance Verification in Progress. "
         "This education loan application has been received and assigned to the student lending underwriting team. "
         "An eligibility review is currently being conducted to confirm that the stated educational institution appears on the U.S. Department of Education's Title IV approved school list, which is a required condition for private education loan origination under TrustNova's Student Lending Policy. "
         "Confirmation of institution eligibility is expected within two business days. "
         "The applicant's credit profile has been reviewed; the credit score of {cs} is within the assessable range and no material adverse credit events have been identified at this stage of the review. "
         "The institution has been contacted and asked to provide a formal Cost of Attendance breakdown for the stated program and enrollment period, which is required to confirm that the requested loan amount does not exceed certified educational expenses. "
         "Additionally, the applicant's financial aid award letter has been requested to assess the role of other funding sources and to determine the appropriate private loan disbursement amount. "
         "The applicant will be notified of a final decision once all outstanding items have been resolved."),
    ],
    "business": [
        ("Application Under Review — Business Financials Under Analysis; Third Year of Tax Filings Requested. "
         "This business loan application has been received and assigned to a commercial underwriter for full review. "
         "CPA-prepared financial statements have been received and reviewed for two of the three required fiscal years; TrustNova's Commercial Lending Policy §4.2 requires three years of financial statements for business loans above the stated threshold, and the underwriter has formally requested the outstanding third year from the applicant's accountant. "
         "Unaudited revenue figures of ${income:,} annually have been noted in the interim, though these figures will be subject to confirmation upon receipt of the full financial package. "
         "The guarantor's personal credit score of {cs} has been obtained and is under review alongside the business credit report. "
         "A site inspection of the primary business location has been scheduled for next week; the site visit is a standard requirement for commercial loans of this type and will be conducted by a member of the commercial lending team. "
         "The file will be presented to the Credit Committee for a final decision within five business days of receipt of all outstanding documentation."),

        ("Application Under Review — SBA Pre-Qualification and Environmental Review in Progress. "
         "This SBA 7(a) loan application has been received and is currently progressing through the multi-step pre-qualification and underwriting process applicable to government-guaranteed business lending. "
         "The business plan has been submitted and has been reviewed by TrustNova's commercial lending team; the plan's financial projections are currently being assessed against current market and industry data to evaluate their reasonableness. "
         "The guarantor's personal credit score of {cs} has been obtained and confirms eligibility in the preliminary SBA pre-qualification assessment; no prior SBA defaults or unresolved federal delinquencies have been identified. "
         "A formal business credit report has been ordered through Dun & Bradstreet and is expected to be returned within two business days. "
         "An environmental review of the subject property proposed as collateral has been initiated, as required for real property collateral under SBA lending guidelines; completion is expected within 10 business days. "
         "SBA pre-qualification is expected to be submitted within 3 business days of receipt of all outstanding items."),

        ("Application Under Review — DSCR Analysis in Progress; Additional Revenue Documentation Requested. "
         "This business loan application has been received and is currently in the final stages of underwriting review by TrustNova's commercial lending team. "
         "All primary documentation — including business tax returns, CPA-prepared financial statements, bank statements, and personal financial disclosures of the guarantor(s) — has been received and verified. "
         "The underwriter is in the process of completing the Debt Service Coverage Ratio analysis, which is a key determinant of approval eligibility for business term lending. "
         "A preliminary DSCR calculation of 1.{cs}x has been derived from the submitted financial statements; this figure is at the borderline of TrustNova's required minimum of 1.25x, and the underwriter has determined that additional revenue documentation from the most recent quarter is required to confirm whether the current DSCR calculation is reflective of the business's ongoing operating trend. "
         "The applicant has been contacted and asked to provide the requested quarterly financials. "
         "The completed file will be presented to the loan committee for a final credit decision within 3 business days of receipt of the additional documentation."),
    ],
}

CLOSED_NOTES = {
    "auto": [
        "Closed — Repaid in full on {date}. {term}-month loan completed {emp} months early. No late payments recorded. Title lien released; copy mailed to customer.",
        "Closed — Loan paid off upon vehicle trade-in. Payoff amount received from dealership on {date}. Account in good standing throughout tenure. Lien released same day.",
        "Closed — Refinanced with external lender. Payoff received {date}. Account had 0 late payments. Customer eligible for loyalty pricing on future applications.",
    ],
    "home": [
        "Closed — Mortgage satisfied in full. Final payoff received {date} (property sale proceeds). All escrow funds disbursed. Title company sent lien release to county recorder.",
        "Closed — Refinanced into lower-rate product. Payoff amount {val} received from new lender {date}. Customer retained; new loan originated in same cycle.",
        "Closed — 15-year fixed-rate mortgage repaid at maturity. Final payment received {date}. Excellent payment history — 0 late payments across {term} installments. Satisfaction of mortgage recorded.",
    ],
    "personal": [
        "Closed — Personal loan repaid in full {date}. Customer made {term} consecutive on-time payments. No prepayment penalty assessed. Account closed in good standing.",
        "Closed — Early payoff. Customer settled balance {date}, {emp} months before maturity. Loan originated for debt consolidation — purpose fulfilled. No outstanding obligations.",
        "Closed — Settled. Account transferred to collections after 180 days past due; settled for {val}% of outstanding balance on {date}. Reported to credit bureaus per policy.",
    ],
    "education": [
        "Closed — Student loan repaid. Grace period ended; repayment phase completed over {term} months with 0 delinquencies. Final payment received {date}.",
        "Closed — Transferred to federal servicer during income-driven repayment election. Balance transferred {date}; account closed on our books. No outstanding balance retained.",
    ],
    "business": [
        "Closed — Business term loan repaid at maturity. All {term} installments received on time. Business in good standing — eligible for future credit facilities.",
        "Closed — Early payoff via business sale proceeds. Payoff and prepayment fee received {date}. Personal guarantee released. UCC-1 termination statement filed.",
        "Closed — SBA loan fully repaid. SBA guarantee released {date}. Business operating continuously throughout term. Account referred to relationship manager for ongoing banking services.",
    ],
}

REJECTION_REASONS = {
    "auto": [
        ("dti_high",
         "Application Declined — Debt-to-Income Ratio Exceeds Policy Threshold. "
         "Following a thorough review of this application, the Credit Committee has determined that the applicant's current debt-to-income ratio of {dti}% materially exceeds the maximum allowable limit of 50% established under TrustNova Auto Lending Policy §3.2. "
         "The applicant's verified gross monthly income supports a maximum debt obligation of {dti}% of take-home pay; however, existing recurring obligations totalling ${obligations:,}/month combined with the proposed additional payment of ${payment:,}/month result in a combined ratio that falls outside acceptable risk parameters. "
         "The Credit Committee recommends the applicant work to reduce outstanding revolving and installment balances to bring the DTI below 45% prior to reapplication. "
         "A formal review may be requested after a minimum of six months of documented debt reduction. TrustNova remains committed to supporting this applicant's financing goals and encourages reapplication once the qualifying threshold has been met."),

        ("credit_score",
         "Application Declined — Credit Profile Does Not Meet Minimum Underwriting Standards. "
         "After careful evaluation of the applicant's credit report and supporting documentation, the Credit Committee has determined that the current credit score of {cs} falls below the minimum required threshold of 620 for standard auto loan origination. "
         "The file reflects two or more trade lines with delinquency status of 30 or more days past due within the most recent 12-month review period, indicating elevated repayment risk. "
         "Additionally, a pattern of late payment behaviour suggests that the current financial position may not support the proposed additional debt obligation at this time. "
         "The applicant is encouraged to bring all delinquent accounts current, maintain a consistent on-time payment record for a minimum of six consecutive months, and address any outstanding collection items. "
         "Upon demonstrating improvement in credit profile metrics, the applicant is welcome to submit a new application for reconsideration."),

        ("no_income",
         "Application Declined — Income Verification Could Not Be Completed. "
         "The Credit Committee has concluded its review and is unable to approve this application due to failure of the income verification process, a required step under TrustNova Lending Policy §5.1. "
         "The pay stubs provided were cross-referenced with employment records obtained through our third-party verification service and were found to contain material discrepancies that could not be resolved through the standard verification protocol. "
         "Furthermore, the applicant has declared self-employment income as the primary income source; however, only one year of federal tax returns has been submitted, whereas two full years are required to establish a verifiable income baseline for self-employed borrowers. "
         "The application has been marked incomplete and placed on hold. The applicant may resubmit with two years of signed tax returns, a current profit and loss statement, and three months of business bank statements."),

        ("ltv_high",
         "Application Declined — Loan-to-Value Ratio Exceeds Permissible Limit. "
         "Following underwriting review, the Credit Committee has determined that the requested loan amount of ${amount:,} exceeds the bank's allowable loan-to-value threshold for the collateral vehicle. "
         "An independent appraisal has placed the current NADA retail value of the subject vehicle at ${nada:,}, resulting in a loan-to-value ratio that surpasses the 110% maximum permitted under TrustNova Auto Lending Guidelines for vehicles classified as more than five model years old. "
         "This policy exists to ensure that the collateral adequately supports the loan balance in the event of repossession, protecting both the institution and the borrower from negative equity exposure. "
         "To proceed, the applicant may consider making an additional down payment of at least ${shortfall:,} to bring the LTV within policy, or alternatively, selecting a newer vehicle whose appraisal value more closely aligns with the financing requested."),

        ("employment",
         "Application Declined — Insufficient Employment History at Current Position. "
         "After reviewing the application file in its entirety, the Credit Committee has determined that the applicant does not currently meet TrustNova's employment stability requirements for auto loan origination. "
         "Our standard underwriting guidelines require that applicants demonstrate a minimum of 12 consecutive months of employment with their current employer prior to loan origination. "
         "The applicant has been employed in the current role for only {months} months, which falls below this threshold. "
         "Furthermore, the file reflects a prior employment gap of {gap} months that was not adequately explained or documented, raising additional concerns regarding income continuity. "
         "Lenders rely on demonstrated employment stability as a key indicator of an applicant's ability to sustain regular loan payments over the full term. "
         "The applicant is encouraged to reapply after reaching the 12-month employment milestone and is advised to maintain uninterrupted employment until that time."),

        ("thin_file",
         "Application Declined — Insufficient Credit History to Support Underwriting Decision. "
         "Following a thorough review of the applicant's credit profile, the Credit Committee has determined that there is insufficient credit history to make a lending determination consistent with TrustNova's standard underwriting practices. "
         "The applicant's credit file reflects only {tradelines} open trade line(s), all of which were established within the past eleven months. "
         "TrustNova's auto loan underwriting guidelines require a minimum of two years of established credit history across at least two distinct trade lines to evaluate repayment behaviour over a meaningful period. "
         "A thin credit file does not necessarily reflect poor creditworthiness; however, it limits the institution's ability to assess risk with the confidence required for unsecured or collateral-backed lending. "
         "The applicant is advised to establish additional credit accounts — such as a secured credit card or credit-builder loan — maintain zero delinquencies, and reapply after 12–18 months of demonstrated positive payment history."),
    ],
    "home": [
        ("dti_high",
         "Application Declined — Debt-to-Income Ratios Exceed Conforming Loan Limits. "
         "After a comprehensive underwriting review conducted in accordance with Fannie Mae conforming loan guidelines and TrustNova Mortgage Policy, the Credit Committee has determined that this application does not meet the required debt-to-income standards. "
         "The applicant's front-end housing ratio of {fe_dti}% and back-end total obligation ratio of {dti}% both exceed the permissible conforming limits of 28% and 43% respectively. "
         "The proposed monthly principal, interest, taxes, and insurance payment of ${housing:,} alone consumes an unacceptably high proportion of the applicant's verified gross monthly income of ${income:,}. "
         "These ratios indicate that adding a mortgage obligation in the requested amount would create a material financial strain and significantly elevate the risk of payment default. "
         "The applicant may improve eligibility by paying down existing debt obligations, increasing verified income, or applying for a lower loan amount that brings DTI ratios within conforming parameters."),

        ("appraisal",
         "Application Declined — Independent Appraisal Does Not Support Requested Loan Amount. "
         "Following the completion of an independent appraisal of the subject property conducted by a licensed, third-party appraiser engaged by TrustNova, the Credit Committee has determined that the loan cannot be approved as submitted. "
         "The appraisal has established a fair market value of ${appraisal:,} for the subject property, which is ${shortfall:,} below the agreed purchase price of ${price:,}. "
         "The resulting loan-to-value ratio at the requested amount would exceed TrustNova's maximum LTV threshold for this product type. "
         "An attempt was made to negotiate a price reduction with the seller; however, the seller has declined to adjust the contract price. "
         "As the applicant has indicated they are unable to fund the appraisal gap with personal funds, the transaction cannot proceed on its current terms. "
         "The applicant is advised to renegotiate the purchase price, identify alternative properties, or source additional equity funds to bridge the identified gap before reapplying."),

        ("credit_score",
         "Application Declined — Credit Profile Does Not Satisfy Conventional Mortgage Requirements. "
         "Following a complete underwriting review of the mortgage application and supporting documentation, the Credit Committee has determined that the applicant's current credit profile does not meet the minimum standards established under TrustNova Mortgage Underwriting Guidelines and conventional loan requirements. "
         "The applicant's credit score of {cs} falls below the 620-point minimum required for conventional mortgage origination. "
         "Additionally, a Chapter 7 bankruptcy was discharged {months} months ago; TrustNova's mortgage policy mandates a minimum post-discharge seasoning period of 48 months before a conventional mortgage application may be considered. "
         "This seasoning requirement is designed to ensure that applicants have had adequate time to rebuild their credit profile and demonstrate sustained financial responsibility following a significant credit event. "
         "The applicant is encouraged to focus on credit rehabilitation during the intervening period and is eligible to reapply as early as {reapply_date}, provided all other eligibility criteria are met at that time."),

        ("employment",
         "Application Declined — Self-Employment Income Does Not Meet Verification Requirements. "
         "The Credit Committee has concluded its review of this mortgage application and is unable to approve the loan due to inability to establish verifiable qualifying income, as required under TrustNova Mortgage Policy §6.3 for self-employed borrowers. "
         "The applicant has declared self-employment as the primary income source; however, federal tax documentation covering only 14 months of business operation has been provided. "
         "TrustNova's underwriting guidelines require a minimum of two full years of self-employment tax history to calculate a stable, annualised qualifying income baseline. "
         "Furthermore, the net income figures reported across the available period exhibit significant fluctuation — ranging from ${low:,} to ${high:,} — making it impractical to establish a consistent qualifying income without the full two-year documentation set. "
         "The applicant is advised to maintain detailed financial records, file complete tax returns for all applicable years, and reapply once the two-year documentation threshold has been satisfied."),

        ("title_issue",
         "Application Declined — Subject Property Title Is Not in Insurable Condition. "
         "Following completion of the title search and review of supporting property documentation, the Credit Committee has determined that the subject property's title is not in a condition that satisfies TrustNova's clear title requirement for mortgage origination. "
         "The title search has revealed an outstanding mechanics lien of ${lien:,} recorded against the property that the current seller has not resolved or arranged to discharge at settlement. "
         "In addition, a boundary dispute with the adjacent parcel has been identified and remains unresolved at the county level, creating a cloud on title that a title insurance underwriter has declined to insure at standard rates. "
         "TrustNova policy requires that all liens be discharged and all title defects be resolved prior to loan closing to protect the institution's first-lien position. "
         "The applicant is advised to work with the seller and their respective legal counsel to resolve all outstanding title matters before this application can be reconsidered for approval."),

        ("assets",
         "Application Declined — Verified Liquid Assets Insufficient to Cover Required Closing Funds. "
         "After a detailed review of the applicant's asset documentation, including bank statements, investment account records, and submitted gift fund documentation, the Credit Committee has determined that verified liquid assets are insufficient to satisfy the funds-to-close requirement for this mortgage transaction. "
         "The total verified funds to close, including down payment, closing costs, prepaid items, and required post-closing reserves, amount to ${required:,}. "
         "The applicant's verified liquid asset balance stands at ${available:,}, creating an uncovered shortfall of ${shortfall:,}. "
         "While gift funds were submitted to partially address this shortfall, the accompanying gift letter does not satisfy the FNMA documentation requirements — specifically, it lacks the donor's signed certification that no repayment is expected — and therefore cannot be counted as verified funds under agency guidelines. "
         "The applicant must either source additional verified liquid assets or provide a fully compliant gift letter before this application can be advanced."),

        ("fraud_flag",
         "Application Declined — Material Income Discrepancy Identified During Underwriting Review. "
         "During the course of underwriting review, the Credit Committee identified a significant discrepancy between income figures declared on the loan application and those reflected in tax transcripts obtained directly from the Internal Revenue Service via IRS Form 4506-C. "
         "The applicant's stated annual income on the application is ${stated:,}; however, the IRS transcript reports taxable income of ${actual:,} for the most recent filed tax year — a material variance that could not be reconciled through the standard documentation review process. "
         "In accordance with TrustNova's fraud prevention protocol and Anti-Money Laundering Policy, this application has been escalated to the Compliance and Fraud Review Team for further investigation. "
         "The applicant has been formally notified of this escalation. No adverse action has been taken pending the outcome of the internal review. "
         "The applicant is advised to cooperate fully with the Compliance Team and to provide any requested documentation to support income verification."),
    ],
    "personal": [
        ("dti_high",
         "Application Declined — Total Debt Obligation Exceeds Unsecured Lending Threshold. "
         "After a thorough review of the applicant's financial profile, the Credit Committee has determined that this personal loan application cannot be approved based on the applicant's current debt-to-income position. "
         "The applicant's verified monthly obligations currently total ${obligations:,}, and the proposed loan would add an estimated payment of ${payment:,}/month, bringing the combined debt-to-income ratio to approximately {combined_dti}%. "
         "TrustNova's Unsecured Personal Lending Policy §2.4 establishes a maximum allowable DTI of 45% for unsecured credit products. "
         "Without the backing of collateral, the institution bears the full credit risk of the obligation, which makes adherence to this threshold essential to sound risk management. "
         "The applicant is advised to reduce outstanding balances on existing debt obligations before reapplying. "
         "Alternatively, the applicant may wish to explore a smaller loan amount that, combined with existing obligations, would bring the total DTI within the approved range."),

        ("credit_score",
         "Application Declined — Credit Profile Reflects Elevated Repayment Risk. "
         "Following a complete review of the applicant's credit report and financial documentation, the Credit Committee has determined that the applicant's current credit profile does not meet the minimum standards required for unsecured personal loan origination at TrustNova. "
         "The applicant's credit score of {cs} reflects a history of adverse credit events, including three accounts currently placed with collection agencies carrying a combined outstanding balance of ${collections:,}, and one charged-off account that was written off within the past 24 months. "
         "These indicators collectively represent a pattern of elevated default risk that is inconsistent with TrustNova's credit standards for unsecured lending products. "
         "The Credit Committee recommends that the applicant prioritise resolution of all collection accounts, negotiate settlements or payment arrangements where possible, and maintain a spotless payment record for a sustained period of no less than 12 consecutive months prior to reapplication. "
         "We remain available to assist the applicant in identifying credit improvement resources."),

        ("stacking",
         "Application Declined — Multiple Concurrent Loan Applications Identified; Aggregated Unsecured Exposure Exceeds Permissible Limit. "
         "During the underwriting review process, the Credit Committee identified that the applicant has submitted loan applications to {other_lenders} additional financial institutions within the preceding 30-day period, with approved commitments totalling ${other_loans:,} not yet reflected in the applicant's current credit report. "
         "This practice, commonly referred to as application stacking, creates a risk profile that is materially different from what the credit report alone would suggest. "
         "When the aggregate of approved pending commitments and the current requested amount are combined, the applicant's projected total unsecured exposure exceeds the income-based borrowing limit established under TrustNova Unsecured Lending Policy. "
         "The Credit Committee cannot approve additional unsecured credit under these circumstances, as doing so would expose the applicant to a debt burden that poses a significant risk of financial hardship. "
         "The applicant is encouraged to allow all newly originated obligations to be reflected on the credit report and to demonstrate repayment capacity before seeking additional unsecured credit."),

        ("employment",
         "Application Declined — Verifiable Income Cannot Be Established. "
         "Following a complete review of the application and all submitted documentation, the Credit Committee has determined that this personal loan application cannot be approved due to an inability to establish verifiable, stable income sufficient to support the requested debt obligation. "
         "The applicant's employment records indicate termination from their most recent salaried position {months} months prior to the date of this application. "
         "The application lists the current income source as self-employment; however, no supporting documentation — including tax filings, business bank statements, or client contracts — has been provided to substantiate self-employment income at the level required to qualify for the requested loan amount. "
         "TrustNova's personal lending guidelines require that all income used for qualification be fully documented and verifiable. "
         "The applicant is encouraged to reapply after accumulating a minimum of six consecutive months of verifiable employment or documented self-employment income supported by the required documentation package."),

        ("thin_file",
         "Application Declined — Credit History Insufficient to Support Unsecured Lending Decision. "
         "After reviewing the applicant's credit profile and accompanying financial documentation, the Credit Committee has determined that the applicant does not possess the established credit history required to qualify for an unsecured personal loan under TrustNova's standard underwriting criteria. "
         "The applicant's credit file contains only {tradelines} active installment account(s), with a combined credit history spanning {months} months, and no revolving credit accounts of any kind. "
         "An unsecured personal loan represents a significant extension of credit without the protection of collateral, and as such, it requires a demonstrated credit track record across multiple account types to allow for a reliable risk assessment. "
         "The Credit Committee is unable to make a lending determination based solely on the available limited credit data. "
         "The applicant is advised to consider beginning with a secured credit product — such as a credit-builder loan or a secured credit card — to establish a broader and longer credit history, and to reapply once a more robust credit profile can be presented."),
    ],
    "education": [
        ("cosigner",
         "Application Declined — Creditworthy Co-Signer Required; Application Submitted Without One. "
         "After reviewing this education loan application in accordance with TrustNova Student Lending Policy, the Credit Committee has determined that the application cannot be approved as submitted. "
         "The primary applicant has a credit file that is less than 12 months old, with no established history of repayment across any trade lines. "
         "While a newly established credit file does not preclude eligibility, TrustNova's student loan guidelines require that all applicants with limited credit history provide a creditworthy co-signer — a responsible adult with a credit score of at least 660 and a demonstrated history of on-time payments — to co-sign the obligation and provide secondary repayment assurance. "
         "This application was submitted without a co-signer, and therefore does not satisfy the minimum eligibility requirements for approval. "
         "The applicant is encouraged to identify a suitable co-signer and resubmit the application, or to explore federal student loan options through FAFSA, which do not require a credit check or co-signer for most borrowers."),

        ("enrollment",
         "Application Declined — Educational Institution Not Listed on Approved Title IV Eligible School Registry. "
         "Following a review of this education loan application, the Credit Committee has determined that the named institution does not appear on the U.S. Department of Education's list of Title IV-approved schools, which is a mandatory eligibility requirement under TrustNova's Student Lending Guidelines and applicable federal consumer lending regulations. "
         "TrustNova's education loan products are designed to support attendance at accredited, Title IV-eligible institutions. "
         "This policy exists to protect borrowers by ensuring that loan proceeds are directed toward programs that meet established quality and accreditation standards, and that students retain access to federal student aid protections and consumer rights. "
         "The applicant is advised to verify the accreditation and Title IV eligibility status of the intended institution directly with the school's financial aid office or through the official U.S. Department of Education database. "
         "If the institution is found to be eligible, the applicant is welcome to resubmit the application with supporting accreditation documentation."),

        ("credit_score",
         "Application Declined — Co-Signer Credit Profile Does Not Meet Minimum Eligibility Requirements. "
         "Following a credit review of both the primary applicant and the co-signer named on this education loan application, the Credit Committee has determined that the co-signer's credit profile does not satisfy the minimum standards required under TrustNova Student Lending Policy. "
         "The co-signer's current credit score of {cs} falls below the minimum threshold of 620, which is required to provide adequate repayment assurance for a private education loan without federal backing. "
         "In addition, the co-signer's credit report reflects two accounts with delinquency of 60 or more days past due within the most recent 24-month period, which indicates an elevated risk of future payment default. "
         "A co-signer is expected to serve as a reliable secondary source of repayment and must meet creditworthiness standards independently. "
         "The applicant is advised to identify an alternative co-signer who meets the minimum credit requirements, or to explore federal loan options through FAFSA, which may be available regardless of credit history."),

        ("program",
         "Application Declined — Requested Loan Amount Exceeds Certified Cost of Attendance. "
         "After completing a review of this education loan application and cross-referencing the requested amount against the Cost of Attendance certification provided by the institution, the Credit Committee has determined that the requested loan amount of ${amount:,} exceeds the certified Cost of Attendance for the stated academic program, which has been officially documented by the institution at ${coa:,} for the applicable enrollment period. "
         "TrustNova's education lending policy strictly limits disbursements to the certified Cost of Attendance to prevent over-borrowing and to comply with federal and state regulations governing the use of education loan proceeds. "
         "Disbursing funds beyond certified educational expenses could expose the applicant to unfavourable tax treatment and would be inconsistent with responsible lending practices. "
         "The applicant may resubmit a revised application requesting a loan amount not to exceed ${coa:,}. "
         "This institution is prepared to process and fund a compliant request promptly upon receipt of the corrected application."),

        ("no_enrollment",
         "Application Declined — Active Enrollment Status Could Not Be Confirmed for the Stated Academic Term. "
         "Following receipt and review of this education loan application, the Credit Committee initiated enrollment verification through the institution's Registrar's Office as required under TrustNova's disbursement eligibility procedures. "
         "The Registrar has formally confirmed that the applicant is not registered as an active student in the program stated on the loan application for the upcoming academic term. "
         "Disbursement of education loan proceeds is contingent upon verified, active enrollment in an eligible program at an approved institution, as required by both TrustNova's internal lending policy and applicable consumer lending regulations. "
         "Funding a loan in the absence of confirmed enrollment would violate the stated purpose of the loan and could expose the applicant to default risk in the event the educational program is not pursued. "
         "The applicant is advised to confirm their enrollment status with the institution's Registrar and, once active enrollment is established, resubmit the application with an updated enrollment verification letter."),
    ],
    "business": [
        ("operating_history",
         "Application Declined — Business Does Not Meet Minimum Operating History Requirement. "
         "Following a detailed review of this business loan application, the Credit Committee has determined that the applicant business does not satisfy TrustNova's minimum operating history threshold for commercial term loan origination. "
         "The business has been in operation for {months} months; TrustNova's Commercial Lending Policy §4.1 requires a minimum of 24 consecutive months of active business operations, supported by at least two full fiscal years of tax filings, before a term loan may be originated. "
         "This requirement reflects the elevated risk profile associated with early-stage businesses, which statistically demonstrate significantly higher failure rates during their first two years of operation than established enterprises. "
         "While the revenue trajectory presented in the business plan is encouraging, the absence of sufficient historical financial data makes it impractical to substantiate projected cash flows with the level of confidence required for prudent credit underwriting. "
         "The applicant is encouraged to reapply after reaching the 24-month milestone and is advised to maintain meticulous financial records in the interim. "
         "In the meantime, the applicant may wish to explore TrustNova's Microenterprise Lending Program, which offers tailored financing solutions for qualifying early-stage businesses."),

        ("dscr",
         "Application Declined — Debt Service Coverage Ratio Falls Below Minimum Required Threshold. "
         "After a comprehensive analysis of the business's financial statements, tax returns, and 12-month bank statement history, the Credit Committee has determined that this business loan application cannot be approved based on an insufficient Debt Service Coverage Ratio. "
         "The DSCR has been calculated at {dscr:.2f}x, which falls below TrustNova's required minimum of 1.25x for commercial term loan origination. "
         "The DSCR measures the degree to which a business's net operating income exceeds its total debt service obligations — a ratio below 1.00x indicates that the business generates less income than is required to service its existing debt, while the required 1.25x minimum provides the institution with a 25% margin of safety against income variability. "
         "At the current ratio, the addition of the proposed loan obligation would expose the business to a meaningful risk of payment default in the event of any revenue shortfall, seasonal downturn, or unexpected operating expense. "
         "The Credit Committee recommends that the applicant focus on revenue growth and operating expense reduction initiatives to improve net income before reapplying for term financing."),

        ("credit_score",
         "Application Declined — Adverse Personal and Business Credit History; Outstanding Tax Liens Remain Unresolved. "
         "Following a review of both the business credit profile and the personal credit history of the business owner(s), the Credit Committee has determined that this application does not meet TrustNova's creditworthiness standards for commercial lending. "
         "The guarantor's personal credit score of {cs} reflects a history of adverse credit events, including two federal tax liens filed within the past five years carrying a combined outstanding balance of ${lien:,}. "
         "TrustNova's commercial lending policy requires that all federal and state tax liens be fully satisfied and released prior to origination of any business credit facility, as unresolved tax liens take priority over the institution's lien position and significantly impair our ability to collect in the event of default. "
         "In addition, the business's Dun & Bradstreet Paydex score is insufficient to qualify under current risk standards. "
         "The applicant is advised to arrange full payment or release of all outstanding tax liens and to work with the business's trade creditors to improve the business credit rating before reapplying."),

        ("collateral",
         "Application Declined — Collateral Coverage Is Inadequate to Secure the Requested Loan Amount. "
         "After conducting a thorough assessment of the assets proposed as collateral for this business loan, the Credit Committee has determined that the collateral package does not provide sufficient security to support the requested financing amount. "
         "An appraisal of the business's tangible assets — including equipment, inventory, and accounts receivable — has established a combined liquidation value of ${assets:,}. "
         "TrustNova's Commercial Lending Policy requires a minimum collateral coverage ratio of 1.0x for secured business term loans, meaning that the liquidation value of pledged assets must fully cover the outstanding loan balance. "
         "At the appraised value, the current collateral package supports only a fraction of the requested amount, leaving a meaningful unsecured exposure that the Credit Committee cannot accept under present risk parameters. "
         "The real property initially offered as additional collateral was found to carry an existing first-priority lien in favour of another creditor, leaving no unencumbered equity available to pledge. "
         "The applicant is advised to identify additional unencumbered collateral or reduce the requested loan amount to align with available collateral value."),

        ("cash_flow",
         "Application Declined — Business Cash Flow Is Insufficient to Service the Proposed Debt Obligation. "
         "Following a detailed analysis of 12 months of business bank statements and the most recently filed business tax returns, the Credit Committee has determined that the business's current cash flow position does not support the addition of the proposed loan payment obligation. "
         "The analysis reveals an average monthly net cash inflow of ${flow:,} after operating expenses, which is materially below the estimated monthly debt service payment of ${payment:,} required under the proposed loan structure. "
         "Furthermore, the business's cash flow profile exhibits pronounced seasonal variability, with {months} consecutive months per year during which net cash flow is negative — periods during which the business would be reliant on cash reserves or credit facilities to meet basic operating and debt service obligations. "
         "Originating additional term debt under these conditions would expose the business to a significant and foreseeable risk of payment default. "
         "The Credit Committee recommends that the applicant consider a reduced loan amount, explore a seasonal revolving line of credit product better suited to the business's cash flow pattern, or reapply after demonstrating sustained improvement in monthly net cash flow metrics."),

        ("fraud_flag",
         "Application Declined — Material Discrepancy Identified Between Stated and Verified Financial Information; Compliance Review Initiated. "
         "During the course of underwriting review, the Credit Committee identified a significant and unexplained discrepancy between the financial information declared on the loan application and data obtained through independent third-party verification sources. "
         "Specifically, the revenue figures stated on the application exceed the income reported on the business's most recent federal tax filings by a material margin, and the discrepancy could not be reconciled through the standard documentation review process. "
         "In addition, the business address listed on the loan application does not correspond to the address of record filed with the applicable Secretary of State office, raising concerns regarding the accuracy of the application's representations. "
         "Pursuant to TrustNova's Fraud Prevention and Bank Secrecy Act compliance obligations, this application has been escalated to the Internal Compliance and Fraud Risk Management Team for formal review. "
         "The applicant has been notified of this escalation and is obligated to cooperate fully with all information requests from the Compliance Team. No further credit decisions will be made on this file pending the outcome of the review."),
    ],
}

PURPOSE_MAP = {
    "auto": [
        "Purchase of 2022 Toyota Camry SE — private party sale",
        "New vehicle purchase — 2024 Honda CR-V EX-L (dealer financing)",
        "Pre-owned 2020 Ford F-150 XLT, certified pre-owned program",
        "Auto refinance — lower rate from existing 11.5% to market rate",
        "Motorcycle purchase — 2023 Harley-Davidson Street Glide",
        "Commercial van for business use — 2023 Ford Transit 250",
        "Used SUV purchase — 2021 Jeep Grand Cherokee Limited",
        "Classic vehicle restoration loan — 1969 Ford Mustang fastback",
    ],
    "home": [
        "Purchase of primary residence — single-family home, 3BR/2BA",
        "Home purchase — new construction, builder contract attached",
        "Refinance of existing mortgage — rate-and-term, no cash-out",
        "Cash-out refinance for home improvement projects",
        "Vacation/second home purchase — lakefront property",
        "Investment property purchase — duplex, rental income plan",
        "Jumbo loan — luxury primary residence purchase",
        "FHA first-time homebuyer purchase — 3.5% down",
    ],
    "personal": [
        "Debt consolidation — 6 credit cards and 2 store accounts",
        "Home improvement — kitchen remodel and bathroom renovation",
        "Medical expenses — surgical procedure not covered by insurance",
        "Emergency fund replenishment following job loss",
        "Wedding expenses — venue, catering, and honeymoon",
        "Moving expenses — interstate relocation for new employment",
        "Adoption expenses — legal fees and agency costs",
        "HVAC system replacement — home emergency repair",
    ],
    "education": [
        "Undergraduate tuition — State University, Computer Science program",
        "Graduate school — MBA program, private institution",
        "Professional certification — CPA exam prep and licensing fees",
        "Coding bootcamp — 6-month full-stack development program",
        "Student loan refinance — consolidating 4 existing federal loans",
        "Medical school tuition — year 2 of 4-year MD program",
        "Law school expenses — JD program, 2nd year funding",
        "Trade school — HVAC technician certification program",
    ],
    "business": [
        "Working capital — seasonal inventory build-up for Q4",
        "Equipment purchase — CNC machining center for manufacturing",
        "Business expansion — opening second retail location",
        "Commercial real estate — purchase of office building",
        "SBA 7(a) loan — business acquisition (asset purchase)",
        "Technology upgrade — ERP system implementation",
        "Franchise acquisition — fast food franchise purchase and build-out",
        "Payroll bridge — temporary cash flow gap during growth phase",
    ],
}


def _fill(template: str, loan_type: str, amount_cents: int, interest_rate: float, term_months: int) -> str:
    """Fill a note template with plausible values derived from the loan."""
    amount = amount_cents // 100
    cs = random.randint(660, 780)
    dti = random.randint(22, 42)
    ltv = random.randint(65, 95)
    emp = random.randint(2, 8)
    income = random.randint(55_000, 180_000)
    val = random.randint(amount // 10, amount // 5) if amount > 10_000 else random.randint(500, 5_000)
    dp = random.randint(5, 25)

    return template.format(
        cs=cs, dti=dti, ltv=ltv, emp=emp, income=income,
        val=val, dp=dp, rate=interest_rate, term=term_months,
        amount=amount,
        # rejection-specific
        obligations=random.randint(2_000, 6_000),
        payment=max(1, round((amount_cents / 100) / (term_months or 60), 0)).__int__(),
        combined_dti=dti + random.randint(10, 20),
        nada=int(amount * 0.85),
        shortfall=int(amount * 0.15),
        months=random.randint(3, 11),
        gap=random.randint(6, 18),
        tradelines=random.randint(1, 3),
        fe_dti=random.randint(29, 40),
        housing=random.randint(1_800, 4_500),
        appraisal=int(amount * 0.88),
        price=amount,
        reapply_date="January 2026",
        low=random.randint(30_000, 60_000),
        high=random.randint(80_000, 150_000),
        lien=random.randint(5_000, 40_000),
        required=int(amount * 0.08),
        available=int(amount * 0.05),
        stated=int(income * 1.35),
        actual=income,
        collections=random.randint(2_000, 15_000),
        other_lenders=random.randint(2, 4),
        other_loans=random.randint(10_000, 35_000),
        coa=int(amount * 0.7),
        dscr=random.uniform(0.80, 1.20),
        dbs=random.randint(25, 48),
        assets=int(amount * 0.55),
        coverage=random.randint(40, 75),
        flow=random.randint(500, 2_500),
        tax=income,
        # closed-specific
        date=f"{random.randint(2020,2024)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
    )


def _approval_note(loan_type: str, amount_cents: int, interest_rate: float, term_months: int) -> str:
    templates = APPROVAL_NOTES.get(loan_type, APPROVAL_NOTES["personal"])
    tpl = random.choice(templates)
    return _fill(tpl, loan_type, amount_cents, interest_rate, term_months)


def _pending_note(loan_type: str, amount_cents: int, interest_rate: float, term_months: int) -> str:
    templates = PENDING_NOTES.get(loan_type, PENDING_NOTES["personal"])
    tpl = random.choice(templates)
    return _fill(tpl, loan_type, amount_cents, interest_rate, term_months)


def _closed_note(loan_type: str, amount_cents: int, interest_rate: float, term_months: int) -> str:
    templates = CLOSED_NOTES.get(loan_type, CLOSED_NOTES["personal"])
    tpl = random.choice(templates)
    return _fill(tpl, loan_type, amount_cents, interest_rate, term_months)


def _rejection_note(loan_type: str, amount_cents: int, interest_rate: float, term_months: int) -> str:
    reasons = REJECTION_REASONS.get(loan_type, REJECTION_REASONS["personal"])
    _, tpl = random.choice(reasons)
    return _fill(tpl, loan_type, amount_cents, interest_rate, term_months)


def _random_purpose(loan_type: str) -> str:
    return random.choice(PURPOSE_MAP.get(loan_type, PURPOSE_MAP["personal"]))


def _random_date_str(start_year=2018, end_year=2024) -> str:
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    return (start + timedelta(days=random.randint(0, (end - start).days))).isoformat()


# ── SQLite enrichment ─────────────────────────────────────────────────────────

def enrich_sqlite():
    import sqlite3
    if not SQLITE_PATH.exists():
        print(f"  SQLite DB not found at {SQLITE_PATH}, skipping.")
        return

    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1. Update notes + purpose for all existing loans
    print("  [SQLite] Updating notes + purpose for existing loans…")
    rows = cur.execute("SELECT id, loan_type, status, amount_cents, interest_rate, term_months FROM loans").fetchall()
    for row in rows:
        lid, lt, status, amt, rate, term = row["id"], row["loan_type"], row["status"], row["amount_cents"], row["interest_rate"], row["term_months"]
        rate  = rate  or 6.5
        term  = term  or 60
        if status == "active":
            note    = _approval_note(lt, amt, rate, term)
        elif status == "pending":
            note    = _pending_note(lt, amt, rate, term)
        elif status == "closed":
            note    = _closed_note(lt, amt, rate, term)
        else:
            note    = _rejection_note(lt, amt, rate, term)
        purpose = _random_purpose(lt)
        cur.execute("UPDATE loans SET notes=?, purpose=? WHERE id=?", (note, purpose, lid))

    # 2. Fetch customer IDs to attach rejected loans to real customers
    # SQLite uses customer_id; PostgreSQL uses id
    col = "customer_id" if "customer_id" in [d[1] for d in cur.execute("PRAGMA table_info(customers)").fetchall()] else "id"
    customer_ids = [r[0] for r in cur.execute(f"SELECT {col} FROM customers").fetchall()]
    if not customer_ids:
        print("  [SQLite] No customers found — skipping rejected loan insertion.")
        con.commit(); con.close(); return

    # 3. Insert ~90 rejected loans
    print("  [SQLite] Inserting rejected loans…")
    loan_types = ["auto", "home", "personal", "education", "business"]
    type_config = {
        "auto":      {"min": 800_000,   "max": 6_000_000,   "rate_lo": 7.5,  "rate_hi": 16.0, "terms": [36, 48, 60, 72]},
        "home":      {"min": 10_000_000,"max": 80_000_000,  "rate_lo": 6.0,  "rate_hi": 8.5,  "terms": [120, 180, 240, 360]},
        "personal":  {"min": 100_000,   "max": 4_000_000,   "rate_lo": 10.0, "rate_hi": 24.0, "terms": [12, 24, 36, 60]},
        "education": {"min": 500_000,   "max": 10_000_000,  "rate_lo": 3.5,  "rate_hi": 7.5,  "terms": [60, 120, 180]},
        "business":  {"min": 2_000_000, "max": 50_000_000,  "rate_lo": 6.5,  "rate_hi": 13.0, "terms": [24, 36, 60, 84]},
    }
    # ~18 per loan type = ~90 total
    inserted = 0
    for lt in loan_types:
        cfg = type_config[lt]
        for _ in range(18):
            amt   = random.randint(cfg["min"], cfg["max"])
            rate  = round(random.uniform(cfg["rate_lo"], cfg["rate_hi"]), 2)
            term  = random.choice(cfg["terms"])
            mpay  = int(amt / term * (1 + rate / 1200))
            cdate = _random_date_str()
            note  = _rejection_note(lt, amt, rate, term)
            purpose = _random_purpose(lt)
            cur.execute("""
                INSERT INTO loans
                  (id, customer_id, loan_type, status, purpose, notes,
                   amount_cents, outstanding_balance_cents,
                   interest_rate, term_months, monthly_payment_cents,
                   collateral, origination_date, maturity_date, created_at)
                VALUES (?,?,?,?,?,?, ?,?, ?,?,?, ?,?,?,?)
            """, (
                uuid.uuid4().hex[:8],
                random.choice(customer_ids),
                lt, "rejected", purpose, note,
                amt, 0,
                rate, term, mpay,
                None, cdate, None, cdate + "T00:00:00",
            ))
            inserted += 1

    con.commit()
    con.close()
    print(f"  [SQLite] Done — updated {len(rows)} loans, inserted {inserted} rejected loans.")


# ── PostgreSQL enrichment ─────────────────────────────────────────────────────

def enrich_postgres():
    try:
        import psycopg2, psycopg2.extras
    except ImportError:
        print("  psycopg2 not installed — skipping PostgreSQL.")
        return

    try:
        pg = psycopg2.connect(PG_URL)
    except Exception as e:
        print(f"  Could not connect to PostgreSQL: {e}")
        return

    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Update notes + purpose for all existing loans
    print("  [PostgreSQL] Updating notes + purpose for existing loans…")
    cur.execute("SELECT id, loan_type, status, amount_cents, interest_rate, term_months FROM loans")
    rows = cur.fetchall()
    updates = []
    for row in rows:
        lid, lt, status = row["id"], row["loan_type"], row["status"]
        amt   = row["amount_cents"] or 0
        rate  = row["interest_rate"] or 6.5
        term  = row["term_months"] or 60
        if status == "active":
            note = _approval_note(lt, amt, rate, term)
        elif status == "pending":
            note = _pending_note(lt, amt, rate, term)
        elif status == "closed":
            note = _closed_note(lt, amt, rate, term)
        else:
            note = _rejection_note(lt, amt, rate, term)
        purpose = _random_purpose(lt)
        updates.append((note, purpose, lid))

    plain_cur = pg.cursor()
    psycopg2.extras.execute_batch(
        plain_cur,
        "UPDATE loans SET notes=%s, purpose=%s WHERE id=%s",
        updates,
    )
    pg.commit()
    print(f"  [PostgreSQL] Updated {len(updates)} loans.")

    # 2. Fetch customer IDs
    cur.execute("SELECT id FROM customers LIMIT 500")
    customer_ids = [r["id"] for r in cur.fetchall()]
    if not customer_ids:
        print("  [PostgreSQL] No customers found — skipping rejected loan insertion.")
        pg.close(); return

    # 3. Check how many rejected loans already exist
    cur.execute("SELECT COUNT(*) as cnt FROM loans WHERE status='rejected'")
    existing_rejected = cur.fetchone()["cnt"]
    if existing_rejected >= 80:
        print(f"  [PostgreSQL] Already has {existing_rejected} rejected loans — skipping insertion.")
        pg.close(); return

    # 4. Insert ~90 rejected loans
    print("  [PostgreSQL] Inserting rejected loans…")
    loan_types = ["auto", "home", "personal", "education", "business"]
    type_config = {
        "auto":      {"min": 800_000,   "max": 6_000_000,   "rate_lo": 7.5,  "rate_hi": 16.0, "terms": [36, 48, 60, 72]},
        "home":      {"min": 10_000_000,"max": 80_000_000,  "rate_lo": 6.0,  "rate_hi": 8.5,  "terms": [120, 180, 240, 360]},
        "personal":  {"min": 100_000,   "max": 4_000_000,   "rate_lo": 10.0, "rate_hi": 24.0, "terms": [12, 24, 36, 60]},
        "education": {"min": 500_000,   "max": 10_000_000,  "rate_lo": 3.5,  "rate_hi": 7.5,  "terms": [60, 120, 180]},
        "business":  {"min": 2_000_000, "max": 50_000_000,  "rate_lo": 6.5,  "rate_hi": 13.0, "terms": [24, 36, 60, 84]},
    }
    new_loans = []
    for lt in loan_types:
        cfg = type_config[lt]
        for _ in range(18):
            amt   = random.randint(cfg["min"], cfg["max"])
            rate  = round(random.uniform(cfg["rate_lo"], cfg["rate_hi"]), 2)
            term  = random.choice(cfg["terms"])
            mpay  = int(amt / term * (1 + rate / 1200))
            cdate = _random_date_str()
            note  = _rejection_note(lt, amt, rate, term)
            purpose = _random_purpose(lt)
            new_loans.append((
                uuid.uuid4().hex[:8],
                random.choice(customer_ids),
                lt, "rejected", purpose, note,
                amt, 0,
                rate, term, mpay,
                None, cdate, None, cdate + "T00:00:00",
            ))

    psycopg2.extras.execute_batch(plain_cur, """
        INSERT INTO loans
          (id, customer_id, loan_type, status, purpose, notes,
           amount_cents, outstanding_balance_cents,
           interest_rate, term_months, monthly_payment_cents,
           collateral, origination_date, maturity_date, created_at)
        VALUES (%s,%s,%s,%s,%s,%s, %s,%s, %s,%s,%s, %s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, new_loans)
    pg.commit()
    pg.close()
    print(f"  [PostgreSQL] Done — inserted {len(new_loans)} rejected loans.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = set(sys.argv[1:])
    skip_sqlite = "--pg-only"     in args
    skip_pg     = "--sqlite-only" in args

    print("=== TrustNova Loan Data Enrichment ===\n")

    if not skip_sqlite:
        print("[1/2] Enriching SQLite (local dev)…")
        enrich_sqlite()
        print()

    if not skip_pg:
        print("[2/2] Enriching PostgreSQL (Render production)…")
        enrich_postgres()
        print()

    print("Done.")
