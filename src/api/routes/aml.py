"""AML (anti-money-laundering) cases: the ML model's alerts.

The `ml_score` Databricks job writes alerts (the riskiest accounts per simulation per day, with reason codes and a
predicted laundering pattern). `python -m src.data.sync_ml_alerts` copies them into the app database's
`ml_alerts` table, which these endpoints read. Until the first sync, the endpoints return an empty list with
`source_ready: false`.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, text

from src.api.aml_reasons import explain
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()

SIMULATIONS = {
    "HIS": "HI-Small", "HIM": "HI-Medium", "HIL": "HI-Large",
    "LIS": "LI-Small", "LIM": "LI-Medium", "LIL": "LI-Large",
}
# The score is a calibrated probability that the account's riskiest payment that day is laundering.
SEVERITY_SQL = {
    "critical": "score >= 0.9",
    "high": "score >= 0.7 AND score < 0.9",
    "medium": "score >= 0.4 AND score < 0.7",
    "low": "score < 0.4",
}
STATUSES = ("open", "reviewing", "escalated", "resolved")


def severity(score: float) -> str:
    if score >= 0.9:
        return "critical"
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _ready() -> bool:
    return inspect(engine).has_table("ml_alerts")


def _reasons(raw: str | None) -> list[dict]:
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return []
    return [{"text": explain(r), "feature": r.get("feature"), "value": r.get("value"),
             "contribution": r.get("contribution")} for r in items]


def to_case(d: dict) -> dict:
    score = float(d["score"])
    pattern = (d.get("predicted_pattern") or "").lower() or None
    amount = d.get("top_amount_usd")
    fmt = d.get("top_payment_format")
    counterparty = d["top_to_account"] if d.get("top_from_account") == d["account_id"] else d.get("top_from_account")
    direction = "to" if d.get("top_from_account") == d["account_id"] else "from"
    description = (f"Riskiest payment: {f'${amount:,.0f}' if amount is not None else 'amount unknown'}"
                   f"{f' by {fmt}' if fmt else ''} {direction} {counterparty or 'an unknown account'}")
    return {
        "id": d["alert_id"],
        "customer_id": d["account_id"],
        "account_id": d["account_id"],
        "simulation": d["variant"],
        "simulation_name": SIMULATIONS.get(d["variant"], d["variant"]),
        "owner_name": d.get("owner_name"),
        "bank_name": d.get("bank_name"),
        "case_type": pattern or "unclassified",
        "predicted_pattern": pattern,
        "pattern_probability": d.get("pattern_probability"),
        "status": d.get("status") or "open",
        "severity": severity(score),
        "risk_score": round(score, 4),
        "rank_in_day": d.get("rank_in_day"),
        "description": description,
        "reasons": _reasons(d.get("reasons")),
        "transaction_id": d.get("top_txn_id"),
        "top_transaction": {
            "txn_id": d.get("top_txn_id"), "timestamp": d.get("top_txn_ts"),
            "from_account": d.get("top_from_account"), "to_account": d.get("top_to_account"),
            "amount_usd": amount, "payment_format": fmt, "currency": d.get("top_currency"),
        },
        "total_amount_cents": round(amount * 100) if amount is not None else 0,
        "transaction_count": d.get("n_txn") or 1,
        "date_range_start": d["alert_date"],
        "date_range_end": d["alert_date"],
        "model_version": f"M1 v{d.get('m1_version')}" + (f" · M3 v{d['m3_version']}" if d.get("m3_version") else ""),
        "sar_filed": False,
        "sar_reference": None,
        "analyst_id": d.get("analyst_id"),
        "created_at": d["alert_date"],
        "synced_at": d.get("synced_at"),
    }


def _filters(status, severity_, customer_id, simulation) -> tuple[str, dict]:
    where, params = [], {}
    if status:
        if status not in STATUSES:
            raise HTTPException(400, f"status must be one of {', '.join(STATUSES)}")
        where.append("status = :status")
        params["status"] = status
    if severity_:
        if severity_ not in SEVERITY_SQL:
            raise HTTPException(400, f"severity must be one of {', '.join(SEVERITY_SQL)}")
        where.append(SEVERITY_SQL[severity_])
    if customer_id:
        where.append("account_id = :account_id")
        params["account_id"] = customer_id
    if simulation:
        if simulation not in SIMULATIONS:
            raise HTTPException(400, f"simulation must be one of {', '.join(SIMULATIONS)}")
        where.append("variant = :variant")
        params["variant"] = simulation
    return ("WHERE " + " AND ".join(where)) if where else "", params


def _summary(conn, where: str, params: dict) -> dict:
    row = conn.execute(text(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open,
               SUM(CASE WHEN status = 'reviewing' THEN 1 ELSE 0 END) AS reviewing,
               SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved,
               SUM(CASE WHEN {SEVERITY_SQL['critical']} THEN 1 ELSE 0 END) AS critical,
               SUM(CASE WHEN {SEVERITY_SQL['high']} THEN 1 ELSE 0 END) AS high,
               SUM(CASE WHEN {SEVERITY_SQL['medium']} THEN 1 ELSE 0 END) AS medium,
               MIN(alert_date) AS first_date, MAX(alert_date) AS last_date, MAX(synced_at) AS synced_at
        FROM ml_alerts {where}
    """), params).fetchone()
    d = dict(row._mapping)
    out = {k: int(d[k] or 0) for k in ("total", "open", "reviewing", "resolved", "critical", "high", "medium")}
    out["sar_filed"] = 0
    return {**out, "first_date": d["first_date"], "last_date": d["last_date"], "synced_at": d["synced_at"]}


@router.get("/cases")
async def list_aml_cases(
    status: str | None = None,
    severity: str | None = None,
    customer_id: str | None = None,
    simulation: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("aml:read")),
):
    """Newest alerts first, then by rank within the day. Filters apply before the limit."""
    if not _ready():
        return {"cases": [], "summary": {}, "total": 0, "source": "ml_alerts", "source_ready": False}
    where, params = _filters(status, severity, customer_id, simulation)
    with engine.connect() as conn:
        summary = _summary(conn, where, params)
        rows = conn.execute(text(f"""
            SELECT * FROM ml_alerts {where}
            ORDER BY alert_date DESC, rank_in_day ASC, variant ASC
            LIMIT :limit OFFSET :offset
        """), {**params, "limit": limit, "offset": offset}).fetchall()
    return {"cases": [to_case(dict(r._mapping)) for r in rows], "summary": summary,
            "total": summary["total"], "source": "ml_alerts", "source_ready": True}


@router.get("/cases/{alert_id}")
async def get_aml_case(
    alert_id: str,
    current_user: CurrentUser = Depends(require_permission("aml:read")),
):
    if not _ready():
        raise HTTPException(404, "Case not found")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM ml_alerts WHERE alert_id = :aid"), {"aid": alert_id}).fetchone()
    if not row:
        raise HTTPException(404, "Case not found")
    return to_case(dict(row._mapping))


@router.get("/stats/summary")
async def get_aml_summary(
    current_user: CurrentUser = Depends(require_permission("aml:read")),
):
    if not _ready():
        return {"total_cases": 0, "open": 0, "resolved": 0, "high_risk": 0, "source_ready": False}
    with engine.connect() as conn:
        s = _summary(conn, "", {})
        by_sim = conn.execute(text("SELECT variant, COUNT(*) FROM ml_alerts GROUP BY variant")).fetchall()
    return {"total_cases": s["total"], "open": s["open"], "reviewing": s["reviewing"], "resolved": s["resolved"],
            "high_risk": s["critical"] + s["high"], "by_simulation": {v: n for v, n in by_sim},
            "first_date": s["first_date"], "last_date": s["last_date"], "synced_at": s["synced_at"],
            "source_ready": True}
