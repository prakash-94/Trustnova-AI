"""
Hybrid Enterprise RAG — structured data retriever.
Fetches live records from SQLite for each intent type and formats them
as LLM-ready context blocks with metadata-rich source citations.
"""
from __future__ import annotations
import datetime
from typing import Optional
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

def get_customer_360(query: str, customer_id: Optional[str] = None) -> tuple[str, list[dict]]:
    """Full customer profile including accounts, recent transactions, loans, fraud, trust score."""
    pk = customer_pk()
    with engine.connect() as conn:
        # Find customer by name if no ID
        if not customer_id:
            name_match = _extract_name_from_query(query)
            if name_match:
                row = conn.execute(text(f"""
                    SELECT * FROM customers
                    WHERE LOWER(first_name || ' ' || last_name) LIKE :nm
                    LIMIT 1
                """), {"nm": f"%{name_match.lower()}%"}).fetchone()
                if row:
                    customer_id = str(dict(row._mapping).get(pk, ""))

        if not customer_id:
            return "No customer specified. Please provide a customer name or ID.\n", []

        cust = conn.execute(text(
            f"SELECT * FROM customers WHERE {pk} = :cid"
        ), {"cid": customer_id}).fetchone()
        if not cust:
            return f"No customer found with ID: {customer_id}\n", []

        c = dict(cust._mapping)

        # Accounts
        acct_rows = conn.execute(text(
            "SELECT * FROM accounts WHERE customer_id = :cid ORDER BY opened_date DESC LIMIT 5"
        ), {"cid": customer_id}).fetchall()

        # Recent transactions
        txn_rows = conn.execute(text("""
            SELECT amount, merchant, category, timestamp, is_fraud
            FROM   enriched_transactions
            WHERE  customer_id = :cid
            ORDER  BY timestamp DESC LIMIT 8
        """), {"cid": customer_id}).fetchall()

        # Loans
        loan_rows = conn.execute(text(
            "SELECT loan_type, status, amount_cents, outstanding_balance_cents, origination_date FROM loans WHERE customer_id = :cid LIMIT 5"
        ), {"cid": customer_id}).fetchall()

        # Fraud alerts
        fraud_rows = conn.execute(text(
            "SELECT risk_score, reason, status, timestamp FROM fraud_alerts WHERE customer_id = :cid ORDER BY timestamp DESC LIMIT 5"
        ), {"cid": customer_id}).fetchall()

        # Trust score
        ts_row = conn.execute(text("""
            SELECT score, tier, timestamp FROM trust_scores
            WHERE customer_id = :cid ORDER BY timestamp DESC LIMIT 1
        """), {"cid": customer_id}).fetchone()

    name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
    cid_short = str(customer_id)[:10]

    blocks = [
        f"=== CUSTOMER 360° VIEW: {name.upper()} ===",
        f"Customer ID: {cid_short} | As of {_now_iso()}",
        "",
        "── PROFILE ──",
        f"  Email         : {c.get('email', 'N/A')}",
        f"  Phone         : {c.get('phone', 'N/A')}",
        f"  Location      : {c.get('address_city', '')}, {c.get('address_state', '')}",
        f"  Segment       : {c.get('segment', 'N/A')}",
        f"  Customer Type : {c.get('customer_type', 'N/A')}",
        f"  KYC Status    : {c.get('kyc_status', 'N/A')}",
        f"  AML Risk      : {c.get('aml_risk_rating', 'N/A')}",
        f"  Credit Score  : {c.get('credit_score', 'N/A')}",
        f"  Annual Income : ${float(c.get('annual_income') or 0):,.0f}",
        f"  PEP           : {'YES — EDD Required' if c.get('is_pep') else 'No'}",
        f"  Sanctioned    : {'YES — BLOCKED' if c.get('is_sanctioned') else 'No'}",
        f"  Member Since  : {str(c.get('created_at', ''))[:10]}",
    ]

    # Accounts
    if acct_rows:
        blocks.append("\n── ACCOUNTS ──")
        for a in acct_rows:
            ad = dict(a._mapping)
            bal = float(ad.get("balance_cents") or 0) / 100
            blocks.append(
                f"  {ad.get('account_type', 'account').title()} #{ad.get('account_number', '')}"
                f" | Status: {ad.get('status', '')} | Balance: ${bal:,.2f}"
            )

    # Loans
    if loan_rows:
        blocks.append("\n── LOANS ──")
        for l in loan_rows:
            ld = dict(l._mapping)
            amt = float(ld.get("amount_cents") or 0) / 100
            outstanding = float(ld.get("outstanding_balance_cents") or 0) / 100
            blocks.append(
                f"  {ld.get('loan_type', '').title()} Loan | Status: {ld.get('status', '')}"
                f" | Original: ${amt:,.0f} | Outstanding: ${outstanding:,.0f}"
            )

    # Recent transactions
    if txn_rows:
        blocks.append("\n── RECENT TRANSACTIONS (last 8) ──")
        for t in txn_rows:
            td = dict(t._mapping)
            amt = float(td.get("amount") or 0)
            flag = " ⚠️ FLAGGED" if td.get("is_fraud") else ""
            blocks.append(
                f"  {str(td.get('timestamp', ''))[:10]} | {td.get('merchant', 'Unknown'):<25}"
                f" | ${abs(amt):>8,.2f} | {td.get('category', '')}{flag}"
            )

    # Fraud alerts
    if fraud_rows:
        blocks.append("\n── FRAUD ALERTS ──")
        for f in fraud_rows:
            fd = dict(f._mapping)
            score = float(fd.get("risk_score") or 0)
            blocks.append(
                f"  Score: {score*100:.0f}% | Status: {fd.get('status', '')} "
                f"| {str(fd.get('reason', ''))[:60]} | {str(fd.get('timestamp', ''))[:10]}"
            )

    # Trust score
    if ts_row:
        tsd = dict(ts_row._mapping)
        blocks.append(
            f"\n── TRUST SCORE: {float(tsd.get('score', 0)):.0f}/100 ({tsd.get('tier', '')} tier) "
            f"| Last updated: {str(tsd.get('timestamp', ''))[:10]} ──"
        )

    blocks.append(f"\nData source: customers, accounts, loans, enriched_transactions, fraud_alerts, trust_scores | As of {_now_iso()}")
    return "\n".join(blocks), [_db_source(f"Customer 360°: {name}", "multi-table", 1)]


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
        if "active" in q_lower:
            filters.append("l.status = 'active'")
        elif "delinquent" in q_lower or "overdue" in q_lower:
            filters.append("l.status IN ('delinquent','defaulted','past_due')")
        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        pk = customer_pk()
        rows = conn.execute(text(f"""
            SELECT l.id, l.customer_id, l.loan_type, l.status,
                   l.amount_cents, l.outstanding_balance_cents,
                   l.interest_rate, l.term_months, l.origination_date,
                   c.first_name, c.last_name
            FROM   loans l
            LEFT   JOIN customers c ON l.customer_id = c.{pk}
            {where}
            ORDER  BY l.origination_date DESC
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
        total_loans = conn.execute(text("SELECT COUNT(*) FROM loans")).scalar() or 0
        active_loans = conn.execute(text("SELECT COUNT(*) FROM loans WHERE status='active'")).scalar() or 0
        delinquent  = conn.execute(text(
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
) -> tuple[str, list[dict]]:
    """
    Dispatch to the right retriever based on intent.
    Returns (context_str, sources_list).
    """
    try:
        if intent == "risk":
            q_lower = query.lower()
            # If general risk dashboard query (no specific level), include portfolio summary
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
            ctx, srcs = get_customer_360(query, customer_id)
            # If no specific customer was resolved, fall back to portfolio summary
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

def _extract_name_from_query(query: str) -> Optional[str]:
    """Extract a person name from a query like 'show customer history for John Doe'."""
    import re
    patterns = [
        r"for\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"about\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"customer\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    ]
    for pat in patterns:
        m = re.search(pat, query)
        if m:
            return m.group(1)
    return None