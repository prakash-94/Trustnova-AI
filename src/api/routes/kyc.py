import os
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
        c.execute(text("""CREATE TABLE IF NOT EXISTS kyc_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT UNIQUE,
            document_type TEXT, document_number TEXT, status TEXT DEFAULT 'pending',
            verified_by TEXT, verification_date TEXT, expiry_date TEXT,
            notes TEXT, risk_rating TEXT DEFAULT 'low', created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

@router.get("/records")
def list_kyc(status: str=None, limit: int=Query(100,le=500), cu: CurrentUser=Depends(require_permission("kyc:read"))):
    filters,params = ["1=1"],{"lim":limit}
    if status: filters.append("status=:st"); params["st"]=status
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM kyc_records WHERE {' AND '.join(filters)} ORDER BY created_at DESC LIMIT :lim"),params).fetchall()
        total = c.execute(text(f"SELECT COUNT(*) FROM kyc_records WHERE {' AND '.join(filters)}"),{k:v for k,v in params.items() if k!='lim'}).fetchone()[0]
    return {"records":[dict(r._mapping) for r in rows],"total":total}

@router.get("/stats/summary")
def kyc_stats(cu: CurrentUser=Depends(require_permission("kyc:read"))):
    with _engine.connect() as c:
        total    = c.execute(text("SELECT COUNT(*) FROM kyc_records")).fetchone()[0]
        verified = c.execute(text("SELECT COUNT(*) FROM kyc_records WHERE status='verified'")).fetchone()[0]
        pending  = c.execute(text("SELECT COUNT(*) FROM kyc_records WHERE status='pending'")).fetchone()[0]
        rejected = c.execute(text("SELECT COUNT(*) FROM kyc_records WHERE status='rejected'")).fetchone()[0]
        expired  = c.execute(text("SELECT COUNT(*) FROM kyc_records WHERE status='expired'")).fetchone()[0]
    return {"total":total,"verified":verified,"pending":pending,"rejected":rejected,"expired":expired}

@router.get("/records/{customer_id}")
def get_kyc(customer_id: str, cu: CurrentUser=Depends(require_permission("kyc:read"))):
    with _engine.connect() as c:
        row = c.execute(text("SELECT * FROM kyc_records WHERE customer_id=:cid"),{"cid":customer_id}).fetchone()
    return dict(row._mapping) if row else {"customer_id":customer_id,"status":"not_started"}

class KycUpdate(BaseModel):
    status: Optional[str]=None; document_type: Optional[str]=None
    document_number: Optional[str]=None; notes: Optional[str]=None
    risk_rating: Optional[str]=None; expiry_date: Optional[str]=None

@router.patch("/records/{customer_id}")
def update_kyc(customer_id: str, body: KycUpdate, cu: CurrentUser=Depends(require_permission("kyc:write"))):
    now = datetime.now().isoformat()
    with _engine.connect() as c:
        existing = c.execute(text("SELECT id FROM kyc_records WHERE customer_id=:cid"),{"cid":customer_id}).fetchone()
        if not existing:
            c.execute(text("INSERT INTO kyc_records (customer_id,status,created_at,updated_at) VALUES (:cid,:st,:now,:now)"),
                      {"cid":customer_id,"st":body.status or "pending","now":now})
        sets,params = ["updated_at=:now"],{"now":now,"cid":customer_id}
        if body.status is not None:          sets.append("status=:st");         params["st"]=body.status
        if body.document_type is not None:   sets.append("document_type=:dt");  params["dt"]=body.document_type
        if body.document_number is not None: sets.append("document_number=:dn");params["dn"]=body.document_number
        if body.notes is not None:           sets.append("notes=:notes");        params["notes"]=body.notes
        if body.risk_rating is not None:     sets.append("risk_rating=:rr");     params["rr"]=body.risk_rating
        if body.expiry_date is not None:     sets.append("expiry_date=:ed");     params["ed"]=body.expiry_date
        if body.status == "verified":        sets.append("verified_by=:vb"); sets.append("verification_date=:vd"); params["vb"]=cu.username; params["vd"]=now
        c.execute(text(f"UPDATE kyc_records SET {', '.join(sets)} WHERE customer_id=:cid"),params)
        c.commit()
    return {"message":"KYC record updated"}
