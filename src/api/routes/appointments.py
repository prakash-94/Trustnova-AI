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
        c.execute(text("""CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, customer_name TEXT,
            assigned_to TEXT, appointment_type TEXT, title TEXT,
            scheduled_at TEXT, duration_minutes INTEGER DEFAULT 30,
            location TEXT DEFAULT 'branch', status TEXT DEFAULT 'scheduled',
            notes TEXT, created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

class AppointmentCreate(BaseModel):
    customer_id: str; customer_name: str; appointment_type: str; title: str
    scheduled_at: str; duration_minutes: int=30; location: str="branch"; notes: Optional[str]=None

class AppointmentUpdate(BaseModel):
    status: Optional[str]=None; scheduled_at: Optional[str]=None
    notes: Optional[str]=None; assigned_to: Optional[str]=None

@router.get("/")
def list_appointments(status: str=None, date: str=None, limit: int=Query(100,le=500), cu: CurrentUser=Depends()):
    filters,params = ["1=1"],{"lim":limit}
    if cu.role not in ("admin","branch_manager"): filters.append("assigned_to=:me"); params["me"]=cu.username
    if status: filters.append("status=:st"); params["st"]=status
    if date:   filters.append("date(scheduled_at)=:d"); params["d"]=date
    with _engine.connect() as c:
        rows = c.execute(text(f"SELECT * FROM appointments WHERE {' AND '.join(filters)} ORDER BY scheduled_at ASC LIMIT :lim"),params).fetchall()
    return {"appointments":[dict(r._mapping) for r in rows],"total":len(rows)}

@router.post("/")
def create_appointment(body: AppointmentCreate, cu: CurrentUser=Depends(require_permission("appointments:write"))):
    now = datetime.now().isoformat()
    with _engine.connect() as c:
        c.execute(text("INSERT INTO appointments (customer_id,customer_name,assigned_to,appointment_type,title,scheduled_at,duration_minutes,location,status,notes,created_at,updated_at) VALUES (:cid,:cn,:at,:atype,:title,:sched,:dur,:loc,'scheduled',:notes,:now,:now)"),
                  {"cid":body.customer_id,"cn":body.customer_name,"at":cu.username,"atype":body.appointment_type,"title":body.title,"sched":body.scheduled_at,"dur":body.duration_minutes,"loc":body.location,"notes":body.notes,"now":now})
        c.commit()
    return {"message":"Appointment created"}

@router.patch("/{apt_id}")
def update_appointment(apt_id: int, body: AppointmentUpdate, cu: CurrentUser=Depends()):
    now = datetime.now().isoformat()
    sets,params = ["updated_at=:now"],{"now":now,"id":apt_id}
    if body.status:       sets.append("status=:st");       params["st"]=body.status
    if body.scheduled_at: sets.append("scheduled_at=:sa"); params["sa"]=body.scheduled_at
    if body.notes:        sets.append("notes=:notes");      params["notes"]=body.notes
    if body.assigned_to:  sets.append("assigned_to=:asgn");params["asgn"]=body.assigned_to
    with _engine.connect() as c:
        c.execute(text(f"UPDATE appointments SET {', '.join(sets)} WHERE id=:id"),params)
        c.commit()
    return {"message":"Appointment updated"}

@router.delete("/{apt_id}")
def cancel_appointment(apt_id: int, cu: CurrentUser=Depends()):
    with _engine.connect() as c:
        c.execute(text("UPDATE appointments SET status='cancelled', updated_at=:now WHERE id=:id"),{"now":datetime.now().isoformat(),"id":apt_id})
        c.commit()
    return {"message":"Appointment cancelled"}
