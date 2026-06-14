import os
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, title TEXT,
            message TEXT, category TEXT DEFAULT 'info', is_read INTEGER DEFAULT 0,
            link TEXT, created_at TEXT)"""))
        c.commit()
_ensure()

def push_notification(user_id: str, title: str, message: str, category: str="info", link: str=None):
    with _engine.connect() as c:
        c.execute(text("INSERT INTO notifications (user_id,title,message,category,link,created_at) VALUES (:uid,:t,:m,:cat,:link,:now)"),
                  {"uid":user_id,"t":title,"m":message,"cat":category,"link":link,"now":datetime.now().isoformat()})
        c.commit()

def push_to_all_users(title: str, message: str, category: str="info", engine=None):
    eng = engine or _engine
    with eng.connect() as c:
        users = c.execute(text("SELECT username FROM users")).fetchall() if _table_exists(c,"users") else []
        for u in users:
            c.execute(text("INSERT INTO notifications (user_id,title,message,category,created_at) VALUES (:uid,:t,:m,:cat,:now)"),
                      {"uid":u[0],"t":title,"m":message,"cat":category,"now":datetime.now().isoformat()})
        c.commit()

def push_to_admins(title: str, message: str, category: str="alert", engine=None):
    eng = engine or _engine
    with eng.connect() as c:
        admins = c.execute(text("SELECT username FROM users WHERE role IN ('admin','branch_manager')")).fetchall() if _table_exists(c,"users") else []
        for a in admins:
            c.execute(text("INSERT INTO notifications (user_id,title,message,category,created_at) VALUES (:uid,:t,:m,:cat,:now)"),
                      {"uid":a[0],"t":title,"m":message,"cat":category,"now":datetime.now().isoformat()})
        c.commit()

def _table_exists(conn,name):
    return conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),{"n":name}).fetchone() is not None

@router.get("/")
def get_notifications(unread_only: bool=False, cu: CurrentUser=Depends()):
    filters,params = ["user_id=:uid"],{"uid":cu.username}
    if unread_only: filters.append("is_read=0")
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM notifications WHERE {' AND '.join(filters)} ORDER BY created_at DESC LIMIT 50"),params).fetchall()
        count = c.execute(text("SELECT COUNT(*) FROM notifications WHERE user_id=:uid AND is_read=0"),{"uid":cu.username}).fetchone()[0]
    return {"notifications":[dict(r._mapping) for r in rows],"unread_count":count}

@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, cu: CurrentUser=Depends()):
    with _engine.connect() as c:
        c.execute(text("UPDATE notifications SET is_read=1 WHERE id=:id AND user_id=:uid"),{"id":notification_id,"uid":cu.username})
        c.commit()
    return {"message":"Marked as read"}

@router.patch("/mark-all-read")
def mark_all_read(cu: CurrentUser=Depends()):
    with _engine.connect() as c:
        c.execute(text("UPDATE notifications SET is_read=1 WHERE user_id=:uid"),{"uid":cu.username})
        c.commit()
    return {"message":"All notifications marked as read"}
