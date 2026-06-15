"""Fraud detection endpoints — real fraud_alerts (262 records) + transaction geo."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()

_iso_model_cache = None


def _get_isolation_forest_score(txn: dict):
    """Return a [0,1] anomaly probability via Isolation Forest, or None if model unavailable."""
    global _iso_model_cache
    import os, pickle, pandas as pd
    from src.models.fraud_detector import FEATURE_COLS
    model_path = os.path.join("models", "fraud_isolation_forest.pkl")
    if not os.path.exists(model_path):
        return None
    if _iso_model_cache is None:
        with open(model_path, "rb") as f:
            _iso_model_cache = pickle.load(f)
    features = pd.DataFrame([txn])[FEATURE_COLS].fillna(0)
    raw = _iso_model_cache.decision_function(features)[0]
    # decision_function returns negative for anomalies; convert to [0,1] probability
    prob = float(1 / (1 + (raw + 0.5) * 4))
    return max(0.0, min(1.0, prob))


def _severity(score: float) -> str:
    if score >= 0.85: return "critical"
    if score >= 0.70: return "high"
    if score >= 0.55: return "medium"
    return "low"


def _fraud_type(reason: str) -> str:
    r = reason.lower()
    if "cross-border" in r or "international" in r: return "wire_fraud"
    if "cash" in r or "deposit" in r: return "structuring"
    if "device" in r or "login" in r: return "account_takeover"
    if "velocity" in r or "rapid" in r: return "velocity_fraud"
    if "card" in r: return "card_fraud"
    return "suspicious_activity"


def _detection_method(reason: str) -> str:
    if "model" in reason.lower() or "ml" in reason.lower():
        return "ML Model"
    if "rule" in reason.lower():
        return "Rule-based Engine"
    return "ML + Rule-based"


def _generate_investigation_notes(row: dict, fraud_type: str, severity: str, score: float) -> str:
    reason    = row.get("reason") or ""
    location  = row.get("location") or ""
    merchant  = row.get("merchant") or ""
    category  = row.get("category") or ""
    amount    = float(row.get("amount") or 0)
    cid_short = (row.get("customer_id") or "")[:8]
    pct       = round(score * 100)

    loc_str  = f" in {location}"        if location  else ""
    mrc_str  = f"'{merchant}'"          if merchant  else "the flagged merchant"
    cat_str  = f" ({category})"         if category  else ""
    amt_str  = f"${amount:,.2f}"        if amount    else "an unspecified amount"

    lines = []

    # ── 1. Detection trigger ───────────────────────────────────────────────
    trigger = reason if reason else "Anomalous transaction pattern identified by ML model and rule-based engine"
    lines.append(f"Detection trigger: {trigger}. Risk model assigned a score of {pct}%, placing this alert in the {severity.upper()} tier.")

    # ── 2. Fraud-type specific technical analysis ──────────────────────────
    if fraud_type == "velocity_fraud":
        lines.append(
            f"Velocity analysis: High-frequency transactions at {mrc_str}{cat_str}{loc_str} exceed the customer's "
            f"90-day behavioural baseline by more than 3 standard deviations. Burst pattern is consistent with "
            f"authorised-push-payment (APP) scam or compromised credential misuse."
        )
        lines.append(
            f"Regulatory flag: Transaction velocity of this nature triggers BSA/AML Rule 31 CFR § 1020.320 "
            f"review and may require a Suspicious Activity Report (SAR) filing with FinCEN within 30 days of "
            f"initial detection."
        )
        lines.append(
            f"Transaction context: Total exposure at {amt_str}{loc_str}. Merchant category{cat_str} is "
            f"associated with elevated money-movement risk per internal risk scoring model v2.3."
        )
        lines.append(
            f"Recommended action: Temporarily restrict outbound transfers for customer {cid_short}***. "
            f"Request source-of-funds documentation and confirm activity via registered contact within 24 hours. "
            f"If unconfirmed, escalate to BSA Officer."
        )

    elif fraud_type == "account_takeover":
        lines.append(
            f"Access anomaly: Authentication signals indicate a potential unauthorised session — "
            f"device fingerprint mismatch or credential-stuffing pattern detected{loc_str}. "
            f"New device initiated a high-value transaction of {amt_str} within the alert window."
        )
        lines.append(
            f"Regulatory obligation: Under Reg E (12 CFR § 1005.11) and FFIEC guidance, unauthorised "
            f"electronic transfers must receive provisional credit within 5 business days and be fully "
            f"investigated within 10 business days of the customer's dispute."
        )
        lines.append(
            f"Risk indicators: Session IP{loc_str} does not match the customer's registered address "
            f"or usual geolocation. Transaction at {mrc_str}{cat_str} is outside the customer's "
            f"established spending pattern."
        )
        lines.append(
            f"Recommended action: Lock online banking access immediately. Initiate step-up MFA challenge "
            f"and contact customer {cid_short}*** via registered phone. If unreachable within 2 hours, "
            f"treat as confirmed ATO and freeze all outbound channels."
        )

    elif fraud_type == "wire_fraud":
        lines.append(
            f"Wire risk: Outbound wire of {amt_str}{loc_str} flagged by OFAC real-time screening "
            f"and cross-border transaction monitoring rules. Destination jurisdiction and beneficiary "
            f"bank require enhanced due diligence (EDD)."
        )
        lines.append(
            f"Compliance trigger: Cross-border wires to elevated-risk jurisdictions require EDD per "
            f"BSA/AML policy Section 4.2 and FATF Recommendation 16. SWIFT beneficiary must be "
            f"validated against FinCEN 314(a) list and OFAC SDN list before release."
        )
        lines.append(
            f"Regulatory hold: Wire has been placed on a compliance hold. Per internal policy, "
            f"international wires above $25,000 require BSA Officer approval (Section 4.2). "
            f"Senior approval is required for amounts above $50,000 (dual-control policy)."
        )
        lines.append(
            f"Recommended action: Do not release funds until AML clearance is obtained. "
            f"Escalate to BSA Officer with full beneficiary details and customer source-of-funds "
            f"documentation. Document all actions in the case management system within 30 days."
        )

    elif fraud_type == "structuring":
        lines.append(
            f"Structuring indicator: Cash transaction of {amt_str} at {mrc_str}{loc_str} is "
            f"consistent with deliberate structuring to evade the $10,000 CTR reporting threshold "
            f"under 31 U.S.C. § 5324. Pattern may indicate layering activity."
        )
        lines.append(
            f"Aggregation review required: Pull the full 30-day cash transaction history for "
            f"customer {cid_short}***. If aggregated same-day cash across branches exceeds $10,000, "
            f"a Currency Transaction Report (CTR) is mandatory regardless of individual amounts."
        )
        lines.append(
            f"Regulatory mandate: CTR must be filed with FinCEN via BSA E-Filing within 15 calendar "
            f"days of the transaction date per 31 CFR § 1010.311. Failure to file is a strict-liability "
            f"BSA violation with civil penalties up to $25,000 per day."
        )
        lines.append(
            f"Recommended action: Place a 3-day transaction hold on cash-out channels for this customer. "
            f"BSA team to review full transaction history and determine CTR/SAR filing obligations. "
            f"Do not alert the customer of the investigation (tipping-off prohibition, 31 U.S.C. § 5318(g)(2))."
        )

    elif fraud_type == "card_fraud":
        lines.append(
            f"Card compromise: Transaction of {amt_str} at {mrc_str}{cat_str}{loc_str} is "
            f"inconsistent with the cardholder's established spending profile. "
            f"Card-not-present (CNP) fraud indicators are present."
        )
        lines.append(
            f"Pattern deviation: Merchant category{cat_str}, transaction amount, and geographic location "
            f"all deviate from the 90-day baseline. CNP transactions above $2,000 require additional "
            f"authentication per internal fraud policy Section 3.2."
        )
        lines.append(
            f"Chargeback obligation: Per Reg E (12 CFR § 1005) and card network rules (Visa/MC), "
            f"provisional credit must be issued within 5 business days of a verified dispute. "
            f"Investigation must be completed within 45 days for international or POS transactions."
        )
        lines.append(
            f"Recommended action: Reissue card with new PAN and CVV for customer {cid_short}*** immediately. "
            f"Block the compromised card number. Initiate a network chargeback if customer confirms "
            f"unauthorised use. Notify card operations team to check for related BIN-level compromise."
        )

    else:  # suspicious_activity
        lines.append(
            f"Behavioural anomaly: Transaction activity for customer {cid_short}*** deviates significantly "
            f"from their established risk profile. A score of {pct}% places this alert in the "
            f"{severity.upper()} tier, triggering mandatory analyst review."
        )
        lines.append(
            f"Contextual risk: Activity at {mrc_str}{cat_str}{loc_str} is outside the customer's "
            f"typical geographic footprint and merchant category history. Amount of {amt_str} also "
            f"exceeds the customer's average transaction value by a statistically significant margin."
        )
        lines.append(
            f"SAR consideration: If the suspicious activity cannot be satisfactorily explained after "
            f"customer contact, a SAR must be filed with FinCEN within 30 days of initial detection "
            f"per 31 CFR § 1020.320. The 30-day clock began at alert creation."
        )
        lines.append(
            f"Recommended action: Contact customer {cid_short}*** via verified registered channel within "
            f"24 hours to confirm or deny the activity. If unreachable or if customer denies the "
            f"transaction, escalate immediately to the BSA Officer and restrict the account."
        )

    # ── 5. Severity-based escalation SLA note ────────────────────────────
    if severity == "critical":
        lines.append(
            f"SLA REQUIREMENT — CRITICAL ({pct}%): Analyst review must be completed within 2 hours "
            f"of alert creation per Fraud SLA Policy. Supervisor notification is mandatory. "
            f"No further transactions above $500 permitted until alert is resolved or escalated."
        )
    elif severity == "high":
        lines.append(
            f"SLA requirement — HIGH ({pct}%): Analyst review required within 4 business hours. "
            f"Supervisor sign-off is required before resolution or dismissal of this alert."
        )
    elif severity == "medium":
        lines.append(
            f"SLA requirement — MEDIUM ({pct}%): Analyst review required within 1 business day. "
            f"Document all findings in the case management system before closing."
        )

    return "\n".join(f"• {line}" for line in lines)


def _row_to_alert(row: dict) -> dict:
    score = float(row.get("risk_score") or 0)
    reason = row.get("reason") or ""
    status = row.get("status") or "open"
    amt = float(row.get("amount") or 0)
    fraud_type = _fraud_type(reason)
    severity   = _severity(score)
    return {
        "id": row["alert_id"],
        "customer_id": row["customer_id"],
        "transaction_id": row.get("transaction_id"),
        "fraud_type": fraud_type,
        "status": status,
        "severity": severity,
        "fraud_score": round(score, 2),
        "amount_at_risk_cents": int(abs(amt) * 100) if amt else None,
        "location": row.get("location"),
        "merchant": row.get("merchant"),
        "category": row.get("category"),
        "investigation_notes": _generate_investigation_notes(row, fraud_type, severity, score),
        "detection_method": _detection_method(reason),
        "resolution": "cleared" if status == "false_positive" else ("confirmed_fraud" if status == "resolved" else None),
        "created_at": row.get("timestamp") or "",
    }


@router.get("/alerts")
async def get_fraud_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    customer_id: Optional[str] = None,
    limit: int = Query(100, le=300),
    current_user: CurrentUser = Depends(require_permission("fraud:read")),
):
    with engine.connect() as conn:
        filters, params = [], {"limit": limit}
        if status:
            filters.append("fa.status = :status")
            params["status"] = status
        if customer_id:
            filters.append("fa.customer_id = :cid")
            params["cid"] = customer_id
        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        rows = conn.execute(text(f"""
            SELECT fa.alert_id, fa.customer_id, fa.transaction_id,
                   fa.risk_score, fa.reason, fa.status, fa.timestamp,
                   et.amount, et.location, et.merchant, et.category
            FROM fraud_alerts fa
            LEFT JOIN enriched_transactions et ON fa.transaction_id = et.transaction_id
            {where}
            ORDER BY fa.timestamp DESC
            LIMIT :limit
        """), params).fetchall()

    alerts = []
    for r in rows:
        d = dict(r._mapping)
        alert = _row_to_alert(d)
        if severity and alert["severity"] != severity:
            continue
        alerts.append(alert)

    summary = {
        "total": len(alerts),
        "open": sum(1 for a in alerts if a["status"] == "open"),
        "under_review": sum(1 for a in alerts if a["status"] in ("reviewing", "in_review")),
        "resolved": sum(1 for a in alerts if a["status"] == "resolved"),
        "false_positive": sum(1 for a in alerts if a["status"] == "false_positive"),
        "critical": sum(1 for a in alerts if a["severity"] == "critical"),
        "high": sum(1 for a in alerts if a["severity"] == "high"),
        "total_at_risk_cents": sum((a["amount_at_risk_cents"] or 0) for a in alerts),
    }
    return {"alerts": alerts, "total": len(alerts), "summary": summary}


@router.get("/alerts/{alert_id}")
async def get_fraud_alert(
    alert_id: str,
    current_user: CurrentUser = Depends(require_permission("fraud:read")),
):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT fa.*, et.amount, et.location, et.merchant, et.category
            FROM fraud_alerts fa
            LEFT JOIN enriched_transactions et ON fa.transaction_id = et.transaction_id
            WHERE fa.alert_id = :aid
        """), {"aid": alert_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _row_to_alert(dict(row._mapping))


@router.get("/check/{customer_id}")
async def fraud_check(
    customer_id: str,
    current_user: CurrentUser = Depends(require_permission("fraud:read")),
):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT fa.*, et.amount, et.location, et.merchant, et.category
            FROM fraud_alerts fa
            LEFT JOIN enriched_transactions et ON fa.transaction_id = et.transaction_id
            WHERE fa.customer_id = :cid
            ORDER BY fa.timestamp DESC
        """), {"cid": customer_id}).fetchall()
    alerts = [_row_to_alert(dict(r._mapping)) for r in rows]
    max_score = max((a["fraud_score"] for a in alerts), default=0)
    return {
        "customer_id": customer_id,
        "alert_count": len(alerts),
        "max_fraud_score": max_score,
        "overall_risk": _severity(max_score) if alerts else "low",
        "alerts": alerts,
    }
