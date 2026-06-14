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
        c.execute(text("""CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, body TEXT,
            category TEXT DEFAULT 'general', priority TEXT DEFAULT 'normal',
            target_roles TEXT DEFAULT 'all', is_active INTEGER DEFAULT 1,
            created_by TEXT, created_at TEXT, expires_at TEXT)"""))
        c.commit()
_ensure()

class AnnouncementCreate(BaseModel):
    title: str; body: str; category: str="general"
    priority: str="normal"; target_roles: str="all"; expires_at: Optional[str]=None

@router.get("/")
def list_announcements(active_only: bool=True, cu: CurrentUser=Depends()):
    filters,params = ["1=1"],{}
    if active_only: filters.append("is_active=1")
    with _engine.connect() as c:
        rows = c.execute(text(f"SELECT * FROM announcements WHERE {' AND '.join(filters)} ORDER BY created_at DESC LIMIT 50"),params).fetchall()
    return {"announcements":[dict(r._mapping) for r in rows],"total":len(rows)}

@router.post("/")
def create_announcement(body: AnnouncementCreate, cu: CurrentUser=Depends(require_permission("admin:write"))):
    now = datetime.now().isoformat()
    with _engine.connect() as c:
        c.execute(text("INSERT INTO announcements (title,body,category,priority,target_roles,is_active,created_by,created_at,expires_at) VALUES (:t,:b,:cat,:pri,:tr,1,:cb,:now,:exp)"),
                  {"t":body.title,"b":body.body,"cat":body.category,"pri":body.priority,"tr":body.target_roles,"cb":cu.username,"now":now,"exp":body.expires_at})
        c.commit()
    return {"message":"Announcement created"}

@router.patch("/{ann_id}/deactivate")
def deactivate(ann_id: int, cu: CurrentUser=Depends(require_permission("admin:write"))):
    with _engine.connect() as c:
        c.execute(text("UPDATE announcements SET is_active=0 WHERE id=:id"),{"id":ann_id})
        c.commit()
    return {"message":"Announcement deactivated"}
