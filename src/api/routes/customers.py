import os, uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, get_current_user, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
            email TEXT, phone TEXT, date_of_birth TEXT, address_street TEXT,
            address_city TEXT, address_state TEXT, address_zip TEXT,
            segment TEXT DEFAULT 'retail', customer_type TEXT DEFAULT 'individual',
            kyc_status TEXT DEFAULT 'pending', aml_risk_rating TEXT DEFAULT 'low',
            credit_score INTEGER, annual_income REAL, employment_status TEXT,
            is_pep INTEGER DEFAULT 0, is_sanctioned INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1, notes TEXT, created_at TEXT, updated_at TEXT)"""))
        c.execute(text("""CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY, customer_id TEXT, account_type TEXT,
            account_number TEXT, balance_cents INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'active', interest_rate REAL, opened_date TEXT,
            last_transaction_date TEXT, created_at TEXT)"""))
        c.execute(text("""CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY, account_id TEXT, customer_id TEXT, transaction_type TEXT,
            amount_cents INTEGER, currency TEXT DEFAULT 'USD', description TEXT,
            merchant TEXT, category TEXT, status TEXT DEFAULT 'completed',
            is_flagged INTEGER DEFAULT 0, flag_reason TEXT, location TEXT, created_at TEXT)"""))
        c.commit()
_ensure()

@router.get("/search")
def search_customers(q: str="", limit: int=Query(20,le=100), cu: CurrentUser=Depends(require_permission("customers:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("""SELECT id,first_name,last_name,email,phone,segment,kyc_status,
            aml_risk_rating,credit_score,is_active FROM customers
            WHERE (first_name LIKE :q OR last_name LIKE :q OR email LIKE :q OR id LIKE :q) LIMIT :lim"""),
            {"q":f"%{q}%","lim":limit}).fetchall()
    return {"results":[dict(r._mapping) for r in rows],"total":len(rows)}

@router.get("/list")
def list_customers(limit: int=Query(100,le=500), offset: int=0, cu: CurrentUser=Depends(require_permission("customers:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("SELECT * FROM customers WHERE is_active=1 ORDER BY created_at DESC LIMIT :lim OFFSET :off"),{"lim":limit,"off":offset}).fetchall()
        total = c.execute(text("SELECT COUNT(*) FROM customers WHERE is_active=1")).fetchone()[0]
    return {"customers":[dict(r._mapping) for r in rows],"total":total}

@router.get("/stats/overview")
def customer_stats(cu: CurrentUser=Depends(require_permission("customers:read"))):
    with _engine.connect() as c:
        total    = c.execute(text("SELECT COUNT(*) FROM customers")).fetchone()[0]
        active   = c.execute(text("SELECT COUNT(*) FROM customers WHERE is_active=1")).fetchone()[0]
        high_risk= c.execute(text("SELECT COUNT(*) FROM customers WHERE aml_risk_rating='high'")).fetchone()[0]
        kyc_pend = c.execute(text("SELECT COUNT(*) FROM customers WHERE kyc_status='pending'")).fetchone()[0]
    return {"total":total,"active":active,"high_risk":high_risk,"kyc_pending":kyc_pend}

@router.get("/{customer_id}/accounts")
def customer_accounts(customer_id: str, cu: CurrentUser=Depends(require_permission("customers:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("SELECT * FROM accounts WHERE customer_id=:cid"),{"cid":customer_id}).fetchall()
    return {"accounts":[dict(r._mapping) for r in rows]}

@router.get("/{customer_id}/transactions")
def customer_transactions(customer_id: str, limit: int=Query(50,le=200), cu: CurrentUser=Depends(require_permission("customers:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("SELECT * FROM transactions WHERE customer_id=:cid ORDER BY created_at DESC LIMIT :lim"),{"cid":customer_id,"lim":limit}).fetchall()
    return {"transactions":[dict(r._mapping) for r in rows]}

@router.get("/{customer_id}/summary")
def customer_summary(customer_id: str, cu: CurrentUser=Depends(require_permission("customers:read"))):
    with _engine.connect() as c:
        cust = c.execute(text("SELECT * FROM customers WHERE id=:id"),{"id":customer_id}).fetchone()
        accts= c.execute(text("SELECT * FROM accounts WHERE customer_id=:cid"),{"cid":customer_id}).fetchall()
        txns = c.execute(text("SELECT * FROM transactions WHERE customer_id=:cid ORDER BY created_at DESC LIMIT 10"),{"cid":customer_id}).fetchall()
    if not cust: raise HTTPException(404,"Customer not found")
    cd = dict(cust._mapping); al = [dict(r._mapping) for r in accts]
    return {"customer":cd,"accounts":al,"recent_transactions":[dict(r._mapping) for r in txns],
            "summary":{"total_balance_cents":sum(a.get("balance_cents",0) for a in al),"account_count":len(al),
                       "kyc_status":cd.get("kyc_status"),"aml_risk":cd.get("aml_risk_rating"),"credit_score":cd.get("credit_score")}}

@router.get("/{customer_id}")
def get_customer(customer_id: str, cu: CurrentUser=Depends(require_permission("customers:read"))):
    with _engine.connect() as c:
        row = c.execute(text("SELECT * FROM customers WHERE id=:id"),{"id":customer_id}).fetchone()
    if not row: raise HTTPException(404,"Customer not found")
    return dict(row._mapping)

class CustomerCreate(BaseModel):
    first_name: str; last_name: str; email: str
    phone: Optional[str]=None; segment: str="retail"; customer_type: str="individual"
    credit_score: Optional[int]=None; annual_income: Optional[float]=None
    employment_status: Optional[str]=None; address_street: Optional[str]=None
    address_city: Optional[str]=None; address_state: Optional[str]=None; notes: Optional[str]=None

@router.post("")
def create_customer(body: CustomerCreate, cu: CurrentUser=Depends(require_permission("customers:write"))):
    cid = f"CUST-{uuid.uuid4().hex[:8].upper()}"; now = datetime.now().isoformat()
    with _engine.connect() as c:
        c.execute(text("""INSERT INTO customers (id,first_name,last_name,email,phone,segment,customer_type,
            credit_score,annual_income,employment_status,address_street,address_city,address_state,
            kyc_status,aml_risk_rating,is_active,notes,created_at,updated_at)
            VALUES (:id,:fn,:ln,:em,:ph,:seg,:ct,:cs,:ai,:es,:as_,:ac,:ast,'pending','low',1,:notes,:now,:now)"""),
            {"id":cid,"fn":body.first_name,"ln":body.last_name,"em":body.email,"ph":body.phone,
             "seg":body.segment,"ct":body.customer_type,"cs":body.credit_score,"ai":body.annual_income,
             "es":body.employment_status,"as_":body.address_street,"ac":body.address_city,
             "ast":body.address_state,"notes":body.notes,"now":now})
        c.commit()
    return {"id":cid,"message":f"Customer {body.first_name} {body.last_name} created"}
