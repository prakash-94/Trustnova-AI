"""Loan management endpoints — real SQLite loans table."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()

FMT = {
    "home": "Home Loan",
    "auto": "Auto Loan",
    "personal": "Personal Loan",
    "education": "Education Loan",
    "business": "Business Loan",
}


def _row_to_loan(row: dict) -> dict:
    return {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "loan_type": row["loan_type"],
        "loan_label": FMT.get(row["loan_type"], row["loan_type"].title()),
        "status": row["status"],
        "purpose": row.get("purpose") or "",
        "description": row.get("notes") or "",
        "requested_amount_cents": int(row.get("amount_cents") or 0),
        "approved_amount_cents": None,
        "outstanding_balance_cents": int(row.get("outstanding_balance_cents") or 0),
        "interest_rate": row.get("interest_rate"),
        "apr": None,
        "term_months": row.get("term_months"),
        "monthly_payment_cents": int(row.get("monthly_payment_cents") or 0),
        "dti_ratio": None,
        "ltv_ratio": None,
        "credit_score_at_origination": None,
        "risk_grade": None,
        "is_delinquent": False,
        "days_past_due": 0,
        "collateral_type": row.get("collateral"),
        "origination_date": row.get("origination_date"),
        "maturity_date": row.get("maturity_date"),
        "created_at": row.get("created_at"),
    }


@router.get("")
async def list_loans(
    status: Optional[str] = None,
    loan_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: CurrentUser = Depends(require_permission("loans:read")),
):
    filters, params = [], {"limit": limit}
    if status:
        filters.append("status = :status")
        params["status"] = status
    if loan_type:
        filters.append("loan_type = :loan_type")
        params["loan_type"] = loan_type
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT * FROM loans {where} ORDER BY created_at DESC LIMIT :limit"
        ), params).fetchall()
        total = conn.execute(text(
            f"SELECT COUNT(*) FROM loans {where}"
        ), {k: v for k, v in params.items() if k != "limit"}).scalar() or 0
    loans = [_row_to_loan(dict(r._mapping)) for r in rows]
    return {"loans": loans, "total": total}


@router.get("/customer/{customer_id}")
async def get_loans_for_customer(
    customer_id: str,
    current_user: CurrentUser = Depends(require_permission("loans:read")),
):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT * FROM loans WHERE customer_id = :cid ORDER BY created_at DESC LIMIT 50"
        ), {"cid": customer_id}).fetchall()
    loans = [_row_to_loan(dict(r._mapping)) for r in rows]
    summary = {
        "total": len(loans),
        "by_type": {},
        "by_status": {},
        "total_outstanding_cents": sum(l["outstanding_balance_cents"] or 0 for l in loans),
        "delinquent_count": 0,
    }
    for l in loans:
        summary["by_type"][l["loan_type"]] = summary["by_type"].get(l["loan_type"], 0) + 1
        summary["by_status"][l["status"]] = summary["by_status"].get(l["status"], 0) + 1
    return {"loans": loans, "summary": summary}


@router.get("/stats/portfolio")
async def get_loan_portfolio(
    loan_type: Optional[str] = Query(None, description="Filter stats by loan type"),
    current_user: CurrentUser = Depends(require_permission("loans:read")),
):
    where = "WHERE loan_type = :lt" if loan_type else ""
    params = {"lt": loan_type} if loan_type else {}
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM loans {where}"), params).scalar() or 0
        by_status = conn.execute(text(
            f"SELECT status, COUNT(*) as cnt FROM loans {where} GROUP BY status"
        ), params).fetchall()
        by_type = conn.execute(text(
            "SELECT loan_type, COUNT(*) as cnt FROM loans GROUP BY loan_type"
        )).fetchall()
    return {
        "total_loans": total,
        "delinquent_count": 0,
        "by_status": {r[0]: r[1] for r in by_status},
        "by_type": {r[0]: {"count": r[1], "avg_dti": 0} for r in by_type},
    }


@router.get("/{loan_id}/detail")
async def get_loan_detail(
    loan_id: str,
    current_user: CurrentUser = Depends(require_permission("loans:read")),
):
    with engine.connect() as conn:
        loan_row = conn.execute(text(
            "SELECT * FROM loans WHERE id = :lid"
        ), {"lid": loan_id}).fetchone()
        if not loan_row:
            raise HTTPException(status_code=404, detail="Loan not found")
        loan = _row_to_loan(dict(loan_row._mapping))
        cid = loan["customer_id"]

        from src.models.database import customer_pk
        c_pk = customer_pk()
        cust_row = conn.execute(text(
            f"SELECT * FROM customers WHERE {c_pk} = :cid"
        ), {"cid": cid}).fetchone()
        customer = {}
        if cust_row:
            c = dict(cust_row._mapping)
            customer = {
                "customer_id":    c["id"],
                "name":           f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                "email":          c.get("email", ""),
                "age":            None,
                "income":         c.get("annual_income"),
                "income_cents":   int((c.get("annual_income") or 0) * 100),
                "credit_score":   c.get("credit_score"),
                "risk_level":     c.get("aml_risk_rating", "low"),
                "account_type":   c.get("customer_type", ""),
                "balance":        None,
                "balance_cents":  0,
                "account_opened": c.get("created_at", ""),
                "account_age_days": 0,
                "sentiment_avg":  None,
            }

        try:
            ts_row = conn.execute(text(
                "SELECT * FROM trust_scores WHERE customer_id = :cid ORDER BY timestamp DESC LIMIT 1"
            ), {"cid": cid}).fetchone()
        except Exception:
            ts_row = None
        trust_score = {}
        if ts_row:
            ts = dict(ts_row._mapping)
            trust_score = {
                "score":                   ts.get("score"),
                "tier":                    ts.get("tier", ""),
                "account_age_component":   ts.get("account_age_component"),
                "credit_score_component":  ts.get("credit_score_component"),
                "fraud_history_component": ts.get("fraud_history_component"),
                "sentiment_component":     ts.get("sentiment_component"),
                "interaction_component":   ts.get("interaction_component"),
                "timestamp":               ts.get("timestamp", ""),
            }

        fa_rows = conn.execute(text("""
            SELECT alert_id, risk_score, reason, status, timestamp
            FROM   fraud_alerts
            WHERE  customer_id = :cid
            ORDER  BY timestamp DESC LIMIT 10
        """), {"cid": cid}).fetchall()
        fraud_alerts = [dict(r._mapping) for r in fa_rows]

        txn_rows = conn.execute(text("""
            SELECT transaction_id, amount, merchant, category,
                   location, timestamp, is_fraud, merchant_risk
            FROM   enriched_transactions
            WHERE  customer_id = :cid
            ORDER  BY timestamp DESC LIMIT 15
        """), {"cid": cid}).fetchall()
        transactions = []
        for r in txn_rows:
            t = dict(r._mapping)
            amt = float(t.get("amount") or 0)
            transactions.append({
                "id":           t["transaction_id"],
                "amount_cents": int(abs(amt) * 100),
                "type":         "credit" if amt >= 0 else "debit",
                "merchant":     t.get("merchant") or "",
                "category":     t.get("category") or "other",
                "location":     t.get("location") or "",
                "timestamp":    str(t.get("timestamp") or ""),
                "is_fraud":     bool(t.get("is_fraud")),
                "merchant_risk": t.get("merchant_risk") or "low",
            })

        other_rows = conn.execute(text("""
            SELECT id, loan_type, status, amount_cents, outstanding_balance_cents,
                   interest_rate, term_months, origination_date
            FROM   loans
            WHERE  customer_id = :cid AND id != :lid
            ORDER  BY origination_date DESC
            LIMIT  10
        """), {"cid": cid, "lid": loan_id}).fetchall()
        loan_history = []
        for r in other_rows:
            h = dict(r._mapping)
            loan_history.append({
                "id":                h["id"],
                "loan_type":         h["loan_type"],
                "loan_label":        FMT.get(h["loan_type"], ""),
                "status":            h["status"],
                "requested_cents":   int(h.get("amount_cents") or 0),
                "outstanding_cents": int(h.get("outstanding_balance_cents") or 0),
                "interest_rate":     h.get("interest_rate"),
                "term_months":       h.get("term_months"),
                "origination_date":  h.get("origination_date"),
                "is_delinquent":     False,
                "risk_grade":        None,
            })

        has_fraud = len(fraud_alerts) > 0
        open_alerts = sum(1 for a in fraud_alerts if a.get("status") == "open")
        avg_risk = (
            sum(float(a.get("risk_score") or 0) for a in fraud_alerts) / len(fraud_alerts)
            if fraud_alerts else 0.0
        )
        kyc = {
            "identity_verified":    bool(customer.get("credit_score") and customer["credit_score"] > 0),
            "income_verified":      bool(customer.get("income") and customer["income"] > 0),
            "address_verified":     True,
            "document_status":      "verified" if not has_fraud else "under_review",
            "aml_check":            "flagged" if open_alerts > 0 else "clear",
            "pep_check":            "clear",
            "risk_rating":          customer.get("risk_level", "low"),
            "avg_fraud_risk_score": round(avg_risk, 2),
            "total_fraud_alerts":   len(fraud_alerts),
            "open_alerts":          open_alerts,
        }

    return {
        "loan":         loan,
        "customer":     customer,
        "trust_score":  trust_score,
        "fraud_alerts": fraud_alerts,
        "transactions": transactions,
        "loan_history": loan_history,
        "kyc":          kyc,
    }


@router.get("/{loan_id}")
async def get_loan(
    loan_id: str,
    current_user: CurrentUser = Depends(require_permission("loans:read")),
):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT * FROM loans WHERE id = :lid"
        ), {"lid": loan_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Loan not found")
    return _row_to_loan(dict(row._mapping))
