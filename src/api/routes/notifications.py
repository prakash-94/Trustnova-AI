"""
Notification system — per-user inbox for all platform events.

Types pushed by other modules:
  announcement    → admin broadcasts to all users
  access_approved → admin approved a user's access request
  access_denied   → admin denied a user's access request
  bug_report      → new bug/feedback submitted (pushed to admins)
  bug_update      → admin updated a report (pushed to submitter)
  account_created → new user account created
"""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from src.api.auth import CurrentUser, get_current_user

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
                CREATE TABLE IF NOT EXISTS notifications (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    username     TEXT NOT NULL,
                    type         TEXT NOT NULL,
                    title        TEXT NOT NULL,
                    body         TEXT DEFAULT '',
                    reference_id TEXT DEFAULT '',
                    is_read      INTEGER DEFAULT 0,
                    created_at   TEXT NOT NULL
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications (username, is_read)"
            ))
            conn.commit()
        _TABLE_CREATED = True
    except Exception as e:
        print(f"[Notifications] table init error: {e}")


# ── Internal push helpers (imported by other route modules) ───────────────────

def push_notification(username: str, type: str, title: str,
                      body: str = "", reference_id: str = "") -> None:
    """Push a single notification to one user."""
    ensure_table()
    try:
        with _engine().connect() as conn:
            conn.execute(text("""
                INSERT INTO notifications (username, type, title, body, reference_id, is_read, created_at)
                VALUES (:u, :t, :title, :body, :ref, 0, :now)
            """), {"u": username, "t": type, "title": title,
                   "body": body, "ref": reference_id, "now": _utcnow()})
            conn.commit()
    except Exception as e:
        print(f"[Notifications] push error: {e}")


def push_to_all_users(type: str, title: str,
                      body: str = "", reference_id: str = "") -> None:
    """Fan-out a notification to every active user in the system."""
    ensure_table()
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                "SELECT username FROM users WHERE is_active = 1"
            )).fetchall()
            now = _utcnow()
            for row in rows:
                conn.execute(text("""
                    INSERT INTO notifications (username, type, title, body, reference_id, is_read, created_at)
                    VALUES (:u, :t, :title, :body, :ref, 0, :now)
                """), {"u": row[0], "t": type, "title": title,
                       "body": body, "ref": reference_id, "now": now})
            conn.commit()
    except Exception as e:
        print(f"[Notifications] push_all error: {e}")


def push_to_admins(type: str, title: str,
                   body: str = "", reference_id: str = "") -> None:
    """Push a notification to every active admin."""
    ensure_table()
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                "SELECT username FROM users WHERE role = 'admin' AND is_active = 1"
            )).fetchall()
            now = _utcnow()
            for row in rows:
                conn.execute(text("""
                    INSERT INTO notifications (username, type, title, body, reference_id, is_read, created_at)
                    VALUES (:u, :t, :title, :body, :ref, 0, :now)
                """), {"u": row[0], "t": type, "title": title,
                       "body": body, "ref": reference_id, "now": now})
            conn.commit()
    except Exception as e:
        print(f"[Notifications] push_admins error: {e}")


# ── GET /notifications ─────────────────────────────────────────────────────────

@router.get("")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    try:
        where = "WHERE username = :u" + (" AND is_read = 0" if unread_only else "")
        with _engine().connect() as conn:
            rows = conn.execute(text(
                f"SELECT * FROM notifications {where} ORDER BY created_at DESC LIMIT :limit"
            ), {"u": current_user.username, "limit": limit}).fetchall()
        items = [dict(r._mapping) for r in rows]
        unread_count = sum(1 for n in items if not n["is_read"])
        return {"notifications": items, "unread_count": unread_count, "total": len(items)}
    except Exception:
        return {"notifications": [], "unread_count": 0, "total": 0}


# ── POST /notifications/mark-read ─────────────────────────────────────────────

class MarkReadBody(BaseModel):
    ids: Optional[List[int]] = None   # None = mark ALL as read


@router.post("/mark-read")
async def mark_read(
    body: MarkReadBody = MarkReadBody(),
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    try:
        with _engine().connect() as conn:
            if body.ids:
                for nid in body.ids:
                    conn.execute(text(
                        "UPDATE notifications SET is_read = 1 WHERE id = :id AND username = :u"
                    ), {"id": nid, "u": current_user.username})
            else:
                conn.execute(text(
                    "UPDATE notifications SET is_read = 1 WHERE username = :u"
                ), {"u": current_user.username})
            conn.commit()
    except Exception as e:
        pass
    return {"status": "ok"}
