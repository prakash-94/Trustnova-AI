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
        "Approved: Credit score {cs} exceeds minimum threshold (660). Debt-to-income ratio {dti}% within guidelines. Vehicle appraised at ${val:,} — LTV ratio {ltv}%. Stable employment {emp}+ years verified. Rate locked at {rate}% for {term}-month term.",
        "Approved: Strong credit profile with no delinquencies in past 36 months. DTI ratio {dti}% acceptable. Dealership invoice confirmed; vehicle VIN verified. Co-applicant income adds additional repayment capacity. {term}-month term at {rate}%.",
        "Approved: Applicant meets all auto lending criteria. Credit score {cs} (prime tier). Employment verified at current employer {emp}+ years; gross income ${{income:,}}/yr. Requested amount within approved vehicle value range. Fixed rate {rate}%.",
        "Approved: Pre-owned vehicle (<5 years old), full CarFax report clear of accidents. LTV {ltv}% within 110% guideline for certified pre-owned. Applicant's banking relationship 3+ years — no NSF incidents. Rate: {rate}% / {term}mo.",
    ],
    "home": [
        "Approved: Excellent credit profile — score {cs}, no late payments 7 years. Property appraised at ${val:,} (LTV {ltv}%). Verified W-2 income ${income:,}/yr, DTI {dti}%. Down payment {dp}% confirmed via bank statement. Fixed rate {rate}% / {term}-month term.",
        "Approved: Conforming loan within FNMA limits. Credit score {cs}; debt obligations manageable at DTI {dti}%. Title search clear, no encumbrances. Homeowner's insurance binder received. Rate: {rate}% fixed for 30 years (est. closing {term}mo).",
        "Approved: FHA-eligible borrower. Credit score {cs} exceeds 580 floor; 3.5% down confirmed. Appraisal completed — property meets HUD minimum property standards. Mortgage insurance premium applied. Employment continuous 2+ years in same industry.",
        "Approved: Jumbo loan — enhanced underwriting applied. Credit score {cs} (required 720+). Reserves verified: {emp}+ months PITI in liquid accounts. DTI {dti}% below 38% jumbo cap. Two appraisals ordered per policy; both within 2% of each other.",
        "Approved: Refinance — appraised equity sufficient for rate-and-term refi. Existing loan in good standing ({emp} consecutive on-time payments). New rate {rate}% saves estimated ${val:,}/mo vs current loan. No cash-out; LTV {ltv}% post-refi.",
    ],
    "personal": [
        "Approved: Unsecured personal loan — credit score {cs} (strong tier). Stable income ${income:,}/yr; DTI {dti}% within policy limit (45%). No bankruptcy in past 7 years; 0 collections. Loan purpose (debt consolidation) reduces overall monthly obligation. Rate: {rate}%.",
        "Approved: Credit score {cs}; consistent payment history across {emp} open trade lines. Requested amount ${val:,} within unsecured limit for income bracket. 36-month term selected — estimated monthly payment well within capacity. Rate: {rate}%.",
        "Approved: Existing customer — positive deposit relationship {emp}+ years; average balance maintained. Credit score {cs}; no current delinquencies. Debt consolidation purpose verified (payoff letters on file). Preferential rate {rate}% applied for relationship pricing.",
        "Approved: Medical expense purpose — expedited review per hardship policy. Credit score {cs}; income verifiable via two recent pay stubs. Hospital invoice on file as supporting documentation. 60-month term approved at {rate}%.",
    ],
    "education": [
        "Approved: Student loan — enrollment verification received from institution. Credit score {cs} (co-signer applied, score {cs}). Combined income supports repayment estimate at graduation. Deferment period approved through expected graduation date. Rate: {rate}% fixed.",
        "Approved: Graduate-level education loan. Applicant's program (MBA, accredited university) qualifies for extended 180-month repayment term. Co-signer credit score {cs} with {emp}+ years stable employment. In-school interest capitalization terms disclosed. Rate: {rate}%.",
        "Approved: Refinance of existing student loans — better rate obtained. Original federal loans ({emp} accounts) consolidated; total payoff sent to servicers. New fixed rate {rate}% vs previous weighted average {val}%. Projected savings ${income:,} over loan life.",
        "Approved: Professional certification program — bootcamp eligible under continuing education policy. Employer tuition reimbursement letter on file (partial). Credit score {cs}; employed full-time while attending. Short-term 24-month repayment at {rate}%.",
    ],
    "business": [
        "Approved: Business term loan — 3 years operating history (required: 2). Gross revenue ${income:,}/yr; net margin {dti}%. Debt service coverage ratio 1.{emp}x (minimum 1.25x). Personal guarantee from majority owner (credit score {cs}). Rate: {rate}% / {term}-month term.",
        "Approved: SBA 7(a) guaranteed loan. Business plan reviewed; market analysis supports revenue projections. Personal credit score {cs}; no prior SBA default. Collateral: business equipment + receivables. SBA guarantee 75% applied — reduced bank risk tier. Rate: Prime + {val}%.",
        "Approved: Equipment financing — specific-purpose loan for listed equipment (invoice attached). Equipment serves as primary collateral (UCC-1 filing on origination). Business operating {emp}+ years, DSCR 1.{cs}x. Cross-collateralized with business deposit account. Rate: {rate}%.",
        "Approved: Business line of credit converted to term loan. Track record: {emp} months of clean draws with no overdrafts. Business credit score 78 (Dun & Bradstreet). Revenue growth {dti}% YoY (last 2 fiscal years). Owners' equity injection {val}% confirmed. Rate: {rate}%.",
    ],
}

PENDING_NOTES = {
    "auto": [
        "Under Review: Vehicle appraisal ordered; awaiting dealer invoice verification. Credit check complete (score {cs}). Employment verification in progress — verbal confirmation received, written confirmation pending. Est. decision: 2-3 business days.",
        "Under Review: Application received. Credit score {cs} — marginal tier; additional documentation requested. Applicant asked to provide 2 recent pay stubs and employer contact. Co-applicant option presented. Awaiting response.",
        "Under Review: VIN history report ordered. Preliminary credit review favorable (score {cs}). DTI calculation pending verification of all listed liabilities. Loan committee review scheduled.",
    ],
    "home": [
        "Under Review: Appraisal ordered — 3rd party licensed appraiser assigned; report expected within 7 business days. Title search in progress. Credit score {cs}; income documentation complete. Flood zone determination requested.",
        "Under Review: Full underwriting package received. Credit score {cs}; all income documents verified. Awaiting appraisal report (ordered {emp} days ago). Property survey requested by applicant's attorney — under review.",
        "Under Review: Conditional approval issued pending: (1) gift letter for down-payment funds, (2) 12-month landlord reference, (3) explanation letter for credit inquiry from 4 months ago. Credit score {cs}.",
    ],
    "personal": [
        "Under Review: Application complete. Credit score {cs} — borderline tier. Debt-to-income ratio being calculated; applicant asked to clarify two disputed liabilities. Bank statement analysis in progress.",
        "Under Review: Loan purpose (home improvement) — contractor quote requested to validate loan amount. Credit profile satisfactory (score {cs}). Income verified. Awaiting scope-of-work documentation.",
        "Under Review: Credit score {cs}. Stacking concerns flagged — applicant has 3 personal loan inquiries in past 60 days. Senior underwriter review requested. Additional income verification ordered.",
    ],
    "education": [
        "Under Review: Enrollment verification pending — official letter requested from registrar. Co-signer application received; co-signer credit check in progress (score {cs}). Expected turnaround: 5 business days.",
        "Under Review: Program eligibility review — verifying institution is on approved Title IV list. Applicant credit score {cs}. Cost of attendance breakdown requested. Financial aid award letter review pending.",
    ],
    "business": [
        "Under Review: Business financials under analysis — CPA-prepared statements received for 2 of 3 required years. Revenue ${income:,}/yr (unaudited). Personal credit score {cs}. Site inspection scheduled next week.",
        "Under Review: SBA pre-qualification in progress. Business plan submitted — reviewed by commercial lending team. Personal credit score {cs}; business credit report ordered. Environmental review for collateral property pending.",
        "Under Review: Loan committee review scheduled. All documentation received; underwriter completing DSCR analysis. DSCR preliminary at 1.{cs}x — borderline. Additional revenue documentation from applicant requested.",
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
