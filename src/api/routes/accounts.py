"""
Bank-wide Accounts endpoint — queries the `accounts` table (not customers).
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine
from datetime import date as _date, timedelta

router = APIRouter()

CANONICAL_TYPES = {
    "personal":    ["personal", "retail", "personal_checking", "premium", "joint", "retirement"],
    "student":     ["student", "education"],
    "business":    ["business", "commercial"],
    "savings":     ["savings", "high_yield_savings"],
    "checking":    ["checking", "basic_checking"],
    "credit_card": ["credit_card", "credit", "revolving"],
}


def _compute_age_days(opened_date) -> int | None:
    if not opened_date:
        return None
    try:
        d = _date.fromisoformat(str(opened_date)[:10])
        return (_date.today() - d).days
    except Exception:
        return None


def _bucket_type(raw: str) -> str:
    raw = (raw or "").lower()
    for bucket, aliases in CANONICAL_TYPES.items():
        if raw in aliases or raw == bucket:
            return bucket
    return "personal"


def _row_to_account(row: dict) -> dict:
    raw_type = row.get("account_type", "")
    status_raw = row.get("status", "active")
    status = "dormant" if status_raw == "inactive" else status_raw
    return {
        "id": row.get("id", ""),
        "customer_id": row.get("customer_id", ""),
        "customer_name": row.get("customer_name", ""),
        "account_number": row.get("account_number", ""),
        "account_type": _bucket_type(raw_type),
        "account_type_raw": raw_type,
        "status": status,
        "balance_cents": int(row.get("balance_cents") or 0),
        "currency": row.get("currency", "USD"),
        "opened_date": row.get("opened_date"),
        "account_age_days": _compute_age_days(row.get("opened_date")),
        "credit_score": row.get("credit_score"),
        "income_cents": None,
        "risk_level": row.get("aml_risk_rating", "low"),
    }


@router.get("/stats")
async def get_accounts_stats(
    current_user: CurrentUser = Depends(require_permission("accounts:read")),
):
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM accounts")).scalar() or 0

        dormant_count = conn.execute(text(
            "SELECT COUNT(*) FROM accounts WHERE status = 'inactive'"
        )).scalar() or 0

        cutoff = (_date.today() - timedelta(days=31)).isoformat()
        new_this_month = conn.execute(text(
            "SELECT COUNT(*) FROM accounts WHERE opened_date >= :cutoff"
        ), {"cutoff": cutoff}).scalar() or 0

        total_balance = conn.execute(text(
            "SELECT COALESCE(SUM(balance_cents), 0) FROM accounts"
        )).scalar() or 0

        type_rows = conn.execute(text("""
            SELECT account_type, COUNT(*) AS cnt,
                   AVG(balance_cents) AS avg_bal,
                   SUM(balance_cents) AS total_bal
            FROM accounts
            GROUP BY account_type
        """)).fetchall()

    by_type: dict = {}
    for r in type_rows:
        bucket = _bucket_type(r[0])
        entry = by_type.setdefault(bucket, {"count": 0, "avg_balance_cents": 0, "total_balance_cents": 0})
        entry["count"] += r[1]
        entry["total_balance_cents"] += int(r[3] or 0)

    for bucket in by_type:
        cnt = by_type[bucket]["count"]
        total_b = by_type[bucket]["total_balance_cents"]
        by_type[bucket]["avg_balance_cents"] = (total_b // cnt) if cnt else 0

    return {
        "total_accounts": total,
        "active_accounts": total - dormant_count,
        "dormant_accounts": dormant_count,
        "new_this_month": new_this_month,
        "total_balance_cents": int(total_balance),
        "avg_balance_cents": int(total_balance / total) if total else 0,
        "by_type": by_type,
    }


@router.get("")
async def list_accounts(
    account_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("accounts:read")),
):
    filters: list[str] = []
    params: dict = {"limit": limit, "offset": offset}

    if account_type and account_type not in ("all", "dormant"):
        aliases = CANONICAL_TYPES.get(account_type, [account_type])
        if aliases:
            placeholders = ", ".join([f":t{i}" for i in range(len(aliases))])
            filters.append(f"LOWER(a.account_type) IN ({placeholders})")
            for i, alias in enumerate(aliases):
                params[f"t{i}"] = alias

    if account_type == "dormant" or status == "dormant":
        filters.append("a.status = 'inactive'")
    elif status and status != "all":
        filters.append("a.status = :status")
        params["status"] = status

    if search:
        filters.append(
            "(LOWER(c.first_name || ' ' || c.last_name) LIKE :search "
            "OR LOWER(c.email) LIKE :search "
            "OR LOWER(a.account_number) LIKE :search)"
        )
        params["search"] = f"%{search.lower()}%"

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        total_count = conn.execute(
            text(f"""
                SELECT COUNT(*)
                FROM accounts a
                LEFT JOIN customers c ON a.customer_id = c.id
                {where}
            """), params
        ).scalar() or 0

        rows = conn.execute(text(f"""
            SELECT a.*,
                   (c.first_name || ' ' || c.last_name) AS customer_name,
                   c.email, c.credit_score, c.aml_risk_rating
            FROM accounts a
            LEFT JOIN customers c ON a.customer_id = c.id
            {where}
            ORDER BY a.balance_cents DESC
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

    accounts = [_row_to_account(dict(r._mapping)) for r in rows]
    return {"accounts": accounts, "total": total_count}
