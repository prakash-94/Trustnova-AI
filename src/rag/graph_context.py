"""
Graph RAG context builder for TrustNova AI.

Traverses the SQL FK graph starting from a customer node and enriches the
context with related records (accounts → transactions → loans → fraud_alerts
→ trust_scores).  Each node type gets a tiered freshness score so the LLM
knows how current each piece of data is.

Freshness decay rates (days until score reaches 0):
  customer profile  : 365  — stable demographic / contact data
  accounts          :   7  — balances updated frequently
  transactions      :   1  — very time-sensitive
  loans             :  30  — status changes monthly
  fraud_alerts      :  14  — investigation lifecycle
  trust_scores      :   1  — recomputed per session

Permission-aware traversal:
  • loans node skipped if the caller lacks  loans:read
  • fraud_alerts node skipped if the caller lacks  fraud:read
  (Field-level redaction of AML/KYC fields is handled by rbac_filter AFTER
   this function returns, so we don't duplicate that logic here.)
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy import text
from src.models.database import engine, customer_pk

# Per-node freshness decay in days
_DECAY: dict[str, int] = {
    "customer_profile": 365,
    "accounts":           7,
    "transactions":       1,
    "loans":             30,
    "fraud_alerts":      14,
    "trust_scores":       1,
}


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def _freshness(ts_value: Optional[str | datetime.datetime], node_type: str) -> float:
    """
    Compute freshness score [0.0, 1.0] for a single record.
    1.0 = just created/updated; decays to 0 after _DECAY[node_type] days.
    Returns 0.5 when the timestamp is absent or unparseable.
    """
    decay_days = _DECAY.get(node_type, 365)
    if not ts_value:
        return 0.5
    if isinstance(ts_value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                ts_value = datetime.datetime.strptime(ts_value[:26], fmt)
                break
            except ValueError:
                continue
        else:
            return 0.5
    now = datetime.datetime.utcnow()
    age_days = max(0, (now - ts_value.replace(tzinfo=None)).days)
    return max(0.0, 1.0 - age_days / decay_days)


def _freshness_bar(score: float) -> str:
    """Return a compact ASCII freshness indicator."""
    if score >= 0.90:
        return "●●●● LIVE"
    if score >= 0.70:
        return "●●●○ Recent"
    if score >= 0.40:
        return "●●○○ Ageing"
    return "●○○○ Stale"


def _has_permission(permissions: List[str], required: str) -> bool:
    """Mirror of rbac_filter.has_permission to avoid circular import."""
    cat = required.split(":")[0]
    for p in permissions:
        if p in ("*", required) or p.startswith(cat + ":"):
            return True
    return False


def build_customer_graph_context(
    customer_id: str,
    query: str,
    permissions: Optional[List[str]] = None,
) -> tuple[str, list[dict], float]:
    """
    Build a permission-filtered, freshness-annotated customer graph context.

    Traverses:
      customer → accounts → enriched_transactions → loans* → fraud_alerts* → trust_scores
      (* = skipped when the caller lacks the required permission)

    Returns:
        (context_str, sources, overall_freshness_score)
        context_str   : LLM-ready text block labelled with per-node freshness
        sources       : list of source dicts for the API response
        overall_freshness : weighted average freshness across traversed nodes
    """
    permissions = permissions or []
    can_see_loans  = _has_permission(permissions, "loans:read")
    can_see_fraud  = _has_permission(permissions, "fraud:read")

    pk = customer_pk()

    with engine.connect() as conn:
        # ── Node 1: Customer profile ─────────────────────────────────────────
        cust_row = conn.execute(
            text(f"SELECT * FROM customers WHERE {pk} = :cid"),
            {"cid": customer_id},
        ).fetchone()
        if not cust_row:
            return f"No customer found with ID: {customer_id}\n", [], 0.0
        c = dict(cust_row._mapping)

        # ── Node 2: Accounts ────────────────────────────────────────────────
        acct_rows = conn.execute(text("""
            SELECT account_number, account_type, status, balance_cents,
                   opened_date, updated_at
            FROM accounts WHERE customer_id = :cid
            ORDER BY balance_cents DESC LIMIT 6
        """), {"cid": customer_id}).fetchall()

        # ── Node 3: Recent transactions ─────────────────────────────────────
        txn_rows = conn.execute(text("""
            SELECT amount, merchant, category, timestamp, is_fraud, location
            FROM enriched_transactions
            WHERE customer_id = :cid
            ORDER BY timestamp DESC LIMIT 10
        """), {"cid": customer_id}).fetchall()

        # ── Node 4: Loans (permission-gated) ────────────────────────────────
        loan_rows = []
        if can_see_loans:
            loan_rows = conn.execute(text("""
                SELECT loan_type, status, amount_cents, outstanding_balance_cents,
                       interest_rate, term_months, origination_date
                FROM loans WHERE customer_id = :cid
                ORDER BY origination_date DESC LIMIT 5
            """), {"cid": customer_id}).fetchall()

        # ── Node 5: Fraud alerts (permission-gated) ──────────────────────────
        fraud_rows = []
        if can_see_fraud:
            fraud_rows = conn.execute(text("""
                SELECT risk_score, reason, status, timestamp
                FROM fraud_alerts
                WHERE customer_id = :cid
                ORDER BY timestamp DESC LIMIT 5
            """), {"cid": customer_id}).fetchall()

        # ── Node 6: Trust score ──────────────────────────────────────────────
        ts_row = conn.execute(text("""
            SELECT score, tier, timestamp
            FROM trust_scores
            WHERE customer_id = :cid
            ORDER BY timestamp DESC LIMIT 1
        """), {"cid": customer_id}).fetchone()

    # ── Freshness computation per node ────────────────────────────────────────
    profile_fresh = _freshness(c.get("created_at"), "customer_profile")

    acct_fresh_vals = [
        _freshness(dict(a._mapping).get("updated_at") or dict(a._mapping).get("opened_date"), "accounts")
        for a in acct_rows
    ]
    acct_fresh = sum(acct_fresh_vals) / len(acct_fresh_vals) if acct_fresh_vals else 0.5

    txn_fresh_vals = [
        _freshness(dict(t._mapping).get("timestamp"), "transactions")
        for t in txn_rows
    ]
    txn_fresh = sum(txn_fresh_vals) / len(txn_fresh_vals) if txn_fresh_vals else 0.5

    loan_fresh_vals = [
        _freshness(dict(l._mapping).get("origination_date"), "loans")
        for l in loan_rows
    ]
    loan_fresh = sum(loan_fresh_vals) / len(loan_fresh_vals) if loan_fresh_vals else None

    fraud_fresh_vals = [
        _freshness(dict(f._mapping).get("timestamp"), "fraud_alerts")
        for f in fraud_rows
    ]
    fraud_fresh = sum(fraud_fresh_vals) / len(fraud_fresh_vals) if fraud_fresh_vals else None

    ts_fresh = (
        _freshness(dict(ts_row._mapping).get("timestamp"), "trust_scores")
        if ts_row else None
    )

    # Weighted overall freshness
    weights  = [profile_fresh * 1.0, acct_fresh * 0.8, txn_fresh * 1.0]
    w_sum    = 2.8
    if loan_fresh is not None:
        weights.append(loan_fresh * 0.6)
        w_sum += 0.6
    if fraud_fresh is not None:
        weights.append(fraud_fresh * 0.8)
        w_sum += 0.8
    if ts_fresh is not None:
        weights.append(ts_fresh * 0.5)
        w_sum += 0.5
    overall_freshness = sum(weights) / w_sum if w_sum > 0 else 0.5

    # ── Build context text ────────────────────────────────────────────────────
    name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()

    blocks: list[str] = [
        f"=== CUSTOMER GRAPH — {name.upper()} ===",
        f"Customer ID: {str(customer_id)[:12]} | Graph freshness: {overall_freshness:.0%} | As of {_now_iso()}",
        "",
    ]

    # — Node 1: Profile ————————————————————————————————————————————————
    blocks += [
        f"── [NODE: customer_profile] freshness={profile_fresh:.0%} {_freshness_bar(profile_fresh)} ──",
        f"  Name         : {name}",
        f"  Email        : {c.get('email', 'N/A')}",
        f"  Phone        : {c.get('phone', 'N/A')}",
        f"  Location     : {c.get('address_city', '')}, {c.get('address_state', '')}",
        f"  Segment      : {c.get('segment', 'N/A')}",
        f"  Type         : {c.get('customer_type', 'N/A')}",
        f"  Employment   : {c.get('employment_status', 'N/A')}",
        f"  Annual Income: ${float(c.get('annual_income') or 0):,.0f}",
        f"  Credit Score : {c.get('credit_score', 'N/A')}",
        f"  KYC Status   : {c.get('kyc_status', 'N/A')}",
        f"  AML Risk     : {c.get('aml_risk_rating', 'N/A')}",
        f"  PEP          : {'YES — EDD Required' if c.get('is_pep') else 'No'}",
        f"  Sanctioned   : {'YES — BLOCKED' if c.get('is_sanctioned') else 'No'}",
        f"  Member Since : {str(c.get('created_at', ''))[:10]}",
        "",
    ]

    # — Node 2: Accounts ————————————————————————————————————————————————
    blocks.append(
        f"── [NODE: accounts] freshness={acct_fresh:.0%} {_freshness_bar(acct_fresh)} ──"
    )
    if acct_rows:
        for a in acct_rows:
            ad = dict(a._mapping)
            bal = float(ad.get("balance_cents") or 0) / 100
            f_score = _freshness(ad.get("updated_at") or ad.get("opened_date"), "accounts")
            blocks.append(
                f"  {ad.get('account_type', '').title()} #{ad.get('account_number', '')[:10]}"
                f" | {ad.get('status', '')} | Balance: ${bal:,.2f}"
                f" | [freshness={f_score:.0%}]"
            )
    else:
        blocks.append("  No accounts found.")
    blocks.append("")

    # — Node 3: Transactions ————————————————————————————————————————————
    blocks.append(
        f"── [NODE: transactions] freshness={txn_fresh:.0%} {_freshness_bar(txn_fresh)} ──"
    )
    if txn_rows:
        blocks.append(f"  {'Date':<12} {'Merchant':<25} {'Category':<18} {'Amount':>10} {'Flag'}")
        for t in txn_rows:
            td = dict(t._mapping)
            amt = float(td.get("amount") or 0)
            flag = "⚠ FRAUD" if td.get("is_fraud") else ""
            blocks.append(
                f"  {str(td.get('timestamp',''))[:10]:<12}"
                f" {str(td.get('merchant',''))[:23]:<25}"
                f" {str(td.get('category',''))[:16]:<18}"
                f" ${abs(amt):>9,.2f} {flag}"
            )
    else:
        blocks.append("  No transactions found.")
    blocks.append("")

    # — Node 4: Loans (permission-gated) ——————————————————————————————
    if can_see_loans:
        blocks.append(
            f"── [NODE: loans] freshness={loan_fresh:.0%} {_freshness_bar(loan_fresh)} ──"
            if loan_fresh is not None
            else "── [NODE: loans] ──"
        )
        if loan_rows:
            for l in loan_rows:
                ld = dict(l._mapping)
                amt = float(ld.get("amount_cents") or 0) / 100
                outstanding = float(ld.get("outstanding_balance_cents") or 0) / 100
                lf = _freshness(ld.get("origination_date"), "loans")
                blocks.append(
                    f"  {ld.get('loan_type', '').title()} | {ld.get('status', '')}"
                    f" | Original: ${amt:,.0f} | Outstanding: ${outstanding:,.0f}"
                    f" | Rate: {float(ld.get('interest_rate') or 0):.2f}%"
                    f" | [freshness={lf:.0%}]"
                )
        else:
            blocks.append("  No loans found.")
        blocks.append("")

    # — Node 5: Fraud alerts (permission-gated) ——————————————————————
    if can_see_fraud:
        blocks.append(
            f"── [NODE: fraud_alerts] freshness={fraud_fresh:.0%} {_freshness_bar(fraud_fresh)} ──"
            if fraud_fresh is not None
            else "── [NODE: fraud_alerts] ──"
        )
        if fraud_rows:
            for f in fraud_rows:
                fd = dict(f._mapping)
                score = float(fd.get("risk_score") or 0)
                ff = _freshness(fd.get("timestamp"), "fraud_alerts")
                blocks.append(
                    f"  Score: {score*100:.0f}% | {fd.get('status', '')} "
                    f"| {str(fd.get('reason', ''))[:60]}"
                    f" | {str(fd.get('timestamp', ''))[:10]}"
                    f" | [freshness={ff:.0%}]"
                )
        else:
            blocks.append("  No fraud alerts.")
        blocks.append("")

    # — Node 6: Trust score ————————————————————————————————————————————
    if ts_row:
        tsd = dict(ts_row._mapping)
        ts_f = ts_fresh if ts_fresh is not None else 0.5
        blocks.append(
            f"── [NODE: trust_score] freshness={ts_f:.0%} {_freshness_bar(ts_f)} ──"
        )
        blocks.append(
            f"  Score: {float(tsd.get('score', 0)):.0f}/100"
            f" ({tsd.get('tier', '')} tier)"
            f" | Last updated: {str(tsd.get('timestamp', ''))[:10]}"
        )
        blocks.append("")

    blocks.append(
        f"Graph source: customers→accounts→enriched_transactions"
        + ("→loans" if can_see_loans else "")
        + ("→fraud_alerts" if can_see_fraud else "")
        + "→trust_scores"
        + f" | Overall freshness: {overall_freshness:.0%}"
    )

    source_entry = {
        "document": f"[Graph] Customer: {name}",
        "page": f"multi-hop · freshness {overall_freshness:.0%}",
        "freshness": round(overall_freshness, 2),
        "source_type": "graph_database",
    }

    return "\n".join(blocks), [source_entry], overall_freshness