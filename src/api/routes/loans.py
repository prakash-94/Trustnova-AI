import os
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS loans (
            id TEXT PRIMARY KEY, customer_id TEXT, loan_type TEXT,
            amount_cents INTEGER, interest_rate REAL, term_months INTEGER,
            status TEXT DEFAULT 'pending', purpose TEXT, collateral TEXT,
            monthly_payment_cents INTEGER, outstanding_balance_cents INTEGER,
            origination_date TEXT, maturity_date TEXT, officer_username TEXT,
            notes TEXT, created_at TEXT)"""))
        c.commit()
_ensure()

@router.get("")
def list_loans(loan_type: str=None, status: str=None, limit: int=Query(100,le=500), offset: int=0, cu: CurrentUser=Depends(require_permission("loans:read"))):
    filters,params = ["1=1"],{"lim":limit,"off":offset}
    if loan_type: filters.append("loan_type=:lt");  params["lt"]=loan_type
    if status:    filters.append("status=:st"); params["st"]=status
    where = " AND ".join(filters)
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM loans WHERE {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),params).fetchall()
        total = c.execute(text(f"SELECT COUNT(*) FROM loans WHERE {where}"),{k:v for k,v in params.items() if k not in ('lim','off')}).fetchone()[0]
    return {"loans":[dict(r._mapping) for r in rows],"total":total}

@router.get("/stats/portfolio")
def loan_stats(cu: CurrentUser=Depends(require_permission("loans:read"))):
    with _engine.connect() as c:
        total    = c.execute(text("SELECT COUNT(*) FROM loans")).fetchone()[0]
        pending  = c.execute(text("SELECT COUNT(*) FROM loans WHERE status='pending'")).fetchone()[0]
        approved = c.execute(text("SELECT COUNT(*) FROM loans WHERE status='approved'")).fetchone()[0]
        active   = c.execute(text("SELECT COUNT(*) FROM loans WHERE status='active'")).fetchone()[0]
        val      = c.execute(text("SELECT COALESCE(SUM(amount_cents),0) FROM loans")).fetchone()[0]
        avg_amt  = c.execute(text("SELECT COALESCE(AVG(amount_cents),0) FROM loans")).fetchone()[0]
    return {"total":total,"pending":pending,"approved":approved,"active":active,"total_value_cents":val,"avg_amount_cents":int(avg_amt)}

@router.get("/customer/{customer_id}")
def customer_loans(customer_id: str, cu: CurrentUser=Depends(require_permission("loans:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("SELECT * FROM loans WHERE customer_id=:cid"),{"cid":customer_id}).fetchall()
    return {"loans":[dict(r._mapping) for r in rows]}

@router.get("/{loan_id}/detail")
@router.get("/{loan_id}")
def get_loan(loan_id: str, cu: CurrentUser=Depends(require_permission("loans:read"))):
    with _engine.connect() as c:
        row = c.execute(text("SELECT * FROM loans WHERE id=:id"),{"id":loan_id}).fetchone()
    if not row: raise HTTPException(404,"Loan not found")
    return dict(row._mapping)
