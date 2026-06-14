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
        c.execute(text("""CREATE TABLE IF NOT EXISTS bug_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT,
            category TEXT DEFAULT 'bug', severity TEXT DEFAULT 'low',
            steps TEXT, expected TEXT, actual TEXT, screenshot_url TEXT,
            status TEXT DEFAULT 'open', submitted_by TEXT, assigned_to TEXT,
            resolution TEXT, created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

class BugReportCreate(BaseModel):
    title: str; description: str; category: str="bug"
    severity: str="low"; steps: Optional[str]=None
    expected: Optional[str]=None; actual: Optional[str]=None

class BugReportUpdate(BaseModel):
    status: Optional[str]=None; assigned_to: Optional[str]=None; resolution: Optional[str]=None

@router.get("/")
def list_bugs(status: str=None, severity: str=None, limit: int=Query(50,le=200), cu: CurrentUser=Depends(require_permission("admin:read"))):
    filters,params = ["1=1"],{"lim":limit}
    if status:   filters.append("status=:st");   params["st"]=status
    if severity: filters.append("severity=:sv"); params["sv"]=severity
    with _engine.connect() as c:
        rows = c.execute(text(f"SELECT * FROM bug_reports WHERE {' AND '.join(filters)} ORDER BY created_at DESC LIMIT :lim"),params).fetchall()
    return {"reports":[dict(r._mapping) for r in rows],"total":len(rows)}

@router.post("/")
def submit_bug(body: BugReportCreate, cu: CurrentUser=Depends()):
    now = datetime.now().isoformat()
    with _engine.connect() as c:
        c.execute(text("INSERT INTO bug_reports (title,description,category,severity,steps,expected,actual,status,submitted_by,created_at,updated_at) VALUES (:t,:d,:cat,:sev,:st,:exp,:act,'open',:by,:now,:now)"),
                  {"t":body.title,"d":body.description,"cat":body.category,"sev":body.severity,"st":body.steps,"exp":body.expected,"act":body.actual,"by":cu.username,"now":now})
        c.commit()
    return {"message":"Bug report submitted"}

@router.patch("/{report_id}")
def update_bug(report_id: int, body: BugReportUpdate, cu: CurrentUser=Depends(require_permission("admin:write"))):
    now = datetime.now().isoformat()
    sets,params = ["updated_at=:now"],{"now":now,"id":report_id}
    if body.status:      sets.append("status=:st");      params["st"]=body.status
    if body.assigned_to: sets.append("assigned_to=:at"); params["at"]=body.assigned_to
    if body.resolution:  sets.append("resolution=:res"); params["res"]=body.resolution
    with _engine.connect() as c:
        c.execute(text(f"UPDATE bug_reports SET {', '.join(sets)} WHERE id=:id"),params)
        c.commit()
    return {"message":"Bug report updated"}
