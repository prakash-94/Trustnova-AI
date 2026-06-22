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
SQLITE_PATH = ROOT / "banking.db"

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
        ("dti_high",      "Declined: Debt-to-income ratio {dti}% exceeds maximum allowable 50% for auto loans. Combined existing monthly obligations (${obligations:,}) leave insufficient capacity for the requested additional payment of ${payment:,}/mo. Recommend reducing existing debt before reapplying."),
        ("credit_score",  "Declined: Credit score {cs} falls below minimum threshold of 620 for standard auto lending. Two or more accounts currently 30+ days past due. Application may be reconsidered after 6 months of on-time payments and score improvement."),
        ("no_income",     "Declined: Income verification failed. Provided pay stubs do not match employer records obtained during verification call. Self-employed income claimed — two years of tax returns required; only one year submitted. Application incomplete."),
        ("ltv_high",      "Declined: Requested loan amount ${amount:,} exceeds 120% of vehicle's NADA retail value (${nada:,}). Bank policy limits auto LTV to 110% for vehicles over 5 years old. Customer may resolve with larger down payment of ${shortfall:,} or newer vehicle."),
        ("employment",    "Declined: Applicant employed at current position for only {months} months; minimum 12 months required. Previous employment gap of {gap} months noted on application. Stable employment history not established."),
        ("thin_file",     "Declined: Insufficient credit history — only {tradelines} open trade lines, all opened within past 11 months. Minimum 2 years of established credit required. Applicant encouraged to build credit through a secured card before reapplying."),
    ],
    "home": [
        ("dti_high",      "Declined: Front-end DTI {fe_dti}% and back-end DTI {dti}% both exceed conforming loan limits (28%/43%). Monthly housing payment alone at ${housing:,} exceeds 28% of gross monthly income of ${income:,}. Application denied per underwriting guidelines."),
        ("appraisal",     "Declined: Property appraisal returned at ${appraisal:,} — ${shortfall:,} below the contract price of ${price:,}. Seller declined to reduce price. Applicant unable to cover the appraisal gap. Loan cannot proceed at requested LTV."),
        ("credit_score",  "Declined: Credit score {cs} below 620 minimum for conventional mortgage. Chapter 7 bankruptcy discharged {months} months ago; 48-month seasoning required post-discharge. Applicant may reapply after {reapply_date}."),
        ("employment",    "Declined: Self-employment income unverifiable for required 2-year period. Only 14 months of Schedule C history provided. Frequent fluctuation in net income (${low:,}–${high:,}) does not support stable qualifying income calculation."),
        ("title_issue",   "Declined: Title search revealed outstanding mechanics lien of ${lien:,} on subject property that seller has not resolved. Additionally, boundary dispute with adjacent parcel is unresolved. Loan cannot close with title in current condition."),
        ("assets",        "Declined: Insufficient verified assets for closing. Required funds to close: ${required:,}. Verified liquid assets: ${available:,}. Shortfall of ${shortfall:,}. Gift funds provided but gift letter not compliant with FNMA requirements."),
        ("fraud_flag",    "Declined: Application flagged for further review — discrepancies found between stated income on application (${stated:,}) and income reflected on tax transcripts (${actual:,}). Application declined pending resolution; referred to compliance team."),
    ],
    "personal": [
        ("dti_high",      "Declined: Debt-to-income ratio {dti}% exceeds maximum 45% for unsecured personal loans. Current monthly obligations: ${obligations:,}. Requested new payment: ${payment:,}. Combined DTI would reach {combined_dti}%. No collateral offered to mitigate risk."),
        ("credit_score",  "Declined: Credit score {cs}. Three accounts currently in collections (${collections:,} combined balance). One charge-off within past 24 months. Pattern indicates elevated default risk. Account must be in good standing for minimum 12 months before reapplication."),
        ("purpose",       "Declined: Loan purpose (gambling debt repayment) is an ineligible use under personal lending policy section 4.2. Policy prohibits loan proceeds designated for settling gambling obligations, payday loans, or other high-risk consumer debts."),
        ("stacking",      "Declined: Application stacking detected — applicant has applied for personal loans at {other_lenders} other financial institutions within the past 30 days, with 2 approvals totaling ${other_loans:,} not yet reflected in credit report. Combined with requested amount, total unsecured exposure exceeds income-based limit."),
        ("employment",    "Declined: Applicant terminated from employment {months} months ago; current income listed as 'self-employed' with no supporting documentation. Without verifiable income, repayment capacity cannot be established. May reapply upon 6 months of verifiable employment."),
        ("thin_file",     "Declined: Insufficient credit history to assess creditworthiness for unsecured loan. No revolving credit established; only {tradelines} installment account(s) with combined history of {months} months. Secured personal loan or credit-builder product recommended instead."),
    ],
    "education": [
        ("cosigner",      "Declined: No established credit history — applicant's credit file is less than 12 months old. Co-signer required per student loan policy. Application submitted without co-signer. Applicant may reapply with a creditworthy co-signer (minimum credit score 660)."),
        ("enrollment",    "Declined: Institution not on approved Title IV eligible school list. Loan proceeds cannot be disbursed to unapproved educational institutions under federal guidelines. Applicant encouraged to confirm school eligibility and reapply for an approved program."),
        ("credit_score",  "Declined: Co-signer credit score {cs} below minimum 620 required for education loans without federal backing. Co-signer has two accounts 60+ days delinquent in past 24 months. A different co-signer or federal loan alternative is recommended."),
        ("program",       "Declined: Requested loan amount ${amount:,} exceeds cost of attendance for the stated program (${coa:,}) as certified by the institution. Loan amount capped at certified cost; applicant declined full requested amount. Partial funding of ${coa:,} available upon resubmission."),
        ("no_enrollment", "Declined: Enrollment verification could not be confirmed. School's registrar office reports applicant is not enrolled in the stated program for the upcoming term. Loan disbursement requires verified active enrollment."),
    ],
    "business": [
        ("operating_history", "Declined: Business has been operating for {months} months; minimum 24-month operating history required for term loans. Revenue trajectory is positive but unverifiable without 2-year tax history. Applicant may reapply after {reapply_date}. Microenterprise lending program suggested as alternative."),
        ("dscr",          "Declined: Debt service coverage ratio calculated at {dscr:.2f}x — below the required minimum of 1.25x. Business net income insufficient to service the proposed new debt obligation alongside existing commitments. Revenue growth needed before approval is feasible."),
        ("credit_score",  "Declined: Business owner personal credit score {cs}; two tax liens filed in past 5 years (${lien:,} combined) — must be fully satisfied before business credit can be extended. Business credit score (D&B) insufficient at {dbs} (required 50+)."),
        ("collateral",    "Declined: Insufficient collateral to secure the requested loan amount. Business assets (equipment + A/R) appraised at ${assets:,} — collateral coverage ratio 0.{coverage}x below required 1.0x. Real property offered was found to have an existing senior lien leaving no available equity."),
        ("cash_flow",     "Declined: Analysis of 12-month bank statements shows average monthly net cash flow of ${flow:,} — inadequate to support ${payment:,}/mo loan payment. Cash flow is also highly seasonal with {months}-month negative periods annually. Loan size must be reduced or seasonal line of credit explored instead."),
        ("fraud_flag",    "Declined: Tax return income (${tax:,}) inconsistent with stated revenue (${stated:,}) — unexplained {gap}% gap. Additionally, business address listed on application does not match Secretary of State registration. Application referred to fraud review team; applicant notified."),
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
