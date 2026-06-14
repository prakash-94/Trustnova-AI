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
        c.execute(text("""CREATE TABLE IF NOT EXISTS access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, requested_by TEXT, role TEXT,
            resource TEXT, reason TEXT, status TEXT DEFAULT 'pending',
            reviewed_by TEXT, review_notes TEXT, created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

class AccessRequestCreate(BaseModel):
    role: str; resource: str; reason: str

class AccessRequestReview(BaseModel):
    status: str; review_notes: Optional[str]=None

@router.get("/")
def list_requests(status: str=None, cu: CurrentUser=Depends(require_permission("admin:read"))):
    filters,params = ["1=1"],{}
    if status: filters.append("status=:st"); params["st"]=status
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM access_requests WHERE {' AND '.join(filters)} ORDER BY created_at DESC"),params).fetchall()
        total = c.execute(text(f"SELECT COUNT(*) FROM access_requests WHERE {' AND '.join(filters)}"),params).fetchone()[0]
    return {"requests":[dict(r._mapping) for r in rows],"total":total}

@router.post("/")
def create_request(body: AccessRequestCreate, cu: CurrentUser=Depends()):
    now = datetime.now().isoformat()
    with _engine.connect() as c:
        c.execute(text("INSERT INTO access_requests (requested_by,role,resource,reason,status,created_at,updated_at) VALUES (:by,:role,:res,:reason,'pending',:now,:now)"),
                  {"by":cu.username,"role":body.role,"res":body.resource,"reason":body.reason,"now":now})
        c.commit()
    return {"message":"Access request submitted"}

@router.patch("/{request_id}")
def review_request(request_id: int, body: AccessRequestReview, cu: CurrentUser=Depends(require_permission("admin:write"))):
    now = datetime.now().isoformat()
    with _engine.connect() as c:
        c.execute(text("UPDATE access_requests SET status=:st, reviewed_by=:rb, review_notes=:notes, updated_at=:now WHERE id=:id"),
                  {"st":body.status,"rb":cu.username,"notes":body.review_notes,"now":now,"id":request_id})
        c.commit()
    return {"message":"Request reviewed"}
