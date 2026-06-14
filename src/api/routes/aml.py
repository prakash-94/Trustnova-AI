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
        c.execute(text("""CREATE TABLE IF NOT EXISTS aml_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, alert_type TEXT,
            risk_level TEXT DEFAULT 'medium', status TEXT DEFAULT 'open',
            description TEXT, transaction_ids TEXT, sar_filed INTEGER DEFAULT 0,
            assigned_to TEXT, resolution TEXT, created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

@router.get("/cases")
def list_cases(status: str=None, risk_level: str=None, limit: int=Query(100,le=500), cu: CurrentUser=Depends(require_permission("aml:read"))):
    filters,params = ["1=1"],{"lim":limit}
    if status:     filters.append("status=:st");       params["st"]=status
    if risk_level: filters.append("risk_level=:rl");   params["rl"]=risk_level
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM aml_cases WHERE {' AND '.join(filters)} ORDER BY created_at DESC LIMIT :lim"),params).fetchall()
        total = c.execute(text(f"SELECT COUNT(*) FROM aml_cases WHERE {' AND '.join(filters)}"),{k:v for k,v in params.items() if k!='lim'}).fetchone()[0]
    return {"cases":[dict(r._mapping) for r in rows],"total":total}

@router.get("/stats/summary")
def aml_stats(cu: CurrentUser=Depends(require_permission("aml:read"))):
    with _engine.connect() as c:
        total     = c.execute(text("SELECT COUNT(*) FROM aml_cases")).fetchone()[0]
        open_c    = c.execute(text("SELECT COUNT(*) FROM aml_cases WHERE status='open'")).fetchone()[0]
        closed    = c.execute(text("SELECT COUNT(*) FROM aml_cases WHERE status='closed'")).fetchone()[0]
        high_risk = c.execute(text("SELECT COUNT(*) FROM aml_cases WHERE risk_level='high'")).fetchone()[0]
        sar       = c.execute(text("SELECT COUNT(*) FROM aml_cases WHERE sar_filed=1")).fetchone()[0]
    return {"total":total,"open":open_c,"closed":closed,"high_risk":high_risk,"sar_filed":sar}

class CaseUpdate(BaseModel):
    status: Optional[str]=None; resolution: Optional[str]=None
    assigned_to: Optional[str]=None; sar_filed: Optional[bool]=None

@router.patch("/cases/{case_id}")
def update_case(case_id: int, body: CaseUpdate, cu: CurrentUser=Depends(require_permission("aml:write"))):
    now = datetime.now().isoformat()
    sets,params = ["updated_at=:now"],{"now":now,"id":case_id}
    if body.status is not None:     sets.append("status=:st");     params["st"]=body.status
    if body.resolution is not None: sets.append("resolution=:res");params["res"]=body.resolution
    if body.assigned_to is not None:sets.append("assigned_to=:at");params["at"]=body.assigned_to
    if body.sar_filed is not None:  sets.append("sar_filed=:sf");  params["sf"]=int(body.sar_filed)
    with _engine.connect() as c:
        c.execute(text(f"UPDATE aml_cases SET {', '.join(sets)} WHERE id=:id"),params); c.commit()
    return {"message":"Case updated"}
