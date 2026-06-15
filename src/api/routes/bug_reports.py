"""
Feedback & Bug Report system.

Flow:
  1. Any user POSTs /bug-reports → all admins are notified
  2. Admin GETs /bug-reports (sees all); user GETs own reports only
  3. Admin PATCHes /bug-reports/{id} → submitter gets notified if status changed
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
                CREATE TABLE IF NOT EXISTS bug_reports (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    submitted_by TEXT NOT NULL,
                    type         TEXT NOT NULL DEFAULT 'feedback',
                    title        TEXT NOT NULL,
                    description  TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'open',
                    priority     TEXT NOT NULL DEFAULT 'medium',
                    admin_notes  TEXT DEFAULT '',
                    reviewed_by  TEXT DEFAULT '',
                    updated_at   TEXT DEFAULT '',
                    created_at   TEXT NOT NULL
                )
            """))
            conn.commit()
        _TABLE_CREATED = True
    except Exception as e:
        print(f"[BugReports] table init error: {e}")


def _is_admin(user: CurrentUser) -> bool:
    return user.role == "admin" or "*" in (user.permissions or [])


class BugReportBody(BaseModel):
    type: str = "feedback"          # feedback | bug | suggestion
    title: str
    description: str
    priority: Optional[str] = "medium"    # low | medium | high | critical


class BugReportUpdate(BaseModel):
    status: Optional[str] = None          # open | in_progress | resolved | closed
    admin_notes: Optional[str] = None
    priority: Optional[str] = None


# ── GET /bug-reports ──────────────────────────────────────────────────────────

@router.get("")
async def list_bug_reports(
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 100,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    is_admin = _is_admin(current_user)
    where_parts = []
    params: dict = {"limit": limit}

    if not is_admin:
        where_parts.append("submitted_by = :user")
        params["user"] = current_user.username
    if status:
        where_parts.append("status = :status")
        params["status"] = status
    if type:
        where_parts.append("type = :type")
        params["type"] = type

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                f"SELECT * FROM bug_reports {where} ORDER BY created_at DESC LIMIT :limit"
            ), params).fetchall()
        return {"reports": [dict(r._mapping) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"reports": [], "total": 0, "error": str(e)}


# ── POST /bug-reports ─────────────────────────────────────────────────────────

@router.post("")
async def create_bug_report(
    body: BugReportBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    try:
        with _engine().connect() as conn:
            result = conn.execute(text("""
                INSERT INTO bug_reports
                    (submitted_by, type, title, description, status, priority, created_at)
                VALUES (:by, :type, :title, :desc, 'open', :priority, :now)
            """), {
                "by":       current_user.username,
                "type":     body.type,
                "title":    body.title,
                "desc":     body.description,
                "priority": body.priority or "medium",
                "now":      _utcnow(),
            })
            report_id = result.lastrowid
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Notify all admins
    from src.api.routes.notifications import push_to_admins
    icon = {"bug": "🐛", "feedback": "💬", "suggestion": "💡"}.get(body.type, "📝")
    push_to_admins(
        type="bug_report",
        title=f"{icon} New {body.type.title()}: {body.title[:60]}",
        body=f"From {current_user.username} ({current_user.role}) · {body.description[:150]}",
        reference_id=str(report_id),
    )

    return {
        "status":  "submitted",
        "id":      report_id,
        "message": "Your report has been submitted. Admin will review shortly.",
    }


# ── PATCH /bug-reports/{id} ───────────────────────────────────────────────────

@router.patch("/{report_id}")
async def update_bug_report(
    report_id: int,
    body: BugReportUpdate,
    current_user: CurrentUser = Depends(require_permission("*")),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin only.")

    ensure_table()

    # Fetch existing record so we can notify the submitter
    try:
        with _engine().connect() as conn:
            row = conn.execute(text(
                "SELECT submitted_by, title, status FROM bug_reports WHERE id = :id"
            ), {"id": report_id}).fetchone()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=404, detail="Report not found.")

    prev_status = row[2]
    set_parts = ["reviewed_by = :by", "updated_at = :now"]
    params: dict = {"by": current_user.username, "now": _utcnow(), "id": report_id}

    if body.status:
        set_parts.append("status = :status")
        params["status"] = body.status
    if body.admin_notes is not None:
        set_parts.append("admin_notes = :notes")
        params["notes"] = body.admin_notes
    if body.priority:
        set_parts.append("priority = :priority")
        params["priority"] = body.priority

    try:
        with _engine().connect() as conn:
            conn.execute(text(
                f"UPDATE bug_reports SET {', '.join(set_parts)} WHERE id = :id"
            ), params)
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Notify submitter if status changed
    if body.status and body.status != prev_status:
        from src.api.routes.notifications import push_notification
        label = {
            "in_progress": "🔧 In Progress",
            "resolved":    "✅ Resolved",
            "closed":      "🔒 Closed",
        }.get(body.status, body.status.replace("_", " ").title())
        note_part = f" — {body.admin_notes}" if body.admin_notes else ""
        push_notification(
            username=row[0],
            type="bug_update",
            title=f"Report Updated: {row[1][:60]}",
            body=f"Status → {label}{note_part}",
            reference_id=str(report_id),
        )

    return {"status": "updated", "id": report_id}
