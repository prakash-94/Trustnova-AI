import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

_CUSTOMER_PK: str | None = None


def customer_pk() -> str:
    """Return the PK column name for the customers table ('customer_id' or 'id')."""
    global _CUSTOMER_PK
    if _CUSTOMER_PK is None:
        with engine.connect() as conn:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(customers)")).fetchall()}
            _CUSTOMER_PK = "customer_id" if "customer_id" in cols else "id"
    return _CUSTOMER_PK


def run_migrations() -> None:
    """Add any missing columns to existing tables so old DB volumes stay compatible."""
    # Columns to add: (table, column, SQLite type, default)
    migrations = [
        ("customers", "phone",         "TEXT",    "NULL"),
        ("customers", "address_city",  "TEXT",    "NULL"),
        ("customers", "address_state", "TEXT",    "NULL"),
        ("customers", "employment_status", "TEXT","NULL"),
    ]
    with engine.begin() as conn:
        for table, col, col_type, default in migrations:
            existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}"))
                print(f"  [migrate] Added column {table}.{col}")