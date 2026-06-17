"""
Credit Card Applications — full lifecycle management.

Roles:
  personal_banker / branch_manager → can submit applications
  branch_manager / admin           → can approve or reject
  All bank staff                   → can view applications they own or all (admin/manager)

Workflow:
  submitted → under_review → approved | rejected | withdrawn
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from src.models.database import auto_pk

from src.api.auth import CurrentUser, get_current_user, require_permission

router = APIRouter()

_TABLE_CREATED = False

REVIEW_ROLES = {"admin", "branch_manager"}
SUBMIT_ROLES = {"admin", "personal_banker", "branch_manager", "executive"}


def _engine():
    from src.models.database import engine
    return engine


def _customer_pk():
    from src.models.database import customer_pk
    return customer_pk()


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _app_number() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid   = str(uuid.uuid4())[:6].upper()
    return f"CC-{stamp}-{uid}"


def ensure_table():
    global _TABLE_CREATED
    if _TABLE_CREATED:
        return
    try:
        with _engine().connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS credit_card_applications (
                    id                      {auto_pk},
                    application_number      TEXT NOT NULL UNIQUE,
                    customer_id             TEXT NOT NULL,
                    customer_name           TEXT DEFAULT '',
                    banker_username         TEXT NOT NULL,
                    banker_name             TEXT DEFAULT '',

                    -- Card preferences
                    card_type               TEXT NOT NULL,
                    requested_limit_cents   INTEGER NOT NULL,

                    -- Applicant financial profile
                    annual_income_cents     INTEGER NOT NULL,
                    employment_status       TEXT NOT NULL,
                    employer_name           TEXT DEFAULT '',
                    monthly_expenses_cents  INTEGER DEFAULT 0,
                    existing_debt_cents     INTEGER DEFAULT 0,
                    residential_status      TEXT DEFAULT 'rent',

                    -- Contact / address
                    address                 TEXT DEFAULT '',
                    phone                   TEXT DEFAULT '',

                    -- Purpose & notes
                    purpose                 TEXT DEFAULT '',
                    banker_notes            TEXT DEFAULT '',

                    -- Review
                    status                  TEXT NOT NULL DEFAULT 'submitted',
                    approved_limit_cents    INTEGER,
                    rejection_reason        TEXT DEFAULT '',
                    reviewed_by             TEXT DEFAULT '',
                    reviewed_at             TEXT DEFAULT '',
                    review_notes            TEXT DEFAULT '',

                    created_at              TEXT NOT NULL,
                    updated_at              TEXT DEFAULT ''
                )
            """))
            conn.commit()
        _TABLE_CREATED = True
    except Exception as e:
        print(f"[CreditCards] table init error: {e}")


def _is_reviewer(user: CurrentUser) -> bool:
    return user.role in REVIEW_ROLES or "*" in (user.permissions or [])


def _can_submit(user: CurrentUser) -> bool:
    return user.role in SUBMIT_ROLES or "*" in (user.permissions or [])


class CreditCardApplicationBody(BaseModel):
    customer_id:            str
    customer_name:          Optional[str] = ""

    # Card
    card_type:              str           # platinum | gold | classic | business | student | rewards
    requested_limit_cents:  int           # e.g. 500000 = $5,000

    # Financial profile
    annual_income_cents:    int
    employment_status:      str           # employed | self_employed | student | retired | unemployed
    employer_name:          Optional[str] = ""
    monthly_expenses_cents: Optional[int] = 0
    existing_debt_cents:    Optional[int] = 0
    residential_status:     Optional[str] = "rent"   # own | rent | with_family | other

    # Contact
    address:                Optional[str] = ""
    phone:                  Optional[str] = ""

    # Notes
    purpose:                Optional[str] = ""
    banker_notes:           Optional[str] = ""


class CreditCardReviewBody(BaseModel):
    status:                 str           # under_review | approved | rejected | withdrawn
    approved_limit_cents:   Optional[int] = None
    rejection_reason:       Optional[str] = ""
    review_notes:           Optional[str] = ""


VALID_CARD_TYPES = {"platinum", "gold", "classic", "business", "student", "rewards"}
VALID_STATUSES   = {"submitted", "under_review", "approved", "rejected", "withdrawn"}


# ── GET /credit-cards/applications ────────────────────────────────────────────

@router.get("/applications")
async def list_applications(
    status:   Optional[str] = None,
    card_type: Optional[str] = None,
    customer_id: Optional[str] = None,
    limit:    int = 100,
    offset:   int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    where_parts = []
    params: dict = {"limit": limit, "offset": offset}

    # Non-reviewer can only see their own submissions
    if not _is_reviewer(current_user):
        where_parts.append("banker_username = :banker")
        params["banker"] = current_user.username

    if status:
        where_parts.append("status = :status")
        params["status"] = status
    if card_type:
        where_parts.append("card_type = :card_type")
        params["card_type"] = card_type
    if customer_id:
        where_parts.append("customer_id = :cid")
        params["cid"] = customer_id

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                f"SELECT * FROM credit_card_applications {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ), params).fetchall()
            # Count
            count_row = conn.execute(text(
                f"SELECT COUNT(*) FROM credit_card_applications {where}"
            ), {k: v for k, v in params.items() if k not in ("limit", "offset")}).fetchone()
        total = count_row[0] if count_row else 0
        return {"applications": [dict(r._mapping) for r in rows], "total": total}
    except Exception as e:
        return {"applications": [], "total": 0, "error": str(e)}


# ── GET /credit-cards/applications/{id} ───────────────────────────────────────

@router.get("/applications/{app_id}")
async def get_application(
    app_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    try:
        with _engine().connect() as conn:
            row = conn.execute(text(
                "SELECT * FROM credit_card_applications WHERE id = :id"
            ), {"id": app_id}).fetchone()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=404, detail="Application not found.")

    data = dict(row._mapping)
    if not _is_reviewer(current_user) and data["banker_username"] != current_user.username:
        raise HTTPException(status_code=403, detail="Access denied.")

    return data


# ── POST /credit-cards/applications ───────────────────────────────────────────

@router.post("/applications")
async def create_application(
    body: CreditCardApplicationBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    if not _can_submit(current_user):
        raise HTTPException(status_code=403, detail="Only bankers and managers can submit credit card applications.")

    if body.card_type not in VALID_CARD_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid card type. Must be one of: {', '.join(VALID_CARD_TYPES)}")
    if body.requested_limit_cents < 10000:    # minimum $100
        raise HTTPException(status_code=422, detail="Requested limit must be at least $100.")
    if body.annual_income_cents < 0:
        raise HTTPException(status_code=422, detail="Annual income cannot be negative.")

    ensure_table()

    # Fetch customer name if not provided
    customer_name = body.customer_name or ""
    if not customer_name and body.customer_id:
        try:
            with _engine().connect() as conn:
                cust = conn.execute(text(
                    f"SELECT first_name, last_name FROM customers WHERE {_customer_pk()} = :id"
                ), {"id": body.customer_id}).fetchone()
                if cust:
                    customer_name = f"{cust[0]} {cust[1]}"
        except Exception:
            pass

    # Fetch banker name
    banker_name = current_user.username
    try:
        with _engine().connect() as conn:
            brow = conn.execute(text(
                "SELECT full_name FROM users WHERE username = :u"
            ), {"u": current_user.username}).fetchone()
            if brow:
                banker_name = brow[0]
    except Exception:
        pass

    app_number = _app_number()
    now = _utcnow()

    try:
        with _engine().connect() as conn:
            result = conn.execute(text("""
                INSERT INTO credit_card_applications (
                    application_number, customer_id, customer_name,
                    banker_username, banker_name,
                    card_type, requested_limit_cents,
                    annual_income_cents, employment_status, employer_name,
                    monthly_expenses_cents, existing_debt_cents, residential_status,
                    address, phone, purpose, banker_notes,
                    status, created_at
                ) VALUES (
                    :app_no, :cid, :cname,
                    :banker, :bname,
                    :card_type, :req_limit,
                    :income, :emp_status, :employer,
                    :expenses, :debt, :res_status,
                    :address, :phone, :purpose, :notes,
                    'submitted', :now
                )
            """), {
                "app_no":    app_number,
                "cid":       body.customer_id,
                "cname":     customer_name,
                "banker":    current_user.username,
                "bname":     banker_name,
                "card_type": body.card_type,
                "req_limit": body.requested_limit_cents,
                "income":    body.annual_income_cents,
                "emp_status":body.employment_status,
                "employer":  body.employer_name or "",
                "expenses":  body.monthly_expenses_cents or 0,
                "debt":      body.existing_debt_cents or 0,
                "res_status":body.residential_status or "rent",
                "address":   body.address or "",
                "phone":     body.phone or "",
                "purpose":   body.purpose or "",
                "notes":     body.banker_notes or "",
                "now":       now,
            })
            app_id = result.lastrowid
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Notify branch managers and admins
    try:
        from src.api.routes.notifications import push_to_admins
        push_to_admins(
            type="credit_card",
            title=f"💳 New CC Application: {app_number}",
            body=f"{customer_name or body.customer_id} · {body.card_type.title()} · ${body.requested_limit_cents // 100:,} limit · Submitted by {current_user.username}",
            reference_id=str(app_id),
        )
    except Exception:
        pass

    return {
        "status":             "submitted",
        "id":                 app_id,
        "application_number": app_number,
        "message":            f"Credit card application {app_number} submitted for review.",
    }


# ── PATCH /credit-cards/applications/{id} ─────────────────────────────────────

@router.patch("/applications/{app_id}")
async def review_application(
    app_id: int,
    body: CreditCardReviewBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status.")

    # Approval / rejection requires reviewer role
    if body.status in ("approved", "rejected") and not _is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Only branch managers and admins can approve or reject applications.")

    ensure_table()

    try:
        with _engine().connect() as conn:
            row = conn.execute(text(
                "SELECT banker_username, customer_id, customer_name, application_number, status, card_type FROM credit_card_applications WHERE id = :id"
            ), {"id": app_id}).fetchone()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=404, detail="Application not found.")

    banker, customer_id, customer_name, app_number, prev_status, card_type = (
        row[0], row[1], row[2], row[3], row[4], row[5]
    )

    # Banker can only change own submission to withdrawn or push to under_review
    if not _is_reviewer(current_user):
        if current_user.username != banker:
            raise HTTPException(status_code=403, detail="Not your application.")
        if body.status not in ("withdrawn", "under_review"):
            raise HTTPException(status_code=403, detail="Bankers can only withdraw or send for review.")

    set_parts = ["status = :status", "updated_at = :now"]
    params: dict = {"status": body.status, "now": _utcnow(), "id": app_id}

    if body.status in ("approved", "rejected"):
        set_parts += ["reviewed_by = :reviewer", "reviewed_at = :rat"]
        params["reviewer"] = current_user.username
        params["rat"] = _utcnow()

    if body.approved_limit_cents is not None:
        set_parts.append("approved_limit_cents = :approved_limit")
        params["approved_limit"] = body.approved_limit_cents
    if body.rejection_reason is not None:
        set_parts.append("rejection_reason = :rej_reason")
        params["rej_reason"] = body.rejection_reason
    if body.review_notes is not None:
        set_parts.append("review_notes = :rev_notes")
        params["rev_notes"] = body.review_notes

    try:
        with _engine().connect() as conn:
            conn.execute(text(
                f"UPDATE credit_card_applications SET {', '.join(set_parts)} WHERE id = :id"
            ), params)
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Notify the submitting banker when status changes
    if body.status != prev_status and banker != current_user.username:
        try:
            from src.api.routes.notifications import push_notification
            icons = {"approved": "✅", "rejected": "❌", "under_review": "🔍", "withdrawn": "↩"}
            push_notification(
                username=banker,
                type="credit_card",
                title=f"{icons.get(body.status, '💳')} CC Application {body.status.replace('_', ' ').title()}: {app_number}",
                body=(
                    f"Customer: {customer_name or customer_id} · {card_type.title()} · "
                    + (f"Approved limit: ${(body.approved_limit_cents or 0) // 100:,}" if body.status == "approved"
                       else body.rejection_reason or body.review_notes or "")
                ),
                reference_id=str(app_id),
            )
        except Exception:
            pass

    return {"status": body.status, "id": app_id, "application_number": app_number}


# ── GET /credit-cards/stats ────────────────────────────────────────────────────

@router.get("/stats")
async def application_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    try:
        with _engine().connect() as conn:
            banker_filter = "" if _is_reviewer(current_user) else "WHERE banker_username = :u"
            params = {} if _is_reviewer(current_user) else {"u": current_user.username}
            rows = conn.execute(text(
                f"SELECT status, COUNT(*) as cnt FROM credit_card_applications {banker_filter} GROUP BY status"
            ), params).fetchall()
        stats = {r[0]: r[1] for r in rows}
        total = sum(stats.values())
        return {
            "total":        total,
            "submitted":    stats.get("submitted", 0),
            "under_review": stats.get("under_review", 0),
            "approved":     stats.get("approved", 0),
            "rejected":     stats.get("rejected", 0),
            "withdrawn":    stats.get("withdrawn", 0),
        }
    except Exception:
        return {"total": 0, "submitted": 0, "under_review": 0, "approved": 0, "rejected": 0, "withdrawn": 0}
