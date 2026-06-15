"""
Announcements — admin publishes news/updates to all users.
On creation, a notification is fanned out to every active user.
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from src.api.auth import CurrentUser, get_current_user, require_permission

router = APIRouter()

_TABLE_CREATED = False


def _engine():
    from src.models.database import engine
    return engine


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def ensure_table():
    global _TABLE_CREATED
    if _TABLE_CREATED:
        return
    try:
        with _engine().connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    body        TEXT NOT NULL,
                    priority    TEXT NOT NULL DEFAULT 'normal',
                    created_by  TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    is_active   INTEGER NOT NULL DEFAULT 1
                )
            """))
            conn.commit()
        _TABLE_CREATED = True
    except Exception as e:
        print(f"[Announcements] table init error: {e}")


class AnnouncementBody(BaseModel):
    title: str
    body: str
    priority: Optional[str] = "normal"    # normal | important | urgent


def _is_admin(user: CurrentUser) -> bool:
    return user.role == "admin" or "*" in (user.permissions or [])


# ── GET /announcements ─────────────────────────────────────────────────────────

@router.get("")
async def list_announcements(
    limit: int = 50,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text("""
                SELECT * FROM announcements
                WHERE is_active = 1
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"limit": limit}).fetchall()
        return {"announcements": [dict(r._mapping) for r in rows], "total": len(rows)}
    except Exception:
        return {"announcements": [], "total": 0}


# ── POST /announcements ────────────────────────────────────────────────────────

@router.post("")
async def create_announcement(
    body: AnnouncementBody,
    current_user: CurrentUser = Depends(require_permission("*")),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin only.")

    priority = body.priority or "normal"
    if priority not in ("normal", "important", "urgent"):
        priority = "normal"

    ensure_table()
    try:
        with _engine().connect() as conn:
            result = conn.execute(text("""
                INSERT INTO announcements (title, body, priority, created_by, created_at, is_active)
                VALUES (:title, :body, :priority, :by, :now, 1)
            """), {
                "title":    body.title,
                "body":     body.body,
                "priority": priority,
                "by":       current_user.username,
                "now":      _utcnow(),
            })
            ann_id = result.lastrowid
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Fan-out to all users
    from src.api.routes.notifications import push_to_all_users
    icon = {"important": "⚠", "urgent": "🚨"}.get(priority, "📢")
    push_to_all_users(
        type="announcement",
        title=f"{icon} {body.title}",
        body=body.body[:200],
        reference_id=str(ann_id),
    )

    return {
        "status":  "created",
        "id":      ann_id,
        "message": "Announcement published — all users notified.",
    }


# ── DELETE /announcements/{id} ─────────────────────────────────────────────────

@router.delete("/{ann_id}")
async def delete_announcement(
    ann_id: int,
    current_user: CurrentUser = Depends(require_permission("*")),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin only.")
    ensure_table()
    try:
        with _engine().connect() as conn:
            conn.execute(text(
                "UPDATE announcements SET is_active = 0 WHERE id = :id"
            ), {"id": ann_id})
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "deleted"}
