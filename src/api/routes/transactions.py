"""
Bank-wide Transactions endpoint.

Use-case: Provides aggregate transaction analytics for the entire bank,
grouped by time period (daily / weekly / monthly / quarterly / half-yearly
/ annual).  This is the Operations-level view — completely separate from
/customers/{id}/transactions which only shows one customer's history.

Data source: enriched_transactions table — 15,000 real transactions.
Fields: transaction_id, customer_id, amount, merchant, category,
        location, timestamp, is_fraud, merchant_risk, device_change.

Endpoints:
    GET /transactions/stats   → KPI metrics + trend array for a period
    GET /transactions         → Paginated list with period/category/fraud filters
"""

import datetime
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()


# ── Period configuration ───────────────────────────────────────────────────────
# Maps frontend tab label → how many days back to look.

PERIOD_DAYS: dict[str, int] = {
    "daily":       1,
    "weekly":      7,
    "monthly":     30,
    "quarterly":   90,
    "half_yearly": 180,
    "annual":      365,
}

# Trend chart granularity per period (how many bars to show, and at what time unit)
PERIOD_TREND: dict[str, dict] = {
    "daily":       {"bars": 24,  "unit": "hour",  "fmt": "%Y-%m-%d %H"},
    "weekly":      {"bars": 7,   "unit": "day",   "fmt": "%Y-%m-%d"},
    "monthly":     {"bars": 30,  "unit": "day",   "fmt": "%Y-%m-%d"},
    "quarterly":   {"bars": 13,  "unit": "week",  "fmt": "%Y-%W"},
    "half_yearly": {"bars": 26,  "unit": "week",  "fmt": "%Y-%W"},
    "annual":      {"bars": 12,  "unit": "month", "fmt": "%Y-%m"},
}

# Cache the DB's max timestamp so we compute cutoffs relative to REAL data,
# not wall-clock time.  This prevents the "30-day window lands past all data" problem
# when running against a dataset seeded in the past.
_DB_MAX_TS_CACHE: str | None = None


def _get_db_max_ts(conn) -> datetime.datetime:
    """
    Return the latest timestamp in enriched_transactions.
    Falls back to utcnow() if table is empty.
    Cached after first call so we don't hit the DB on every request.
    """
    global _DB_MAX_TS_CACHE
    if _DB_MAX_TS_CACHE is None:
        row = conn.execute(text(
            "SELECT MAX(timestamp) FROM enriched_transactions"
        )).fetchone()
        raw = row[0] if row and row[0] else None
        if raw:
            _DB_MAX_TS_CACHE = raw
        else:
            _DB_MAX_TS_CACHE = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        return datetime.datetime.fromisoformat(_DB_MAX_TS_CACHE)
    except Exception:
        return datetime.datetime.utcnow()


def _cutoff_date(period: str, ref: datetime.datetime | None = None) -> str:
    """
    Return ISO date string for the start of the requested period,
    anchored to `ref` (defaults to current UTC time).

    By passing the DB's max timestamp as `ref` we ensure the period window
    always contains real data regardless of when the dataset was seeded.
    """
    days = PERIOD_DAYS.get(period, 30)
    base = ref or datetime.datetime.utcnow()
    return (base - datetime.timedelta(days=days)).strftime("%Y-%m-%d")


def _row_to_txn(row: dict) -> dict:
    """
    Transform an enriched_transactions row into the frontend Transaction shape.

    Target output:
    {
        "id": "TXN-abc123",
        "customer_id": "cust-xyz",
        "transaction_type": "debit",    # credit | debit (sign of amount)
        "amount_cents": 15000,
        "description": "Starbucks",     # merchant field
        "merchant_name": "Starbucks",
        "merchant_category": "food",    # category field
        "location": "Dallas, TX",
        "channel": "pos",
        "status": "completed",
        "is_flagged": false,            # is_fraud = 1
        "merchant_risk": "low",
        "created_at": "2024-04-01T13:22:00"
    }
    """
    amt = float(row.get("amount") or 0)
    return {
        "id": row.get("transaction_id", ""),
        "customer_id": row.get("customer_id", ""),
        "transaction_type": "credit" if amt >= 0 else "debit",
        "amount_cents": int(abs(amt) * 100),
        "description": row.get("merchant") or "Unknown",
        "merchant_name": row.get("merchant") or "",
        "merchant_category": row.get("category") or "other",
        "location": row.get("location") or "",
        "channel": "pos",
        "status": "completed",
        "is_flagged": bool(row.get("is_fraud")),
        "is_fraud": bool(row.get("is_fraud")),
        "merchant_risk": row.get("merchant_risk") or "low",
        "created_at": str(row.get("timestamp") or ""),
    }


# ── GET /transactions/stats ────────────────────────────────────────────────────

@router.get("/stats")
async def get_transaction_stats(
    period: str = Query(
        "monthly",
        description="daily | weekly | monthly | quarterly | half_yearly | annual",
    ),
    current_user: CurrentUser = Depends(require_permission("transactions:read")),
):
    """
    Bank-wide transaction KPIs for the selected time period.

    Use-case: When a Risk Analyst selects the "Monthly" tab in the
    Transactions Operations page, the frontend calls this endpoint to
    populate the 6 KPI cards and the trend bar chart.

    Calculation logic:
    - total_transactions   = COUNT(*) in the period window
    - total_volume_cents   = SUM(ABS(amount)) * 100
    - avg_amount_cents     = AVG(ABS(amount)) * 100
    - fraud_count          = COUNT WHERE is_fraud = 1
    - failed_count         = 0 (all our data is 'completed'; hook up later)
    - by_category          = GROUP BY category → top 8
    - trend                = daily GROUP BY (up to 30 points)

    Target output:
    {
        "period": "monthly",
        "total_transactions": 1450,
        "total_volume_cents": 18500000,
        "avg_amount_cents": 12758,
        "fraud_count": 45,
        "failed_count": 0,
        "all_time_total": 15000,
        "by_category": {
            "food": { "count": 312, "volume_cents": 4620000 },
            "retail": { "count": 289, ... },
            ...
        },
        "trend": [
            { "day": "2024-04-01", "count": 48, "volume_cents": 610000 },
            { "day": "2024-04-02", "count": 51, ... },
            ...
        ]
    }
    """
    with engine.connect() as conn:
        # Anchor the period to the DB's own max timestamp.
        # This means "monthly" = last 30 days of whatever data exists,
        # not last 30 days from wall-clock now (which would miss older seeded data).
        ref_dt = _get_db_max_ts(conn)
        cutoff = _cutoff_date(period, ref_dt)

        # ── Period KPIs ──────────────────────────────────────────────────────
        stats_row = conn.execute(text("""
            SELECT
                COUNT(*)                                                       AS total,
                COALESCE(SUM(ABS(amount)), 0)                                  AS total_volume,
                COALESCE(AVG(ABS(amount)), 0)                                  AS avg_amount,
                COALESCE(SUM(CASE WHEN is_fraud = 1 THEN 1 ELSE 0 END), 0)    AS fraud_count
            FROM enriched_transactions
            WHERE timestamp >= :cutoff
        """), {"cutoff": cutoff}).fetchone()

        # ── All-time total ────────────────────────────────────────────────────
        all_time = conn.execute(text(
            "SELECT COUNT(*) FROM enriched_transactions"
        )).scalar() or 0

        # ── Category breakdown ────────────────────────────────────────────────
        cat_rows = conn.execute(text("""
            SELECT category,
                   COUNT(*)           AS cnt,
                   SUM(ABS(amount))   AS vol
            FROM   enriched_transactions
            WHERE  timestamp >= :cutoff
            GROUP  BY category
            ORDER  BY cnt DESC
            LIMIT  8
        """), {"cutoff": cutoff}).fetchall()

        # ── Trend bars — period-appropriate granularity ───────────────────────
        # Different periods use different time units for the chart bars:
        #   daily → hourly bars   (24 bars)
        #   weekly/monthly → daily bars
        #   quarterly/half-yearly → weekly bars
        #   annual → monthly bars
        trend_cfg = PERIOD_TREND.get(period, PERIOD_TREND["monthly"])

        if trend_cfg["unit"] == "hour":
            group_expr = "strftime('%Y-%m-%d %H', timestamp)"
            label_expr = "strftime('%Y-%m-%d %H', timestamp)"
        elif trend_cfg["unit"] == "week":
            group_expr = "strftime('%Y-%W', timestamp)"
            label_expr = "strftime('%Y-%W', timestamp)"
        elif trend_cfg["unit"] == "month":
            group_expr = "strftime('%Y-%m', timestamp)"
            label_expr = "strftime('%Y-%m', timestamp)"
        else:  # day
            group_expr = "DATE(timestamp)"
            label_expr = "DATE(timestamp)"

        trend_rows = conn.execute(text(f"""
            SELECT {label_expr}         AS day,
                   COUNT(*)             AS cnt,
                   SUM(ABS(amount))     AS vol
            FROM   enriched_transactions
            WHERE  timestamp >= :cutoff
            GROUP  BY {group_expr}
            ORDER  BY day ASC
            LIMIT  :bars
        """), {"cutoff": cutoff, "bars": trend_cfg["bars"]}).fetchall()

    s = dict(stats_row._mapping) if stats_row else {}

    return {
        "period": period,
        "total_transactions": int(s.get("total") or 0),
        "total_volume_cents": int(float(s.get("total_volume") or 0) * 100),
        "avg_amount_cents":   int(float(s.get("avg_amount")    or 0) * 100),
        "fraud_count":        int(s.get("fraud_count") or 0),
        "failed_count":       0,
        "all_time_total":     int(all_time),
        "by_category": {
            r[0]: {
                "count":        r[1],
                "volume_cents": int(float(r[2] or 0) * 100),
            }
            for r in cat_rows
        },
        "trend": [
            {
                "day":          str(r[0]),
                "count":        r[1],
                "volume_cents": int(float(r[2] or 0) * 100),
            }
            for r in trend_rows
        ],
    }


# ── GET /transactions ──────────────────────────────────────────────────────────

@router.get("")
async def list_transactions(
    period: Optional[str] = Query(None, description="daily|weekly|monthly|quarterly|half_yearly|annual"),
    category: Optional[str] = Query(None, description="Filter by merchant category"),
    is_fraud: Optional[bool] = Query(None, description="Filter flagged transactions"),
    search: Optional[str] = Query(None, description="Search merchant or location"),
    limit: int = Query(50, le=1000),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("transactions:read")),
):
    """
    Bank-wide paginated transaction list with optional filters.

    Use-case: The "Monthly" tab in Transactions Operations shows the table
    of all transactions in the last 30 days.  The analyst searches for
    "Starbucks" to see coffee-shop spending across the entire bank.

    Examples:
        GET /transactions?period=weekly&limit=50
        GET /transactions?period=monthly&is_fraud=true&limit=100
        GET /transactions?search=walmart&period=quarterly

    Target output:
    {
        "transactions": [
            { "id": "TXN-001", "customer_id": "cust-abc",
              "merchant_name": "Starbucks", "amount_cents": 650,
              "is_flagged": false, "created_at": "2024-04-15T09:30:00" },
            ...
        ],
        "total": 1450
    }
    """
    filters: list[str] = []
    params: dict = {"limit": limit, "offset": offset}

    if period and period in PERIOD_DAYS:
        with engine.connect() as _c:
            ref_dt = _get_db_max_ts(_c)
        filters.append("timestamp >= :cutoff")
        params["cutoff"] = _cutoff_date(period, ref_dt)

    if category:
        filters.append("LOWER(category) = :category")
        params["category"] = category.lower()

    if is_fraud is not None:
        filters.append("is_fraud = :is_fraud")
        params["is_fraud"] = 1 if is_fraud else 0

    if search:
        filters.append(
            "(LOWER(merchant) LIKE :search OR LOWER(location) LIKE :search)"
        )
        params["search"] = f"%{search.lower()}%"

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        total_count = conn.execute(
            text(f"SELECT COUNT(*) FROM enriched_transactions {where}"), params
        ).scalar() or 0

        rows = conn.execute(text(
            f"""
            SELECT *
            FROM   enriched_transactions
            {where}
            ORDER  BY timestamp DESC
            LIMIT  :limit
            OFFSET :offset
            """
        ), params).fetchall()

    txns = [_row_to_txn(dict(r._mapping)) for r in rows]
    return {"transactions": txns, "total": total_count}
