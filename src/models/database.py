import os
from sqlalchemy import create_engine, text, inspect as sa_inspect

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")

# Render's managed PostgreSQL provides "postgres://" but SQLAlchemy 2.x requires "postgresql://".
# Write the fixed URL back to the environment so every other module that calls
# os.getenv("DATABASE_URL") also gets the corrected scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")

# auto_pk is imported by every route/model that issues CREATE TABLE statements
auto_pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if _is_sqlite else "SERIAL PRIMARY KEY"

_engine_kwargs: dict = (
    {"connect_args": {"check_same_thread": False}}
    if _is_sqlite
    else {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}
)
engine = create_engine(DATABASE_URL, **_engine_kwargs)

_CUSTOMER_PK: str | None = None


def customer_pk() -> str:
    """Return the PK column name for the customers table ('customer_id' or 'id')."""
    global _CUSTOMER_PK
    if _CUSTOMER_PK is None:
        insp = sa_inspect(engine)
        try:
            cols = {c["name"] for c in insp.get_columns("customers")}
            # New production/bootstrap schema uses `id`; the legacy local ETL
            # database uses `customer_id`. Prefer `id` when both are present so
            # hard-coded joins in older route modules stay compatible.
            _CUSTOMER_PK = "id" if "id" in cols else "customer_id"
        except Exception:
            _CUSTOMER_PK = "customer_id"
    return _CUSTOMER_PK


def _table_columns(conn, table: str) -> set[str]:
    """Return existing column names for a table — works on both SQLite and PostgreSQL."""
    if _is_sqlite:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}
    rows = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = :t AND table_schema = 'public'
    """), {"t": table}).fetchall()
    return {r[0] for r in rows}


def ensure_indexes() -> None:
    """Create performance indexes if they don't exist. Safe to run on every startup."""
    indexes = [
        # customers — list ordering + risk filter + search
        "CREATE INDEX IF NOT EXISTS idx_customers_name       ON customers(first_name, last_name)",
        "CREATE INDEX IF NOT EXISTS idx_customers_aml        ON customers(aml_risk_rating)",
        # fraud_alerts — most queried join column
        "CREATE INDEX IF NOT EXISTS idx_fraud_customer       ON fraud_alerts(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_fraud_status         ON fraud_alerts(status)",
        "CREATE INDEX IF NOT EXISTS idx_fraud_ts             ON fraud_alerts(timestamp)",
        # loans
        "CREATE INDEX IF NOT EXISTS idx_loans_customer       ON loans(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_loans_status         ON loans(status)",
        "CREATE INDEX IF NOT EXISTS idx_loans_created        ON loans(created_at)",
        # enriched_transactions
        "CREATE INDEX IF NOT EXISTS idx_etxn_customer        ON enriched_transactions(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_etxn_ts              ON enriched_transactions(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_etxn_fraud           ON enriched_transactions(is_fraud)",
        # trust_scores
        "CREATE INDEX IF NOT EXISTS idx_trust_customer_ts    ON trust_scores(customer_id, timestamp)",
        # accounts
        "CREATE INDEX IF NOT EXISTS idx_accounts_customer    ON accounts(customer_id)",
    ]
    with engine.begin() as conn:
        for sql in indexes:
            try:
                conn.execute(text(sql))
            except Exception as e:
                print(f"  [index] Skipped: {e}")
    print("  [index] Performance indexes verified.")


def run_migrations() -> None:
    """Add any missing columns to existing tables so old DB volumes stay compatible."""
    migrations = [
        ("customers", "phone",             "TEXT", "NULL"),
        ("customers", "address_city",      "TEXT", "NULL"),
        ("customers", "address_state",     "TEXT", "NULL"),
        ("customers", "employment_status", "TEXT", "NULL"),
    ]
    with engine.begin() as conn:
        for table, col, col_type, default in migrations:
            try:
                existing = _table_columns(conn, table)
                if col not in existing:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}"
                    ))
                    print(f"  [migrate] Added column {table}.{col}")
            except Exception as e:
                print(f"  [migrate] Skipped {table}.{col}: {e}")
