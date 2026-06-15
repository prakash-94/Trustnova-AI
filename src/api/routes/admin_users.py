"""
Admin user management — list, create, update, and deactivate platform users.
Admin can grant admin role to any new or existing user.
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from src.api.auth import CurrentUser, require_permission

router = APIRouter()

VALID_ROLES = [
    "admin", "personal_banker", "branch_manager", "loan_officer",
    "underwriter", "fraud_analyst", "aml_analyst", "kyc_analyst",
    "commercial_banker", "treasury_analyst", "credit_risk_analyst",
    "operations_specialist",
]


def _engine():
    from src.models.database import engine
    return engine


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _require_admin(user: CurrentUser):
    if user.role != "admin" and "*" not in (user.permissions or []):
        raise HTTPException(status_code=403, detail="Admin only.")


class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str
    full_name: str


class UpdateUserBody(BaseModel):
    role: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    new_password: Optional[str] = None


# ── GET /admin/users ──────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    current_user: CurrentUser = Depends(require_permission("*")),
):
    _require_admin(current_user)
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                "SELECT username, full_name, role, is_active, created_at FROM users ORDER BY created_at DESC"
            )).fetchall()
        return {"users": [dict(r._mapping) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"users": [], "total": 0, "error": str(e)}


# ── POST /admin/users ─────────────────────────────────────────────────────────

@router.post("/users")
async def create_user(
    body: CreateUserBody,
    current_user: CurrentUser = Depends(require_permission("*")),
):
    _require_admin(current_user)

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role. Valid roles: {', '.join(VALID_ROLES)}",
        )
    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=422, detail="Username must be at least 3 characters.")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")

    import src.api.auth as _auth
    try:
        with _engine().connect() as conn:
            existing = conn.execute(text(
                "SELECT username FROM users WHERE username = :u"
            ), {"u": body.username.strip()}).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail=f"Username '{body.username}' already exists.")

            hashed = _auth._hash_pw(body.password)
            conn.execute(text("""
                INSERT INTO users (username, hashed_password, role, full_name, is_active, created_at)
                VALUES (:u, :h, :r, :fn, 1, :now)
            """), {
                "u":   body.username.strip(),
                "h":   hashed,
                "r":   body.role,
                "fn":  body.full_name,
                "now": _utcnow(),
            })
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Welcome notification for the new user
    from src.api.routes.notifications import push_notification, ensure_table
    ensure_table()
    push_notification(
        username=body.username.strip(),
        type="account_created",
        title="Welcome to TrustNova AI",
        body=(
            f"Your account was created by {current_user.username}. "
            f"Role: {body.role.replace('_', ' ').title()}"
        ),
    )

    return {
        "status":    "created",
        "username":  body.username.strip(),
        "role":      body.role,
        "full_name": body.full_name,
    }


# ── PATCH /admin/users/{username} ─────────────────────────────────────────────

@router.patch("/users/{username}")
async def update_user(
    username: str,
    body: UpdateUserBody,
    current_user: CurrentUser = Depends(require_permission("*")),
):
    _require_admin(current_user)
    if username == current_user.username:
        raise HTTPException(status_code=400, detail="Use your profile settings to edit your own account.")
    if body.role and body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role.")

    set_parts = []
    params: dict = {"u": username}

    if body.role:
        set_parts.append("role = :role")
        params["role"] = body.role
    if body.full_name:
        set_parts.append("full_name = :fn")
        params["fn"] = body.full_name
    if body.is_active is not None:
        set_parts.append("is_active = :active")
        params["active"] = 1 if body.is_active else 0
    if body.new_password:
        if len(body.new_password) < 6:
            raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")
        import src.api.auth as _auth
        set_parts.append("hashed_password = :hpw")
        params["hpw"] = _auth._hash_pw(body.new_password)

    if not set_parts:
        raise HTTPException(status_code=422, detail="Nothing to update.")

    try:
        with _engine().connect() as conn:
            conn.execute(text(
                f"UPDATE users SET {', '.join(set_parts)} WHERE username = :u"
            ), params)
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Notify user if role changed
    if body.role:
        from src.api.routes.notifications import push_notification, ensure_table
        ensure_table()
        push_notification(
            username=username,
            type="account_created",
            title="Your role has been updated",
            body=f"Your role is now: {body.role.replace('_', ' ').title()} — updated by {current_user.username}",
        )

    return {"status": "updated", "username": username}


# ── DELETE /admin/users/{username} (soft-delete = deactivate) ─────────────────

@router.delete("/users/{username}")
async def deactivate_user(
    username: str,
    current_user: CurrentUser = Depends(require_permission("*")),
):
    _require_admin(current_user)
    if username == current_user.username:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")
    try:
        with _engine().connect() as conn:
            conn.execute(text(
                "UPDATE users SET is_active = 0 WHERE username = :u"
            ), {"u": username})
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "deactivated", "username": username}
