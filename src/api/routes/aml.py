"""AML (Anti-Money Laundering) monitoring endpoints — real fraud_alerts + transactions."""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()

_TYPE_MAP = {
    "Cross-border transaction inconsistent with customer profile": "cross_border",
    "Unusual cash deposit pattern": "structuring",
    "Rapid fund transfers": "layering",
    "Multiple accounts receiving funds": "layering",
    "High-value transaction from new device": "account_takeover",
    "Transaction velocity anomaly": "velocity",
}

def _classify(reason: str) -> str:
    for keyword, ctype in _TYPE_MAP.items():
        if keyword.lower() in reason.lower():
            return ctype
    return "unusual_activity"

def _severity(score: float) -> str:
    if score >= 0.85: return "critical"
    if score >= 0.70: return "high"
    if score >= 0.55: return "medium"
    return "low"


def _row_to_case(row: dict, txn: dict | None) -> dict:
    score = float(row.get("risk_score") or 0)
    reason = row.get("reason") or ""
    ts = row.get("timestamp") or ""
    amt_cents = int(float(txn.get("amount") or 0) * 100) if txn else 0
    return {
        "id": row["alert_id"],
        "customer_id": row["customer_id"],
        "case_type": _classify(reason),
        "status": row.get("status") or "open",
        "severity": _severity(score),
        "risk_score": round(score, 2),
        "description": reason,
        "transaction_id": row.get("transaction_id"),
        # Match AMLCase TypeScript interface field names
        "total_amount_cents": amt_cents,
        "transaction_count": 1,
        "date_range_start": ts[:10] if ts else None,
        "date_range_end": ts[:10] if ts else None,
        "location": txn.get("location") if txn else None,
        "merchant": txn.get("merchant") if txn else None,
        "category": txn.get("category") if txn else None,
        "sar_filed": False,
        "sar_reference": None,
        "analyst_id": None,
        "created_at": ts,
    }


@router.get("/cases")
async def list_aml_cases(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    customer_id: Optional[str] = None,
    limit: int = Query(50, le=500),
    current_user: CurrentUser = Depends(require_permission("aml:read")),
):
    with engine.connect() as conn:
        filters, params = [], {}
        if status:
            filters.append("fa.status = :status")
            params["status"] = status
        if customer_id:
            filters.append("fa.customer_id = :cid")
            params["cid"] = customer_id
        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        # ── Accurate totals from the entire matching dataset (no LIMIT) ──
        total_row = conn.execute(text(f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN fa.status = 'open'     THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN fa.status = 'resolved' THEN 1 ELSE 0 END) AS resolved_count,
                SUM(CASE WHEN fa.risk_score >= 0.85  THEN 1 ELSE 0 END) AS critical_count,
                SUM(CASE WHEN fa.risk_score >= 0.70
                          AND fa.risk_score < 0.85    THEN 1 ELSE 0 END) AS high_count
            FROM fraud_alerts fa
            {where}
        """), params).fetchone()
        tot = dict(total_row._mapping) if total_row else {}

        # ── Paginated list for display ──
        rows = conn.execute(text(f"""
            SELECT fa.alert_id, fa.customer_id, fa.transaction_id,
                   fa.risk_score, fa.reason, fa.status, fa.timestamp,
                   et.amount, et.location, et.merchant, et.category
            FROM fraud_alerts fa
            LEFT JOIN enriched_transactions et ON fa.transaction_id = et.transaction_id
            {where}
            ORDER BY fa.timestamp DESC
            LIMIT :limit
        """), {**params, "limit": limit}).fetchall()

    cases = []
    for r in rows:
        d = dict(r._mapping)
        txn = {"amount": d.get("amount"), "location": d.get("location"),
               "merchant": d.get("merchant"), "category": d.get("category")}
        case = _row_to_case(d, txn)
        if severity and case["severity"] != severity:
            continue
        cases.append(case)

    # Summary counts reflect the full dataset, not just the page
    summary = {
        "total":    int(tot.get("total", 0) or 0),
        "open":     int(tot.get("open_count", 0) or 0),
        "critical": int(tot.get("critical_count", 0) or 0),
        "high":     int(tot.get("high_count", 0) or 0),
        "resolved": int(tot.get("resolved_count", 0) or 0),
        "sar_filed": 0,
    }
    return {"cases": cases, "summary": summary, "total": int(tot.get("total", 0) or 0)}


@router.get("/cases/{alert_id}")
async def get_aml_case(
    alert_id: str,
    current_user: CurrentUser = Depends(require_permission("aml:read")),
):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT fa.*, et.amount, et.location, et.merchant, et.category
            FROM fraud_alerts fa
            LEFT JOIN enriched_transactions et ON fa.transaction_id = et.transaction_id
            WHERE fa.alert_id = :aid
        """), {"aid": alert_id}).fetchone()
    if not row:
        return {"error": "Case not found"}
    d = dict(row._mapping)
    txn = {"amount": d.get("amount"), "location": d.get("location"),
           "merchant": d.get("merchant"), "category": d.get("category")}
    return _row_to_case(d, txn)


@router.get("/stats/summary")
async def get_aml_summary(
    current_user: CurrentUser = Depends(require_permission("aml:read")),
):
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts")).scalar() or 0
        open_count = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts WHERE status='open'")).scalar() or 0
        resolved = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts WHERE status='resolved'")).scalar() or 0
        fp = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts WHERE status='false_positive'")).scalar() or 0
        high_risk = conn.execute(text(
            "SELECT COUNT(*) FROM fraud_alerts WHERE risk_score >= 0.70"
        )).scalar() or 0
    return {
        "total_cases": total,
        "open": open_count,
        "resolved": resolved,
        "false_positive": fp,
        "high_risk": high_risk,
    }
