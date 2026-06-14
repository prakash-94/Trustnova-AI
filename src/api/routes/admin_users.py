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
        c.execute(text("""CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, full_name TEXT,
            email TEXT, role TEXT, is_active INTEGER DEFAULT 1,
            last_login TEXT, created_by TEXT, created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

class UserCreate(BaseModel):
    username: str; full_name: str; email: str; role: str; password: str

class UserUpdate(BaseModel):
    full_name: Optional[str]=None; email: Optional[str]=None
    role: Optional[str]=None; is_active: Optional[bool]=None

@router.get("/")
def list_users(role: str=None, is_active: bool=None, limit: int=Query(100,le=500), cu: CurrentUser=Depends(require_permission("admin:read"))):
    filters,params = ["1=1"],{"lim":limit}
    if role: filters.append("role=:role"); params["role"]=role
    if is_active is not None: filters.append("is_active=:act"); params["act"]=1 if is_active else 0
    with _engine.connect() as c:
        rows = c.execute(text(f"SELECT id,username,full_name,email,role,is_active,last_login,created_at FROM users WHERE {' AND '.join(filters)} LIMIT :lim"),params).fetchall()
    return {"users":[dict(r._mapping) for r in rows],"total":len(rows)}

@router.get("/stats")
def user_stats(cu: CurrentUser=Depends(require_permission("admin:read"))):
    with _engine.connect() as c:
        total  = c.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
        active = c.execute(text("SELECT COUNT(*) FROM users WHERE is_active=1")).fetchone()[0]
        by_role= c.execute(text("SELECT role, COUNT(*) FROM users GROUP BY role")).fetchall()
    return {"total":total,"active":active,"inactive":total-active,"by_role":{r[0]:r[1] for r in by_role}}

@router.patch("/{username}/deactivate")
def deactivate_user(username: str, cu: CurrentUser=Depends(require_permission("admin:write"))):
    with _engine.connect() as c:
        c.execute(text("UPDATE users SET is_active=0, updated_at=:now WHERE username=:u"),{"now":datetime.now().isoformat(),"u":username})
        c.commit()
    return {"message":f"User {username} deactivated"}

@router.patch("/{username}/activate")
def activate_user(username: str, cu: CurrentUser=Depends(require_permission("admin:write"))):
    with _engine.connect() as c:
        c.execute(text("UPDATE users SET is_active=1, updated_at=:now WHERE username=:u"),{"now":datetime.now().isoformat(),"u":username})
        c.commit()
    return {"message":f"User {username} activated"}

@router.patch("/{username}/role")
def change_role(username: str, role: str, cu: CurrentUser=Depends(require_permission("admin:write"))):
    with _engine.connect() as c:
        c.execute(text("UPDATE users SET role=:r, updated_at=:now WHERE username=:u"),{"r":role,"now":datetime.now().isoformat(),"u":username})
        c.commit()
    return {"message":f"Role updated to {role}"}
