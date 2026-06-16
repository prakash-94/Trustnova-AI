"""
Access Request system — users request elevated permissions; admin approves or denies.

Temporary Access Flow:
  1. Non-admin user clicks "Request Access" on a locked sidebar section
  2. POST /access-requests  → creates a pending record
  3. Admin sees it in the queue; clicks Approve
  4. PATCH /access-requests/{id}  → sets status=approved, expires_at=utcnow+N min
  5. User's frontend polls GET /access-requests/my-grants every 30s
  6. When a grant is found, the sidebar section unlocks with a live countdown
  7. Backend require_permission() also checks active grants so API calls succeed
  8. At expires_at the section relocks automatically on both frontend and backend
"""
from datetime import datetime, timedelta, timezone

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _utcnow_str() -> str:
    return _utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import text

from src.api.auth import CurrentUser, require_permission, get_current_user, log_audit

router = APIRouter()

# Minutes a temporary access grant stays active after approval
TEMP_ACCESS_MINUTES = 10

_TABLE_CREATED = False


def _engine():
    from src.models.database import engine
    return engine


def ensure_table():
    global _TABLE_CREATED
    if _TABLE_CREATED:
        return
    try:
        with _engine().connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS access_requests (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    section     TEXT NOT NULL,
                    reason      TEXT,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    expires_at  TEXT,
                    created_at  TEXT NOT NULL
                )
            """))
            # Add expires_at column if this is an older DB without it
            try:
                conn.execute(text(
                    "ALTER TABLE access_requests ADD COLUMN expires_at TEXT"
                ))
            except Exception:
                pass  # column already exists
            conn.commit()
        _TABLE_CREATED = True
    except Exception as e:
        print(f"[AccessRequests] Could not create table: {e}")


class AccessRequestBody(BaseModel):
    section: str
    reason: Optional[str] = None


class AccessRequestReview(BaseModel):
    status: str                    # 'approved' | 'denied'
    note: Optional[str] = None
    duration_minutes: int = TEMP_ACCESS_MINUTES


# ── POST /access-requests ─────────────────────────────────────────────────────
# Any authenticated user can submit a request.

@router.post("")
async def create_request(
    body: AccessRequestBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    now = _utcnow_str()
    try:
        with _engine().connect() as conn:
            conn.execute(text("""
                INSERT INTO access_requests (username, role, section, reason, status, created_at)
                VALUES (:u, :r, :s, :reason, 'pending', :now)
            """), {
                "u": current_user.username,
                "r": current_user.role,
                "s": body.section,
                "reason": body.reason,
                "now": now,
            })
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save request: {e}")
    # Notify all admins so the bell icon lights up immediately
    try:
        from src.api.routes.notifications import push_to_admins
        role_label = current_user.role.replace("_", " ").title()
        section_label = body.section.replace("_", " ").title()
        push_to_admins(
            type="access_request",
            title=f"🔐 Access Request: {section_label}",
            body=f"{current_user.username} ({role_label}) is requesting access to '{section_label}'."
                 + (f" Reason: {body.reason}" if body.reason else ""),
            reference_id="",
        )
    except Exception:
        pass

    return {
        "status": "submitted",
        "message": f"Access request for '{body.section}' submitted for admin review.",
    }


# ── GET /access-requests/my-grants ────────────────────────────────────────────
# Returns active (approved + not yet expired) grants for the calling user.
# The frontend polls this every 30s to detect newly approved access.

@router.get("/my-grants")
async def my_grants(
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    now = _utcnow_str()
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text("""
                SELECT section, expires_at
                FROM   access_requests
                WHERE  username = :u
                  AND  status   = 'approved'
                  AND  expires_at IS NOT NULL
                  AND  expires_at > :now
                ORDER  BY expires_at DESC
            """), {"u": current_user.username, "now": now}).fetchall()
    except Exception:
        return {"grants": []}

    grants = []
    for r in rows:
        section = r[0]
        expires_at = r[1]
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            remaining = int((exp_dt - _utcnow()).total_seconds())
        except Exception:
            remaining = 0
        if remaining > 0:
            grants.append({
                "section":    section,
                "expires_at": expires_at,
                "remaining_seconds": remaining,
            })

    return {"grants": grants}


# ── GET /access-requests ──────────────────────────────────────────────────────
# Admin only: full queue view.

@router.get("")
async def list_requests(
    current_user: CurrentUser = Depends(require_permission("*")),
):
    if current_user.role != "admin" and "*" not in (current_user.permissions or []):
        raise HTTPException(status_code=403, detail="Admin only.")
    ensure_table()
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                "SELECT * FROM access_requests ORDER BY created_at DESC LIMIT 200"
            )).fetchall()
        return {"requests": [dict(r._mapping) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"requests": [], "total": 0, "error": str(e)}


# ── PATCH /access-requests/{req_id} ──────────────────────────────────────────
# Admin only: approve or deny; sets expires_at when approving.

@router.patch("/{req_id}")
async def review_request(
    req_id: int,
    body: AccessRequestReview,
    current_user: CurrentUser = Depends(require_permission("*")),
):
    if current_user.role != "admin" and "*" not in (current_user.permissions or []):
        raise HTTPException(status_code=403, detail="Admin only.")
    if body.status not in ("approved", "denied"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'denied'.")

    ensure_table()
    now = _utcnow_str()

    # Only set expires_at when approving
    expires_at: Optional[str] = None
    if body.status == "approved":
        minutes = max(1, min(body.duration_minutes, 60))  # clamp 1–60 min
        expires_at = (_utcnow() + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

    # Fetch the requesting user before updating (needed for notification)
    requesting_user: Optional[str] = None
    requesting_section: Optional[str] = None
    try:
        with _engine().connect() as conn:
            row = conn.execute(text(
                "SELECT username, section FROM access_requests WHERE id = :id"
            ), {"id": req_id}).fetchone()
            if row:
                requesting_user = row[0]
                requesting_section = row[1]
    except Exception:
        pass

    try:
        with _engine().connect() as conn:
            conn.execute(text("""
                UPDATE access_requests
                SET status      = :s,
                    reviewed_by = :by,
                    reviewed_at = :at,
                    expires_at  = :exp
                WHERE id = :id
            """), {
                "s":   body.status,
                "by":  current_user.username,
                "at":  now,
                "exp": expires_at,
                "id":  req_id,
            })
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    log_audit(current_user.username, current_user.role,
              "access_request_review", "access_requests", resource_id=str(req_id))

    # Notify the requesting user of the outcome
    if requesting_user:
        try:
            from src.api.routes.notifications import push_notification
            section_label = (requesting_section or "").replace("_", " ").title()
            if body.status == "approved":
                minutes = max(1, min(body.duration_minutes, 60))
                push_notification(
                    username=requesting_user,
                    type="access_approved",
                    title=f"✅ Access Granted: {section_label}",
                    body=f"Your request for '{section_label}' was approved for {minutes} minutes.",
                    reference_id=str(req_id),
                )
            else:
                push_notification(
                    username=requesting_user,
                    type="access_denied",
                    title=f"❌ Access Denied: {section_label}",
                    body=f"Your request for '{section_label}' was not approved.",
                    reference_id=str(req_id),
                )
        except Exception:
            pass  # never block the response for a notification failure

    return {
        "status":      body.status,
        "reviewed_by": current_user.username,
        "expires_at":  expires_at,
    }
