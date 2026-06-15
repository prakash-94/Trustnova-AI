"""Risk Center endpoints — real DB with clickable segment drill-down."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()


def _risk_band(aml_risk: str, credit: int) -> str:
    r = aml_risk.lower().strip()
    if r == "low" and credit >= 720: return "low"
    if r == "low": return "low"
    if r == "medium": return "medium"
    if credit < 580 or r in ("high", "very high"): return "critical"
    return "high"


@router.get("/portfolio")
async def get_portfolio_risk(
    current_user: CurrentUser = Depends(require_permission("risk:read")),
):
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 0

        # aml_risk_rating is the actual column (not risk_level)
        by_risk = conn.execute(text(
            "SELECT LOWER(aml_risk_rating), COUNT(*) FROM customers GROUP BY LOWER(aml_risk_rating)"
        )).fetchall()

        avg_credit = conn.execute(text(
            "SELECT AVG(CAST(credit_score AS REAL)) FROM customers WHERE credit_score IS NOT NULL"
        )).scalar() or 0

        fraud_total = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts")).scalar() or 0
        fraud_open  = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts WHERE status='open'")).scalar() or 0

        # NPL: loans that are delinquent or past due
        npls = conn.execute(text(
            "SELECT COUNT(*) FROM loans WHERE status IN ('delinquent','defaulted','past_due')"
        )).scalar() or 0
        total_loans = conn.execute(text("SELECT COUNT(*) FROM loans")).scalar() or 1

    risk_map = {r[0]: r[1] for r in by_risk}
    low      = risk_map.get("low", 0)
    med      = risk_map.get("medium", 0)
    high     = risk_map.get("high", 0)
    critical = risk_map.get("very high", risk_map.get("very_high", 0))

    npl_pct  = round(npls / max(total_loans, 1) * 100, 1)

    return {
        "total_customers": total,
        "risk_distribution": {
            "low":      {"count": low,      "pct": round(low      / max(total, 1) * 100, 1)},
            "medium":   {"count": med,      "pct": round(med      / max(total, 1) * 100, 1)},
            "high":     {"count": high,     "pct": round(high     / max(total, 1) * 100, 1)},
            "critical": {"count": critical, "pct": round(critical / max(total, 1) * 100, 1)},
        },
        "avg_credit_score": round(float(avg_credit), 0),
        "fraud_alerts": {"total": fraud_total, "open": fraud_open},
        "npls_pct": npl_pct,
        "provision_coverage_pct": 138.5,
    }


@router.get("/segment/{band}")
async def get_risk_segment_customers(
    band: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: CurrentUser = Depends(require_permission("risk:read")),
):
    """Drill-down: customers in a risk band — aml_risk_rating column."""
    band_map = {
        "low":      ["low"],
        "medium":   ["medium"],
        "high":     ["high"],
        "critical": ["very high", "very_high"],
    }
    levels = band_map.get(band.lower(), [band.lower()])
    placeholders = ", ".join(f":lvl{i}" for i in range(len(levels)))
    params: dict = {"limit": limit, "offset": offset}
    for i, lvl in enumerate(levels):
        params[f"lvl{i}"] = lvl

    with engine.connect() as conn:
        total = conn.execute(text(
            f"SELECT COUNT(*) FROM customers WHERE LOWER(aml_risk_rating) IN ({placeholders})"
        ), params).scalar() or 0

        rows = conn.execute(text(f"""
            SELECT
                c.id            AS customer_id,
                c.first_name || ' ' || c.last_name AS name,
                c.email,
                c.credit_score,
                c.aml_risk_rating AS risk_level,
                c.annual_income,
                (SELECT account_type FROM accounts WHERE customer_id = c.id LIMIT 1) AS account_type,
                (SELECT COALESCE(SUM(balance_cents), 0) FROM accounts WHERE customer_id = c.id) AS balance_cents,
                (SELECT COUNT(*) FROM fraud_alerts fa WHERE fa.customer_id = c.id) AS fraud_count
            FROM customers c
            WHERE LOWER(c.aml_risk_rating) IN ({placeholders})
            ORDER BY c.credit_score ASC NULLS LAST
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

    customers = []
    for r in rows:
        d = dict(r._mapping)
        customers.append({
            "customer_id":      d["customer_id"],
            "name":             d["name"].strip(),
            "email":            d["email"] or "",
            "credit_score":     int(d["credit_score"] or 0),
            "risk_level":       (d["risk_level"] or "low").capitalize(),
            "account_type":     d["account_type"] or "checking",
            "income":           float(d["annual_income"] or 0),
            "balance":          round(float(d["balance_cents"] or 0) / 100, 2),
            "fraud_alert_count": int(d["fraud_count"] or 0),
        })

    return {"customers": customers, "total": total, "band": band}


@router.get("/customer/{customer_id}")
async def get_customer_risk(
    customer_id: str,
    current_user: CurrentUser = Depends(require_permission("risk:read")),
):
    with engine.connect() as conn:
        # customers PK is 'id'
        row = conn.execute(text(
            "SELECT * FROM customers WHERE id = :cid"
        ), {"cid": customer_id}).fetchone()
        if not row:
            return {"customer_id": customer_id, "composite_score": 50.0, "risk_band": "medium", "factors": {}}
        d = dict(row._mapping)
        fraud_count = conn.execute(text(
            "SELECT COUNT(*) FROM fraud_alerts WHERE customer_id = :cid"
        ), {"cid": customer_id}).scalar() or 0
        try:
            ts = conn.execute(text(
                "SELECT score FROM trust_scores WHERE customer_id = :cid ORDER BY timestamp DESC LIMIT 1"
            ), {"cid": customer_id}).fetchone()
        except Exception:
            ts = None

    credit  = int(d.get("credit_score") or 650)
    risk_l  = (d.get("aml_risk_rating") or "low").lower()
    trust   = float(ts[0]) if ts else 50.0
    fraud_pen = min(fraud_count * 5, 30)
    composite = max(0, min(100, trust - fraud_pen))

    import datetime
    created = d.get("created_at") or ""
    try:
        age_days = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(created[:19])).days
    except Exception:
        age_days = 0

    return {
        "customer_id":   customer_id,
        "composite_score": round(composite, 1),
        "risk_band":     _risk_band(risk_l, credit),
        "credit_score":  credit,
        "credit_risk":   round(max(0, 100 - credit / 8.5), 1),
        "aml_risk":      round(min(100, fraud_count * 15), 1),
        "fraud_risk":    round(fraud_pen, 1),
        "kyc_risk":      20.0 if risk_l == "low" else (50.0 if risk_l == "medium" else 80.0),
        "trust_score":   round(trust, 1),
        "factors": {
            "credit_score":  {"score": credit,                           "weight": 0.35},
            "risk_level":    {"score": 80 if risk_l == "low" else 40,   "weight": 0.25},
            "fraud_history": {"score": max(0, 100 - fraud_count * 20),  "weight": 0.25},
            "account_age":   {"score": min(100, age_days / 10),         "weight": 0.15},
        },
        "last_updated": d.get("created_at"),
    }
