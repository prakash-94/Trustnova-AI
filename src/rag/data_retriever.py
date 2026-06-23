"""
Hybrid Enterprise RAG — structured data retriever.
Fetches live records from SQLite for each intent type and formats them
as LLM-ready context blocks with metadata-rich source citations.
"""
from __future__ import annotations
import datetime
from typing import List, Optional
from sqlalchemy import text
from src.models.database import engine, customer_pk


# ── helpers ──────────────────────────────────────────────────────────────────

def _db_source(label: str, table: str, count: int) -> dict:
    return {
        "document": f"[DB] {label}",
        "page": f"{count} records · live data",
        "freshness": 1.0,
        "source_type": "database",
        "table": table,
    }


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


# ── Risk Profiles ─────────────────────────────────────────────────────────────

def get_risk_profiles(query: str, limit: int = 30) -> tuple[str, list[dict]]:
    """
    Return customer risk profiles from DB.
    Detects 'high'/'medium'/'low'/'critical' in the query to filter.
    """
    q = query.lower()

    # Determine risk filter
    if any(w in q for w in ("high", "critical")):
        risk_filter = ("high", "very high")
        label = "High / Critical Risk Customers"
    elif "medium" in q:
        risk_filter = ("medium",)
        label = "Medium Risk Customers"
    elif "low" in q:
        risk_filter = ("low",)
        label = "Low Risk Customers"
    else:
        risk_filter = None
        label = "All Risk Profiles"

    pk = customer_pk()
    with engine.connect() as conn:
        if risk_filter:
            placeholders = ", ".join(f":r{i}" for i in range(len(risk_filter)))
            params = {f"r{i}": v for i, v in enumerate(risk_filter)}
            params["lim"] = limit
            rows = conn.execute(text(f"""
                SELECT {pk} AS cid, first_name, last_name, email,
                       credit_score, aml_risk_rating,
                       annual_income, is_pep, is_sanctioned, created_at
                FROM   customers
                WHERE  LOWER(aml_risk_rating) IN ({placeholders})
                ORDER  BY credit_score ASC NULLS LAST
                LIMIT  :lim
            """), params).fetchall()
        else:
            rows = conn.execute(text(f"""
                SELECT {pk} AS cid, first_name, last_name, email,
                       credit_score, aml_risk_rating,
                       annual_income, is_pep, is_sanctioned, created_at
                FROM   customers
                ORDER  BY CASE LOWER(aml_risk_rating)
                    WHEN 'very high' THEN 1 WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3 ELSE 4 END,
                  credit_score ASC NULLS LAST
                LIMIT  :lim
            """), {"lim": limit}).fetchall()

        # Fraud alert counts per customer
        fa_map: dict[str, int] = {}
        try:
            fa_rows = conn.execute(text(
                "SELECT customer_id, COUNT(*) AS cnt FROM fraud_alerts GROUP BY customer_id"
            )).fetchall()
            fa_map = {r[0]: r[1] for r in fa_rows}
        except Exception:
            pass

        # Trust scores
        ts_map: dict[str, float] = {}
        try:
            ts_rows = conn.execute(text("""
                SELECT customer_id, score FROM trust_scores
                WHERE  (customer_id, timestamp) IN (
                    SELECT customer_id, MAX(timestamp) FROM trust_scores GROUP BY customer_id
                )
            """)).fetchall()
            ts_map = {r[0]: float(r[1]) for r in ts_rows}
        except Exception:
            pass

    if not rows:
        return f"No customers found matching the risk filter '{label}'.\n", []

    lines = [
        f"=== {label.upper()} ===",
        f"Retrieved: {_now_iso()} | Total shown: {len(rows)}",
        "",
        f"{'#':<4} {'Name':<22} {'ID':<12} {'Risk Level':<12} {'Credit':<8} "
        f"{'Fraud Alerts':<14} {'Trust Score':<13} {'PEP':<5} {'Income':>12}",
        "-" * 100,
    ]

    for i, r in enumerate(rows, 1):
        d = dict(r._mapping)
        cid = str(d.get("cid", ""))
        name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
        risk = (d.get("aml_risk_rating") or "unknown").capitalize()
        credit = str(d.get("credit_score") or "—")
        fraud_cnt = str(fa_map.get(cid, 0))
        ts = f"{ts_map[cid]:.0f}/100" if cid in ts_map else "—"
        pep = "YES" if d.get("is_pep") else "No"
        income = f"${float(d.get('annual_income') or 0):,.0f}"
        lines.append(
            f"{i:<4} {name:<22} {cid[:10]:<12} {risk:<12} {credit:<8} "
            f"{fraud_cnt:<14} {ts:<13} {pep:<5} {income:>12}"
        )

    lines += ["", f"Data source: customers + fraud_alerts + trust_scores tables | As of {_now_iso()}"]
    return "\n".join(lines), [_db_source(label, "customers", len(rows))]


# ── Fraud Alerts ──────────────────────────────────────────────────────────────

def get_fraud_data(query: str, customer_id: Optional[str] = None, limit: int = 20) -> tuple[str, list[dict]]:
    q = query.lower()
    status_filter = None
    if "open" in q:
        status_filter = "open"
    elif "resolved" in q:
        status_filter = "resolved"

    with engine.connect() as conn:
        pk = customer_pk()
        params: dict = {"lim": limit}
        filters = []
        if customer_id:
            filters.append("fa.customer_id = :cid")
            params["cid"] = customer_id
        if status_filter:
            filters.append("fa.status = :status")
            params["status"] = status_filter
        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        rows = conn.execute(text(f"""
            SELECT fa.alert_id, fa.customer_id, fa.risk_score, fa.reason,
                   fa.status, fa.timestamp,
                   c.first_name, c.last_name, c.aml_risk_rating
            FROM   fraud_alerts fa
            LEFT   JOIN customers c ON fa.customer_id = c.{pk}
            {where}
            ORDER  BY fa.risk_score DESC, fa.timestamp DESC
            LIMIT  :lim
        """), params).fetchall()

        total_open = conn.execute(text(
            "SELECT COUNT(*) FROM fraud_alerts WHERE status = 'open'"
        )).scalar() or 0

    if not rows:
        return "No fraud alerts found matching the query.\n", []

    label = f"{'Customer ' + customer_id[:8] if customer_id else 'Institution-wide'} Fraud Alerts"
    lines = [
        f"=== FRAUD ALERTS — {label.upper()} ===",
        f"Total open alerts: {total_open} | Retrieved: {_now_iso()}",
        "",
        f"{'Alert ID':<16} {'Customer':<22} {'Score':>6} {'Severity':<10} {'Status':<14} {'Reason':<40} {'Date'}",
        "-" * 120,
    ]

    for r in rows:
        d = dict(r._mapping)
        alert_id = str(d.get("alert_id", ""))[:14]
        name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip() or d.get("customer_id", "")[:8]
        score = float(d.get("risk_score") or 0)
        sev = "Critical" if score >= 0.85 else ("High" if score >= 0.70 else ("Medium" if score >= 0.55 else "Low"))
        status = str(d.get("status") or "open").replace("_", " ").title()
        reason = str(d.get("reason") or "")[:38]
        date = str(d.get("timestamp") or "")[:10]
        lines.append(
            f"{alert_id:<16} {name:<22} {score*100:>5.0f}% {sev:<10} {status:<14} {reason:<40} {date}"
        )

    lines += ["", f"Data source: fraud_alerts table | As of {_now_iso()}"]
    return "\n".join(lines), [_db_source(label, "fraud_alerts", len(rows))]


# ── Customer 360 ──────────────────────────────────────────────────────────────

def get_customer_360(
    query: str,
    customer_id: Optional[str] = None,
    permissions: Optional[List[str]] = None,
) -> tuple[str, list[dict]]:
    """
    Full customer graph context including accounts, transactions, loans (if permitted),
    fraud alerts (if permitted), and trust score.

    Uses GraphContextBuilder for tiered freshness scoring and permission-aware
    node traversal.
    """
    from src.rag.graph_context import build_customer_graph_context

    pk = customer_pk()
    searched_name: Optional[str] = None

    # Resolve customer ID from name when not provided
    if not customer_id:
        searched_name = _extract_name_from_query(query)
        if searched_name:
            with engine.connect() as conn:
                row = conn.execute(text(f"""
                    SELECT * FROM customers
                    WHERE LOWER(first_name || ' ' || last_name) LIKE :nm
                    LIMIT 1
                """), {"nm": f"%{searched_name.lower()}%"}).fetchone()
                if row:
                    customer_id = str(dict(row._mapping).get(pk, ""))

    if not customer_id:
        if searched_name:
            return (
                f"No customer found matching the name '{searched_name}'.\n"
                f"The name may be misspelled or the customer may not exist in the system. "
                f"Please verify the spelling or search by Customer ID.\n",
                [],
            )
        return "No customer specified. Please provide a customer name or ID.\n", []

    ctx, sources, _ = build_customer_graph_context(
        customer_id=customer_id,
        query=query,
        permissions=permissions or [],
    )
    return ctx, sources


# ── Transactions ──────────────────────────────────────────────────────────────

def get_transactions(query: str, customer_id: Optional[str] = None, limit: int = 25) -> tuple[str, list[dict]]:
    with engine.connect() as conn:
        params: dict = {"lim": limit}
        filters = []
        if customer_id:
            filters.append("customer_id = :cid")
            params["cid"] = customer_id
        q = query.lower()
        if "fraud" in q or "flagged" in q:
            filters.append("is_fraud = 1")
        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        rows = conn.execute(text(f"""
            SELECT transaction_id, customer_id, amount, merchant, category,
                   location, timestamp, is_fraud, merchant_risk
            FROM   enriched_transactions
            {where}
            ORDER  BY timestamp DESC
            LIMIT  :lim
        """), params).fetchall()

    if not rows:
        return "No transactions found.\n", []

    label = f"{'Customer ' + customer_id[:8] if customer_id else 'Recent'} Transactions"
    lines = [
        f"=== {label.upper()} ===",
        f"Retrieved: {_now_iso()} | Count: {len(rows)}",
        "",
        f"{'Date':<12} {'Customer':<12} {'Merchant':<28} {'Category':<18} {'Amount':>10} {'Flag':<8} {'Location'}",
        "-" * 110,
    ]
    for r in rows:
        d = dict(r._mapping)
        amt = float(d.get("amount") or 0)
        flag = "FRAUD" if d.get("is_fraud") else ""
        lines.append(
            f"{str(d.get('timestamp', ''))[:10]:<12} "
            f"{str(d.get('customer_id', ''))[:10]:<12} "
            f"{str(d.get('merchant', ''))[:26]:<28} "
            f"{str(d.get('category', ''))[:16]:<18} "
            f"${abs(amt):>9,.2f} "
            f"{flag:<8} "
            f"{str(d.get('location', ''))[:20]}"
        )
    lines += ["", f"Data source: enriched_transactions table | As of {_now_iso()}"]
    return "\n".join(lines), [_db_source(label, "enriched_transactions", len(rows))]


# ── Loans ─────────────────────────────────────────────────────────────────────

def get_loans(query: str, customer_id: Optional[str] = None, limit: int = 25) -> tuple[str, list[dict]]:
    with engine.connect() as conn:
        params: dict = {"lim": limit}
        filters = []
        if customer_id:
            filters.append("l.customer_id = :cid")
            params["cid"] = customer_id
        q_lower = query.lower()
        if "pending" in q_lower:
            filters.append("l.status = 'pending'")
        elif "active" in q_lower:
            filters.append("l.status = 'active'")
        elif "delinquent" in q_lower or "overdue" in q_lower:
            filters.append("l.status IN ('delinquent','defaulted','past_due')")
        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        highest_terms = ("highest", "largest", "biggest", "maximum", "max ", "top ")
        lowest_terms = ("lowest", "smallest", "minimum", "min ")
        is_highest = any(term in q_lower for term in highest_terms)
        is_lowest = any(term in q_lower for term in lowest_terms)
        amount_field = "l.outstanding_balance_cents" if "outstanding" in q_lower else "l.amount_cents"
        if is_highest:
            order_by = f"{amount_field} DESC"
            params["lim"] = 1
        elif is_lowest:
            order_by = f"{amount_field} ASC"
            params["lim"] = 1
        else:
            order_by = "l.origination_date DESC"

        pk = customer_pk()
        rows = conn.execute(text(f"""
            SELECT l.id, l.customer_id, l.loan_type, l.status,
                   l.amount_cents, l.outstanding_balance_cents,
                   l.interest_rate, l.term_months, l.origination_date,
                   c.first_name, c.last_name
            FROM   loans l
            LEFT   JOIN customers c ON l.customer_id = c.{pk}
            {where}
            ORDER  BY {order_by}
            LIMIT  :lim
        """), params).fetchall()

        total_loans = conn.execute(text("SELECT COUNT(*) FROM loans")).scalar() or 0
        active = conn.execute(text("SELECT COUNT(*) FROM loans WHERE status='active'")).scalar() or 0

    if not rows:
        return "No loans found.\n", []

    label = f"{'Customer ' + customer_id[:8] if customer_id else 'Loan Portfolio'}"
    lines = [
        f"=== LOAN PORTFOLIO — {label.upper()} ===",
        f"Total loans: {total_loans} | Active: {active} | Retrieved: {_now_iso()}",
        "",
        f"{'Customer':<22} {'Type':<12} {'Status':<14} {'Amount':>12} {'Outstanding':>13} {'Rate':>6} {'Term':>6} {'Date'}",
        "-" * 110,
    ]
    if is_highest or is_lowest:
        top = dict(rows[0]._mapping)
        top_name = f"{top.get('first_name', '')} {top.get('last_name', '')}".strip() or str(top.get("customer_id", ""))[:8]
        selected_cents = top.get("outstanding_balance_cents") if "outstanding" in q_lower else top.get("amount_cents")
        metric = "outstanding loan balance" if "outstanding" in q_lower else "original loan amount"
        direction = "highest" if is_highest else "lowest"
        lines.extend([
            f"ANSWER: {top_name} (customer ID: {top.get('customer_id')}) has the {direction} {metric}: "
            f"${float(selected_cents or 0) / 100:,.2f}.",
            "",
        ])
    for r in rows:
        d = dict(r._mapping)
        name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip() or str(d.get("customer_id", ""))[:8]
        amt = float(d.get("amount_cents") or 0) / 100
        outstanding = float(d.get("outstanding_balance_cents") or 0) / 100
        rate = f"{float(d.get('interest_rate') or 0):.2f}%"
        term = f"{d.get('term_months') or 0}mo"
        lines.append(
            f"{name:<22} {str(d.get('loan_type', '')):<12} {str(d.get('status', '')):<14} "
            f"${amt:>11,.0f} ${outstanding:>12,.0f} {rate:>6} {term:>6} {str(d.get('origination_date', ''))[:10]}"
        )
    lines += ["", f"Data source: loans table | As of {_now_iso()}"]
    return "\n".join(lines), [_db_source(label, "loans", len(rows))]


# ── Accounts ──────────────────────────────────────────────────────────────────

def get_accounts(query: str, customer_id: Optional[str] = None, limit: int = 25) -> tuple[str, list[dict]]:
    with engine.connect() as conn:
        params: dict = {"lim": limit}
        filters = []
        if customer_id:
            filters.append("a.customer_id = :cid")
            params["cid"] = customer_id
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        pk = customer_pk()
        rows = conn.execute(text(f"""
            SELECT a.id, a.customer_id, a.account_number, a.account_type,
                   a.status, a.balance_cents, a.opened_date,
                   c.first_name, c.last_name
            FROM   accounts a
            LEFT   JOIN customers c ON a.customer_id = c.{pk}
            {where}
            ORDER  BY a.balance_cents DESC
            LIMIT  :lim
        """), params).fetchall()

    if not rows:
        return "No accounts found.\n", []

    label = f"{'Customer ' + customer_id[:8] if customer_id else 'Account Portfolio'}"
    lines = [
        f"=== ACCOUNTS — {label.upper()} ===",
        f"Retrieved: {_now_iso()} | Count: {len(rows)}",
        "",
        f"{'Customer':<22} {'Account #':<16} {'Type':<14} {'Status':<10} {'Balance':>14} {'Opened'}",
        "-" * 95,
    ]
    for r in rows:
        d = dict(r._mapping)
        name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip() or str(d.get("customer_id", ""))[:8]
        bal = float(d.get("balance_cents") or 0) / 100
        lines.append(
            f"{name:<22} {str(d.get('account_number', '')):<16} {str(d.get('account_type', '')):<14} "
            f"{str(d.get('status', '')):<10} ${bal:>13,.2f} {str(d.get('opened_date', ''))[:10]}"
        )
    lines += ["", f"Data source: accounts table | As of {_now_iso()}"]
    return "\n".join(lines), [_db_source(label, "accounts", len(rows))]


# ── Trust Scores ──────────────────────────────────────────────────────────────

def get_trust_scores(query: str, customer_id: Optional[str] = None, limit: int = 20) -> tuple[str, list[dict]]:
    pk = customer_pk()
    with engine.connect() as conn:
        if customer_id:
            rows = conn.execute(text(f"""
                SELECT ts.customer_id, ts.score, ts.tier, ts.timestamp,
                       c.first_name, c.last_name, c.aml_risk_rating
                FROM   trust_scores ts
                LEFT   JOIN customers c ON ts.customer_id = c.{pk}
                WHERE  ts.customer_id = :cid
                ORDER  BY ts.timestamp DESC LIMIT :lim
            """), {"cid": customer_id, "lim": limit}).fetchall()
        else:
            rows = conn.execute(text(f"""
                SELECT ts.customer_id, ts.score, ts.tier, ts.timestamp,
                       c.first_name, c.last_name, c.aml_risk_rating
                FROM   trust_scores ts
                INNER  JOIN (
                    SELECT customer_id, MAX(timestamp) AS mt
                    FROM   trust_scores GROUP BY customer_id
                ) latest ON ts.customer_id = latest.customer_id AND ts.timestamp = latest.mt
                LEFT   JOIN customers c ON ts.customer_id = c.{pk}
                ORDER  BY ts.score DESC
                LIMIT  :lim
            """), {"lim": limit}).fetchall()

    if not rows:
        return "No trust scores found.\n", []

    label = f"{'Customer ' + customer_id[:8] if customer_id else 'Trust Score Summary'}"
    lines = [
        f"=== TRUST SCORES — {label.upper()} ===",
        f"Retrieved: {_now_iso()} | Count: {len(rows)}",
        "",
        f"{'Customer':<22} {'ID':<12} {'Score':>7} {'Tier':<12} {'AML Risk':<12} {'Last Updated'}",
        "-" * 80,
    ]
    for r in rows:
        d = dict(r._mapping)
        name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip() or d.get("customer_id", "")[:8]
        cid = str(d.get("customer_id", ""))[:10]
        score = float(d.get("score") or 0)
        tier = str(d.get("tier") or "")
        risk = str(d.get("aml_risk_rating") or "")
        updated = str(d.get("timestamp") or "")[:10]
        lines.append(f"{name:<22} {cid:<12} {score:>6.1f} {tier:<12} {risk:<12} {updated}")
    lines += ["", f"Data source: trust_scores table | As of {_now_iso()}"]
    return "\n".join(lines), [_db_source(label, "trust_scores", len(rows))]


# ── Portfolio Summary (risk dashboard) ───────────────────────────────────────

def get_portfolio_summary() -> tuple[str, list[dict]]:
    """Institution-wide risk/fraud/AML summary for dashboard-style queries."""
    with engine.connect() as conn:
        total_customers = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 0
        by_risk = conn.execute(text(
            "SELECT LOWER(aml_risk_rating), COUNT(*) FROM customers GROUP BY LOWER(aml_risk_rating)"
        )).fetchall()
        total_fraud = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts")).scalar() or 0
        open_fraud  = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts WHERE status='open'")).scalar() or 0
        total_loans   = conn.execute(text("SELECT COUNT(*) FROM loans")).scalar() or 0
        active_loans  = conn.execute(text("SELECT COUNT(*) FROM loans WHERE status='active'")).scalar() or 0
        pending_loans = conn.execute(text("SELECT COUNT(*) FROM loans WHERE status='pending'")).scalar() or 0
        delinquent    = conn.execute(text(
            "SELECT COUNT(*) FROM loans WHERE status IN ('delinquent','defaulted','past_due')"
        )).scalar() or 0
        try:
            avg_trust = conn.execute(text("SELECT AVG(score) FROM trust_scores")).scalar() or 0
        except Exception:
            avg_trust = 0

    risk_map = {r[0]: r[1] for r in by_risk}
    low    = risk_map.get("low", 0)
    medium = risk_map.get("medium", 0)
    high   = risk_map.get("high", 0)
    critical = risk_map.get("very high", risk_map.get("very_high", 0))

    lines = [
        "=== TRUSNOVA RISK DASHBOARD — INSTITUTION-WIDE SUMMARY ===",
        f"As of {_now_iso()}",
        "",
        "── CUSTOMER RISK DISTRIBUTION ──",
        f"  Total Customers : {total_customers:,}",
        f"  Low Risk        : {low:,}  ({low/max(total_customers,1)*100:.1f}%)",
        f"  Medium Risk     : {medium:,}  ({medium/max(total_customers,1)*100:.1f}%)",
        f"  High Risk       : {high:,}  ({high/max(total_customers,1)*100:.1f}%)",
        f"  Critical Risk   : {critical:,}  ({critical/max(total_customers,1)*100:.1f}%)",
        "",
        "── FRAUD & AML ALERTS ──",
        f"  Total Alerts    : {total_fraud:,}",
        f"  Open (active)   : {open_fraud:,}",
        f"  Resolved        : {total_fraud - open_fraud:,}",
        "",
        "── LOAN PORTFOLIO ──",
        f"  Total Loans     : {total_loans:,}",
        f"  Active          : {active_loans:,}",
        f"  Pending         : {pending_loans:,}",
        f"  Delinquent/NPL  : {delinquent:,}  (NPL ratio: {delinquent/max(total_loans,1)*100:.2f}%)",
        "",
        f"── AI TRUST SCORE (avg across customers) : {float(avg_trust):.1f}/100 ──",
        "",
        f"Data source: customers, fraud_alerts, loans, trust_scores | As of {_now_iso()}",
    ]
    return "\n".join(lines), [_db_source("Institution Risk Dashboard", "multi-table", total_customers)]


# ── Main dispatch ─────────────────────────────────────────────────────────────

def retrieve_structured_data(
    intent: str,
    query: str,
    customer_id: Optional[str] = None,
    permissions: Optional[List[str]] = None,
) -> tuple[str, list[dict]]:
    """
    Dispatch to the right retriever based on intent.
    Returns (context_str, sources_list).
    `permissions` is forwarded to retrievers that support permission-aware traversal.
    """
    try:
        if intent == "risk":
            q_lower = query.lower()
            has_level = any(w in q_lower for w in ("high", "medium", "low", "critical"))
            ctx, srcs = get_risk_profiles(query, limit=30)
            if not has_level or "dashboard" in q_lower or "overview" in q_lower:
                summary_ctx, summary_srcs = get_portfolio_summary()
                ctx = summary_ctx + "\n\n" + ctx
                srcs = summary_srcs + srcs
            return ctx, srcs

        elif intent == "fraud":
            return get_fraud_data(query, customer_id)

        elif intent == "customer":
            ctx, srcs = get_customer_360(query, customer_id, permissions=permissions)
            # Only fall back to portfolio summary when NO name was mentioned at all
            # (e.g. "show me customers" with no specific name).
            # If a name was searched but not found, keep the targeted error message.
            if ctx.startswith("No customer specified"):
                return get_portfolio_summary()
            return ctx, srcs

        elif intent == "transaction":
            return get_transactions(query, customer_id)

        elif intent == "account":
            return get_accounts(query, customer_id)

        elif intent == "loan":
            return get_loans(query, customer_id)

        elif intent == "trust_score":
            return get_trust_scores(query, customer_id)

        elif intent == "stats":
            return get_portfolio_summary()

        else:
            return "", []

    except Exception as e:
        return f"[Data retrieval error for intent '{intent}': {e}]\n", []


# ── helpers ───────────────────────────────────────────────────────────────────

_NAME_STOP_WORDS = {
    # articles / pronouns
    "the", "a", "an", "his", "her", "their", "my", "your", "its",
    "me", "us", "him", "it", "we", "they", "i",
    # action verbs
    "show", "get", "pull", "find", "display", "give", "fetch", "tell",
    # banking nouns that aren't names
    "customer", "client",
    # profile-type keywords that can trail a name
    "profile", "history", "detail", "summary", "overview", "transaction",
}


def _trim_name(candidate: str) -> Optional[str]:
    """Strip leading/trailing stop words; return None if fewer than 2 words remain."""
    words = candidate.split()
    while words and words[0].lower() in _NAME_STOP_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _NAME_STOP_WORDS:
        words.pop()
    return " ".join(words) if len(words) >= 2 else None


def _extract_name_from_query(query: str) -> Optional[str]:
    """
    Extract a person's name from a query string.

    Handles:
      - Explicit name keyword: "with name raj" / "named John Doe"
      - Name-first:  "Raj J profile history"  → "Raj J"
      - Prefixed:    "show history for John Doe" → "John Doe"
      - Single-char surname: "raj J" (initial as last name)
    """
    import re

    _W = r"[A-Za-z][a-zA-Z]*"  # one name word (allows "J", "Raj", "Johnson")

    # Priority 0: explicit "name / named / called" keyword
    # Accepts single-word names (first-name-only searches like "with name raj")
    # Must be checked BEFORE the general patterns to avoid false positives.
    m = re.search(
        rf"(?:named?|called)\s+({_W}(?:\s+{_W}){{0,2}})",
        query,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip()
        words = candidate.split()
        while words and words[0].lower() in _NAME_STOP_WORDS:
            words.pop(0)
        while words and words[-1].lower() in _NAME_STOP_WORDS:
            words.pop()
        if words:  # single-word first names are valid for explicit name queries
            return " ".join(words)

    # Priority 1: 1–3 words immediately before a profile/history keyword
    # No ^ anchor so it finds the name anywhere: "show me Natalie Gordon profile" → "Natalie Gordon"
    # _trim_name strips leading/trailing stop words like "show", "me", "profile"
    m = re.search(
        rf"({_W}(?:\s+{_W}){{1,2}})\s+(?:profile|history|detail|360|summary|overview)",
        query,
        re.IGNORECASE,
    )
    if m:
        name = _trim_name(m.group(1))
        if name:
            return name

    # Priority 2: name after "for / about / of"
    # "show history for John Doe" → "John Doe"
    m = re.search(
        rf"(?:for|about|of)\s+({_W}(?:\s+{_W}){{0,2}})",
        query,
        re.IGNORECASE,
    )
    if m:
        name = _trim_name(m.group(1))
        if name:
            return name

    # Priority 3: name after "customer / client"
    # "customer Maria Garcia" → "Maria Garcia"
    m = re.search(
        rf"(?:customer|client)\s+({_W}(?:\s+{_W}){{0,2}})",
        query,
        re.IGNORECASE,
    )
    if m:
        name = _trim_name(m.group(1))
        if name:
            return name

    return None
