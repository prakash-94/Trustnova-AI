"""
Migrate core banking tables from local banking.db (SQLite) → Render PostgreSQL.

Run once:
    python scripts/migrate_to_postgres.py

The script is idempotent — re-running skips tables that already have rows.
"""

import os, sys, sqlite3, psycopg2, psycopg2.extras
from pathlib import Path

# ── Connection setup ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "banking.db"

PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://trusnova_ai_db_user:d67OeJyggmJnozW49ScKBykUMyVPqUsC"
    "@dpg-d8ovslkvikkc7393sipg-a.oregon-postgres.render.com/trusnova_ai_db",
)

BATCH = 500   # rows per INSERT batch


# ── Helpers ───────────────────────────────────────────────────────────────────

def pg_tables(pg):
    cur = pg.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    return {r[0] for r in cur.fetchall()}


def pg_row_count(pg, table):
    cur = pg.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def sqlite_rows(sl, query):
    cur = sl.cursor()
    cur.execute(query)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def bulk_insert(pg, table, cols, rows, batch=BATCH):
    if not rows:
        return 0
    placeholders = ",".join(["%s"] * len(cols))
    col_list = ",".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    total = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        cur = pg.cursor()
        psycopg2.extras.execute_batch(cur, sql, chunk)
        pg.commit()
        total += len(chunk)
        print(f"    {table}: inserted {total}/{len(rows)} rows", end="\r")
    print()
    return total


# ── Per-table DDL + migration ─────────────────────────────────────────────────

def migrate_customers(pg, sl):
    """customers — rename customer_id → id to match accounts.py JOIN ON c.id"""
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id              TEXT,
            name            TEXT,
            email           TEXT,
            age             BIGINT,
            annual_income   FLOAT,
            credit_score    BIGINT,
            aml_risk_rating TEXT,
            account_type    TEXT,
            balance         FLOAT,
            account_opened  TEXT,
            account_age_days BIGINT,
            sentiment_avg   FLOAT,
            created_at      TEXT,
            first_name      TEXT,
            last_name       TEXT,
            kyc_status      TEXT,
            kyc_notes       TEXT,
            date_of_birth   TEXT,
            segment         TEXT,
            customer_type   TEXT,
            is_pep          BIGINT,
            is_sanctioned   BIGINT,
            is_active       BIGINT,
            phone           TEXT,
            address_city    TEXT,
            address_state   TEXT,
            employment_status TEXT
        )
    """)
    pg.commit()

    # Add columns that may be missing from already-migrated production tables
    for col, col_type in [("kyc_notes", "TEXT"), ("date_of_birth", "TEXT")]:
        try:
            pg.cursor().execute(f"ALTER TABLE customers ADD COLUMN {col} {col_type}")
            pg.commit()
            print(f"  customers: added column {col}")
        except Exception:
            pg.rollback()  # column already exists — safe to ignore

    if pg_row_count(pg, "customers") > 0:
        print("  customers: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT * FROM customers")
    # rename customer_id → id for the PostgreSQL column
    pg_cols = ["id" if c == "customer_id" else c for c in cols]
    # add missing columns with NULL values
    extra_cols = ["phone", "address_city", "address_state", "employment_status"]
    for ec in extra_cols:
        if ec not in pg_cols:
            pg_cols.append(ec)
            rows = [r + (None,) for r in rows]

    bulk_insert(pg, "customers", pg_cols, rows)


def migrate_accounts(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id              TEXT,
            customer_id     TEXT,
            account_number  TEXT,
            account_type    TEXT,
            status          TEXT,
            balance_cents   BIGINT,
            currency        TEXT,
            opened_date     TEXT,
            interest_rate   FLOAT
        )
    """)
    pg.commit()

    if pg_row_count(pg, "accounts") > 0:
        print("  accounts: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT * FROM accounts")
    # pad missing interest_rate column
    if "interest_rate" not in cols:
        cols = list(cols) + ["interest_rate"]
        rows = [r + (0.0,) for r in rows]
    bulk_insert(pg, "accounts", cols, rows)


def migrate_enriched_transactions(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS enriched_transactions (
            transaction_id  TEXT,
            customer_id     TEXT,
            amount          FLOAT,
            merchant        TEXT,
            merchant_risk   BIGINT,
            category        TEXT,
            location        TEXT,
            hour            BIGINT,
            is_weekend      BIGINT,
            device_change   BIGINT,
            location_change BIGINT,
            frequency       BIGINT,
            is_fraud        BIGINT,
            timestamp       TEXT,
            geo_mismatch    BIGINT,
            device_new      BIGINT,
            name            TEXT,
            email           TEXT,
            age             BIGINT,
            income          FLOAT,
            credit_score    BIGINT,
            risk_level      TEXT,
            account_type    TEXT,
            balance         FLOAT,
            account_opened  TEXT,
            account_age_days BIGINT,
            sentiment_avg   FLOAT,
            created_at      TEXT,
            avg_interaction_sentiment FLOAT,
            interaction_count BIGINT,
            ticket_count    BIGINT,
            avg_ticket_sentiment FLOAT,
            complaint_count BIGINT,
            avg_complaint_sentiment FLOAT,
            fraud_flag_count BIGINT,
            amount_zscore   FLOAT,
            velocity_30m    INTEGER
        )
    """)
    pg.commit()

    if pg_row_count(pg, "enriched_transactions") > 0:
        print("  enriched_transactions: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT * FROM enriched_transactions")
    bulk_insert(pg, "enriched_transactions", cols, rows)


def migrate_fraud_alerts(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS fraud_alerts (
            alert_id        TEXT,
            customer_id     TEXT,
            transaction_id  TEXT,
            risk_score      FLOAT,
            reason          TEXT,
            status          TEXT,
            timestamp       TEXT
        )
    """)
    pg.commit()

    if pg_row_count(pg, "fraud_alerts") > 0:
        print("  fraud_alerts: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT * FROM fraud_alerts")
    bulk_insert(pg, "fraud_alerts", cols, rows)


def migrate_loans(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id                        TEXT,
            customer_id               TEXT,
            loan_type                 TEXT,
            status                    TEXT,
            purpose                   TEXT,
            notes                     TEXT,
            amount_cents              BIGINT,
            outstanding_balance_cents BIGINT,
            interest_rate             FLOAT,
            term_months               BIGINT,
            monthly_payment_cents     BIGINT,
            collateral                TEXT,
            origination_date          TEXT,
            maturity_date             TEXT,
            created_at                TEXT
        )
    """)
    pg.commit()

    if pg_row_count(pg, "loans") > 0:
        print("  loans: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT * FROM loans")
    bulk_insert(pg, "loans", cols, rows)


def migrate_kyc_records(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS kyc_records (
            id                  SERIAL PRIMARY KEY,
            customer_id         TEXT UNIQUE,
            document_type       TEXT,
            document_number     TEXT,
            status              TEXT DEFAULT 'pending',
            verified_by         TEXT,
            verification_date   TEXT,
            expiry_date         TEXT,
            notes               TEXT,
            risk_rating         TEXT DEFAULT 'low',
            created_at          TEXT,
            updated_at          TEXT
        )
    """)
    pg.commit()

    if pg_row_count(pg, "kyc_records") > 0:
        print("  kyc_records: already populated, skipping.")
        return

    # skip the autoincrement `id` column — let Postgres SERIAL handle it
    cols, rows = sqlite_rows(sl, "SELECT customer_id, document_type, document_number, status, verified_by, verification_date, expiry_date, notes, risk_rating, created_at, updated_at FROM kyc_records")
    bulk_insert(pg, "kyc_records", cols, rows)


def migrate_aml_cases(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS aml_cases (
            id              SERIAL PRIMARY KEY,
            customer_id     TEXT,
            alert_type      TEXT,
            risk_level      TEXT DEFAULT 'medium',
            status          TEXT DEFAULT 'open',
            description     TEXT,
            transaction_ids TEXT,
            sar_filed       INTEGER DEFAULT 0,
            assigned_to     TEXT,
            resolution      TEXT,
            created_at      TEXT,
            updated_at      TEXT
        )
    """)
    pg.commit()

    if pg_row_count(pg, "aml_cases") > 0:
        print("  aml_cases: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT customer_id, alert_type, risk_level, status, description, transaction_ids, sar_filed, assigned_to, resolution, created_at, updated_at FROM aml_cases")
    bulk_insert(pg, "aml_cases", cols, rows)


def migrate_risk_assessments(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS risk_assessments (
            id               SERIAL PRIMARY KEY,
            customer_id      TEXT UNIQUE,
            risk_score       FLOAT DEFAULT 0.0,
            risk_band        TEXT DEFAULT 'low',
            credit_risk      FLOAT DEFAULT 0.0,
            fraud_risk       FLOAT DEFAULT 0.0,
            aml_risk         FLOAT DEFAULT 0.0,
            operational_risk FLOAT DEFAULT 0.0,
            assessed_by      TEXT,
            notes            TEXT,
            created_at       TEXT,
            updated_at       TEXT
        )
    """)
    pg.commit()
    print("  risk_assessments: table ready (0 rows to migrate).")


def migrate_trust_scores(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS trust_scores (
            id                       SERIAL PRIMARY KEY,
            customer_id              TEXT NOT NULL,
            score                    FLOAT NOT NULL,
            tier                     TEXT NOT NULL,
            account_age_component    FLOAT,
            credit_score_component   FLOAT,
            fraud_history_component  FLOAT,
            sentiment_component      FLOAT,
            interaction_component    FLOAT,
            timestamp                TEXT NOT NULL
        )
    """)
    pg.commit()

    if pg_row_count(pg, "trust_scores") > 0:
        print("  trust_scores: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT customer_id, score, tier, account_age_component, credit_score_component, fraud_history_component, sentiment_component, interaction_component, timestamp FROM trust_scores")
    bulk_insert(pg, "trust_scores", cols, rows)


def migrate_access_requests(pg):
    """access_requests — auto-created at runtime but ensure it exists on fresh deploy."""
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS access_requests (
            id          SERIAL PRIMARY KEY,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL,
            section     TEXT NOT NULL,
            reason      TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            reviewed_by TEXT,
            reviewed_at TEXT,
            expires_at  TEXT,
            created_at  TEXT NOT NULL
        )
    """)
    pg.commit()
    print("  access_requests: table ready.")


def migrate_llm_usage(pg, sl):
    pg.cursor().execute("""
        CREATE TABLE IF NOT EXISTS llm_usage (
            id          SERIAL PRIMARY KEY,
            task_type   TEXT NOT NULL,
            model       TEXT NOT NULL,
            provider    TEXT,
            tokens_in   INTEGER,
            tokens_out  INTEGER,
            cost_usd    FLOAT,
            latency_ms  FLOAT,
            success     INTEGER DEFAULT 1,
            error       TEXT,
            timestamp   TEXT NOT NULL
        )
    """)
    pg.commit()

    if pg_row_count(pg, "llm_usage") > 0:
        print("  llm_usage: already populated, skipping.")
        return

    cols, rows = sqlite_rows(sl, "SELECT task_type, model, provider, tokens_in, tokens_out, cost_usd, latency_ms, success, error, timestamp FROM llm_usage")
    bulk_insert(pg, "llm_usage", cols, rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"SQLite source: {SQLITE_PATH}")
    if not SQLITE_PATH.exists():
        sys.exit(f"ERROR: {SQLITE_PATH} not found. Run from the project root.")

    print("Connecting to Render PostgreSQL …")
    pg = psycopg2.connect(PG_URL)
    sl = sqlite3.connect(str(SQLITE_PATH))

    steps = [
        ("customers",              migrate_customers),
        ("accounts",               migrate_accounts),
        ("enriched_transactions",  migrate_enriched_transactions),
        ("fraud_alerts",           migrate_fraud_alerts),
        ("loans",                  migrate_loans),
        ("kyc_records",            migrate_kyc_records),
        ("aml_cases",              migrate_aml_cases),
        ("risk_assessments",       migrate_risk_assessments),
        ("trust_scores",           migrate_trust_scores),
        ("llm_usage",              migrate_llm_usage),
        ("access_requests",        lambda pg, _sl: migrate_access_requests(pg)),
    ]

    for name, fn in steps:
        print(f"\n>> {name}")
        try:
            fn(pg, sl)
        except Exception as e:
            pg.rollback()
            print(f"  ERROR: {e}")

    # Final counts
    print("\n=== Final row counts in PostgreSQL ===")
    for name, _ in steps:
        try:
            print(f"  {name}: {pg_row_count(pg, name)} rows")
        except Exception:
            print(f"  {name}: (error reading count)")

    sl.close()
    pg.close()
    print("\nDone.")


if __name__ == "__main__":
    main()