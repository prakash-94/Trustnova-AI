"""
Shared pytest fixtures and configuration for Banking AI Copilot tests.

Sets environment variables before any test imports happen, ensuring
all modules pick up the right config (SQLite, sentence_transformers, chromadb).
"""
import os
import pytest

# Set test environment BEFORE any src imports
os.environ.setdefault("DATABASE_URL", "sqlite:///./banking.db")
os.environ.setdefault("EMBEDDING_BACKEND", "sentence_transformers")
os.environ.setdefault("VECTOR_DB", "chroma")
os.environ.setdefault("CHROMA_PERSIST_DIR", "data/chroma_db")
os.environ.setdefault("CHROMA_COLLECTION", "banking_docs")


@pytest.fixture(scope="session")
def db_engine():
    """Session-scoped SQLAlchemy engine pointing at the test database."""
    from sqlalchemy import create_engine
    return create_engine(os.environ["DATABASE_URL"])


@pytest.fixture(scope="session")
def sample_customer_id(db_engine):
    """Return one real customer_id from the database."""
    import pandas as pd
    df = pd.read_sql("SELECT customer_id FROM customers LIMIT 1", db_engine)
    if df.empty:
        pytest.skip("No customers in database — run data generators first")
    return df.iloc[0]["customer_id"]


@pytest.fixture(scope="session")
def sample_transaction(db_engine):
    """Return a sample high-risk transaction dict for fraud tests."""
    return {
        "amount": 9500.00,
        "hour": 3,
        "geo_mismatch": 1,
        "device_new": 1,
        "is_weekend": 0,
        "amount_zscore": 4.2,
        "velocity_30m": 5,
        "credit_score": 420,
        "account_age_days": 15,
        "merchant_risk": 0.9,
    }
