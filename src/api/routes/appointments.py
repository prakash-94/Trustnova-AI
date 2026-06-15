"""
Appointments — Bank Executives schedule meetings with bank employees.

Flow:
  1. Executive creates appointment → employee notified
  2. Employee confirms / reschedules → executive notified
  3. Either party cancels → other party notified
  4. GET /appointments/employees returns all active users for the picker
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
                CREATE TABLE IF NOT EXISTS appointments (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_by        TEXT NOT NULL,
                    employee_username TEXT NOT NULL,
                    employee_name     TEXT DEFAULT '',
                    employee_role     TEXT DEFAULT '',
                    title             TEXT NOT NULL,
                    description       TEXT DEFAULT '',
                    scheduled_date    TEXT NOT NULL,
                    scheduled_time    TEXT NOT NULL,
                    duration_mins     INTEGER DEFAULT 30,
                    location_type     TEXT DEFAULT 'in_person',
                    location_detail   TEXT DEFAULT '',
                    status            TEXT DEFAULT 'pending',
                    notes             TEXT DEFAULT '',
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT DEFAULT ''
                )
            """))
            conn.commit()
        _TABLE_CREATED = True
    except Exception as e:
        print(f"[Appointments] table init error: {e}")


class AppointmentBody(BaseModel):
    employee_username: str
    title: str
    description: Optional[str] = ""
    scheduled_date: str             # YYYY-MM-DD
    scheduled_time: str             # HH:MM
    duration_mins: Optional[int] = 30
    location_type: Optional[str] = "in_person"   # in_person | video | phone
    location_detail: Optional[str] = ""


class AppointmentUpdate(BaseModel):
    status: Optional[str] = None    # confirmed | completed | cancelled | rescheduled
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    notes: Optional[str] = None
    location_detail: Optional[str] = None


# ── GET /appointments/employees ────────────────────────────────────────────────
# Available for all authenticated users so executive can pick an employee.

@router.get("/employees")
async def list_employees(
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                "SELECT username, full_name, role FROM users WHERE is_active = 1 AND username != :u ORDER BY role, full_name"
            ), {"u": current_user.username}).fetchall()
        from src.api.auth import ROLES
        return {
            "employees": [
                {
                    "username":  r[0],
                    "full_name": r[1],
                    "role":      r[2],
                    "role_label": ROLES.get(r[2], {}).get("label", r[2]),
                }
                for r in rows
            ]
        }
    except Exception as e:
        return {"employees": [], "error": str(e)}


# ── GET /appointments ──────────────────────────────────────────────────────────

@router.get("")
async def list_appointments(
    status: Optional[str] = None,
    limit: int = 100,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    where_parts = ["(created_by = :u OR employee_username = :u)"]
    params: dict = {"u": current_user.username, "limit": limit}
    if status:
        where_parts.append("status = :status")
        params["status"] = status

    where = "WHERE " + " AND ".join(where_parts)
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(
                f"SELECT * FROM appointments {where} ORDER BY scheduled_date DESC, scheduled_time DESC LIMIT :limit"
            ), params).fetchall()
        return {"appointments": [dict(r._mapping) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"appointments": [], "total": 0, "error": str(e)}


# ── POST /appointments ─────────────────────────────────────────────────────────

@router.post("")
async def create_appointment(
    body: AppointmentBody,
    current_user: CurrentUser = Depends(get_current_user),
):
    if "appointments:write" not in (current_user.permissions or []) and "*" not in (current_user.permissions or []):
        raise HTTPException(status_code=403, detail="No permission to create appointments.")

    ensure_table()

    # Fetch employee info
    employee_name = body.employee_username
    employee_role = ""
    try:
        with _engine().connect() as conn:
            emp = conn.execute(text(
                "SELECT full_name, role FROM users WHERE username = :u AND is_active = 1"
            ), {"u": body.employee_username}).fetchone()
            if emp:
                employee_name = emp[0]
                employee_role = emp[1]
    except Exception:
        pass

    if not employee_name:
        raise HTTPException(status_code=404, detail="Employee not found.")

    try:
        with _engine().connect() as conn:
            result = conn.execute(text("""
                INSERT INTO appointments
                    (created_by, employee_username, employee_name, employee_role,
                     title, description, scheduled_date, scheduled_time, duration_mins,
                     location_type, location_detail, status, created_at)
                VALUES
                    (:by, :emp_u, :emp_n, :emp_r,
                     :title, :desc, :date, :time, :dur,
                     :loc_type, :loc_detail, 'pending', :now)
            """), {
                "by":        current_user.username,
                "emp_u":     body.employee_username,
                "emp_n":     employee_name,
                "emp_r":     employee_role,
                "title":     body.title,
                "desc":      body.description or "",
                "date":      body.scheduled_date,
                "time":      body.scheduled_time,
                "dur":       body.duration_mins or 30,
                "loc_type":  body.location_type or "in_person",
                "loc_detail":body.location_detail or "",
                "now":       _utcnow(),
            })
            appt_id = result.lastrowid
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Notify the employee
    try:
        from src.api.routes.notifications import push_notification
        loc_label = {"video": "Video call", "phone": "Phone call"}.get(body.location_type or "", "In-person")
        push_notification(
            username=body.employee_username,
            type="appointment",
            title=f"📅 New Appointment: {body.title}",
            body=f"From {current_user.username} · {body.scheduled_date} at {body.scheduled_time} · {loc_label}",
            reference_id=str(appt_id),
        )
    except Exception:
        pass

    return {
        "status": "created",
        "id": appt_id,
        "message": f"Appointment scheduled with {employee_name}.",
    }


# ── PATCH /appointments/{id} ───────────────────────────────────────────────────

@router.patch("/{appt_id}")
async def update_appointment(
    appt_id: int,
    body: AppointmentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()

    # Fetch existing
    try:
        with _engine().connect() as conn:
            row = conn.execute(text(
                "SELECT created_by, employee_username, title, status FROM appointments WHERE id = :id"
            ), {"id": appt_id}).fetchone()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    creator, emp_username, appt_title, prev_status = row[0], row[1], row[2], row[3]

    # Only the creator or the assigned employee can update
    if current_user.username not in (creator, emp_username) and "*" not in (current_user.permissions or []):
        raise HTTPException(status_code=403, detail="Not your appointment.")

    valid_statuses = {"confirmed", "completed", "cancelled", "rescheduled", "pending"}
    if body.status and body.status not in valid_statuses:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    set_parts = ["updated_at = :now"]
    params: dict = {"now": _utcnow(), "id": appt_id}
    if body.status:
        set_parts.append("status = :status")
        params["status"] = body.status
    if body.scheduled_date:
        set_parts.append("scheduled_date = :date")
        params["date"] = body.scheduled_date
    if body.scheduled_time:
        set_parts.append("scheduled_time = :time")
        params["time"] = body.scheduled_time
    if body.notes is not None:
        set_parts.append("notes = :notes")
        params["notes"] = body.notes
    if body.location_detail is not None:
        set_parts.append("location_detail = :loc")
        params["loc"] = body.location_detail

    try:
        with _engine().connect() as conn:
            conn.execute(text(
                f"UPDATE appointments SET {', '.join(set_parts)} WHERE id = :id"
            ), params)
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Notify the other party
    if body.status and body.status != prev_status:
        notify_user = creator if current_user.username == emp_username else emp_username
        try:
            from src.api.routes.notifications import push_notification
            status_labels = {
                "confirmed":   "✅ Confirmed",
                "cancelled":   "❌ Cancelled",
                "rescheduled": "📅 Rescheduled",
                "completed":   "✔ Completed",
            }
            push_notification(
                username=notify_user,
                type="appointment",
                title=f"Appointment {status_labels.get(body.status, body.status)}: {appt_title}",
                body=f"Updated by {current_user.username}" + (f" · {body.notes}" if body.notes else ""),
                reference_id=str(appt_id),
            )
        except Exception:
            pass

    return {"status": "updated", "id": appt_id}


# ── DELETE /appointments/{id} ──────────────────────────────────────────────────

@router.delete("/{appt_id}")
async def cancel_appointment(
    appt_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    ensure_table()
    try:
        with _engine().connect() as conn:
            row = conn.execute(text(
                "SELECT created_by, employee_username, title FROM appointments WHERE id = :id"
            ), {"id": appt_id}).fetchone()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    creator, emp_username, title = row[0], row[1], row[2]
    if current_user.username not in (creator, emp_username) and "*" not in (current_user.permissions or []):
        raise HTTPException(status_code=403, detail="Not your appointment.")

    try:
        with _engine().connect() as conn:
            conn.execute(text(
                "UPDATE appointments SET status = 'cancelled', updated_at = :now WHERE id = :id"
            ), {"now": _utcnow(), "id": appt_id})
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    notify_user = creator if current_user.username == emp_username else emp_username
    try:
        from src.api.routes.notifications import push_notification
        push_notification(
            username=notify_user,
            type="appointment",
            title=f"❌ Appointment Cancelled: {title}",
            body=f"Cancelled by {current_user.username}",
            reference_id=str(appt_id),
        )
    except Exception:
        pass

    return {"status": "cancelled", "id": appt_id}
