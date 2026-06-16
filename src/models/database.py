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