import os, random, string
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS credit_card_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, application_number TEXT UNIQUE,
            customer_id TEXT, customer_name TEXT, card_type TEXT,
            requested_limit_cents INTEGER DEFAULT 0, approved_limit_cents INTEGER DEFAULT 0,
            annual_income_cents INTEGER DEFAULT 0, employment_status TEXT,
            credit_score INTEGER DEFAULT 0, status TEXT DEFAULT 'pending',
            reviewed_by TEXT, review_notes TEXT, submitted_at TEXT,
            reviewed_at TEXT, created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

def _gen_app_num():
    ts  = datetime.now().strftime("%Y%m%d")
    rnd = ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
    return f"CC-{ts}-{rnd}"

class CreditCardAppCreate(BaseModel):
    customer_id: str; customer_name: str; card_type: str
    requested_limit_cents: int=500000; annual_income_cents: int=0
    employment_status: str="employed"; credit_score: int=700

class CreditCardAppReview(BaseModel):
    status: str; approved_limit_cents: Optional[int]=None; review_notes: Optional[str]=None

@router.get("/")
def list_applications(status: str=None, limit: int=Query(100,le=500), cu: CurrentUser=Depends(require_permission("credit_cards:read"))):
    filters,params = ["1=1"],{"lim":limit}
    if status: filters.append("status=:st"); params["st"]=status
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM credit_card_applications WHERE {' AND '.join(filters)} ORDER BY submitted_at DESC LIMIT :lim"),params).fetchall()
        total = c.execute(text(f"SELECT COUNT(*) FROM credit_card_applications WHERE {' AND '.join(filters)}"),{k:v for k,v in params.items() if k!='lim'}).fetchone()[0]
    return {"applications":[dict(r._mapping) for r in rows],"total":total}

@router.get("/stats")
def card_stats(cu: CurrentUser=Depends(require_permission("credit_cards:read"))):
    with _engine.connect() as c:
        total     = c.execute(text("SELECT COUNT(*) FROM credit_card_applications")).fetchone()[0]
        pending   = c.execute(text("SELECT COUNT(*) FROM credit_card_applications WHERE status='pending'")).fetchone()[0]
        approved  = c.execute(text("SELECT COUNT(*) FROM credit_card_applications WHERE status='approved'")).fetchone()[0]
        rejected  = c.execute(text("SELECT COUNT(*) FROM credit_card_applications WHERE status='rejected'")).fetchone()[0]
        tot_limit = c.execute(text("SELECT COALESCE(SUM(approved_limit_cents),0) FROM credit_card_applications WHERE status='approved'")).fetchone()[0]
    return {"total":total,"pending":pending,"approved":approved,"rejected":rejected,"total_approved_limit_cents":tot_limit}

@router.post("/")
def submit_application(body: CreditCardAppCreate, cu: CurrentUser=Depends(require_permission("credit_cards:write"))):
    now = datetime.now().isoformat()
    app_num = _gen_app_num()
    with _engine.connect() as c:
        c.execute(text("""INSERT INTO credit_card_applications
            (application_number,customer_id,customer_name,card_type,requested_limit_cents,annual_income_cents,
             employment_status,credit_score,status,submitted_at,created_at,updated_at)
            VALUES (:an,:cid,:cn,:ct,:rl,:ai,:es,:cs,'pending',:now,:now,:now)"""),
            {"an":app_num,"cid":body.customer_id,"cn":body.customer_name,"ct":body.card_type,
             "rl":body.requested_limit_cents,"ai":body.annual_income_cents,"es":body.employment_status,
             "cs":body.credit_score,"now":now})
        c.commit()
    return {"message":"Application submitted","application_number":app_num}

@router.patch("/{app_id}")
def review_application(app_id: int, body: CreditCardAppReview, cu: CurrentUser=Depends(require_permission("credit_cards:approve"))):
    now = datetime.now().isoformat()
    sets = ["status=:st","reviewed_by=:rb","reviewed_at=:now","updated_at=:now"]
    params = {"st":body.status,"rb":cu.username,"now":now,"id":app_id}
    if body.approved_limit_cents is not None: sets.append("approved_limit_cents=:al"); params["al"]=body.approved_limit_cents
    if body.review_notes: sets.append("review_notes=:notes"); params["notes"]=body.review_notes
    with _engine.connect() as c:
        c.execute(text(f"UPDATE credit_card_applications SET {', '.join(sets)} WHERE id=:id"),params)
        c.commit()
    return {"message":f"Application {body.status}"}

@router.get("/{app_id}")
def get_application(app_id: int, cu: CurrentUser=Depends(require_permission("credit_cards:read"))):
    with _engine.connect() as c:
        row = c.execute(text("SELECT * FROM credit_card_applications WHERE id=:id"),{"id":app_id}).fetchone()
    if not row: return {"error":"Not found"}
    return dict(row._mapping)
