"""
Unit tests for customer context retrieval.
Updated for Phase 3 — tests real data from SQLite and RAG modules.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
from src.rag.customer_context import (
    get_customer_profile,
    get_last_n_transactions,
    get_sentiment_trend,
    get_trust_score,
    get_support_tickets,
    get_fraud_history,
    get_full_customer_context,
    get_db_engine,
)


@pytest.fixture
def sample_customer_id():
    """Get a real customer_id from the database."""
    engine = get_db_engine()
    df = pd.read_sql("SELECT customer_id FROM customers LIMIT 1", engine)
    assert not df.empty, "No customers found in database. Run Phase 2 data generation first."
    return df.iloc[0]["customer_id"]


@pytest.fixture
def invalid_customer_id():
    return "NONEXISTENT_ID"


class TestCustomerProfile:
    def test_valid_customer(self, sample_customer_id):
        profile = get_customer_profile(sample_customer_id)
        assert profile is not None
        assert profile["customer_id"] == sample_customer_id
        assert "name" in profile
        assert "balance" in profile
        assert "credit_score" in profile
        assert isinstance(profile["balance"], float)
        assert 300 <= profile["credit_score"] <= 850

    def test_phase2_fields(self, sample_customer_id):
        """Verify Phase 2 fields are present."""
        profile = get_customer_profile(sample_customer_id)
        assert "age" in profile
        assert "income" in profile
        assert "risk_level" in profile
        assert "account_type" in profile
        assert profile["age"] > 0
        assert profile["income"] > 0

    def test_invalid_customer(self, invalid_customer_id):
        profile = get_customer_profile(invalid_customer_id)
        assert profile is None


class TestTransactions:
    def test_last_n_transactions(self, sample_customer_id):
        txns = get_last_n_transactions(sample_customer_id, n=5)
        assert isinstance(txns, list)
        assert len(txns) <= 5
        if txns:
            assert "amount" in txns[0]
            assert "category" in txns[0]
            assert txns[0]["amount"] > 0

    def test_default_n(self, sample_customer_id):
        txns = get_last_n_transactions(sample_customer_id)
        assert len(txns) <= 5

    def test_invalid_customer(self, invalid_customer_id):
        txns = get_last_n_transactions(invalid_customer_id)
        assert txns == []


class TestSentimentTrend:
    def test_valid_customer(self, sample_customer_id):
        sentiment = get_sentiment_trend(sample_customer_id)
        assert "total_interactions" in sentiment
        assert "avg_sentiment" in sentiment
        assert "sentiment_distribution" in sentiment
        assert "recent_notes" in sentiment

    def test_invalid_customer(self, invalid_customer_id):
        sentiment = get_sentiment_trend(invalid_customer_id)
        assert sentiment["total_interactions"] == 0


class TestTrustScore:
    def test_valid_customer(self, sample_customer_id):
        score = get_trust_score(sample_customer_id)
        assert "score" in score
        assert "tier" in score
        assert 0 <= score["score"] <= 100
        assert score["tier"] in ["High Risk", "Moderate", "Trusted"]

    def test_components(self, sample_customer_id):
        score = get_trust_score(sample_customer_id)
        assert "components" in score
        components = score["components"]
        assert "credit_score" in components
        assert "account_age" in components
        assert "sentiment" in components
        assert "balance" in components
        assert "fraud_history" in components

    def test_invalid_customer(self, invalid_customer_id):
        score = get_trust_score(invalid_customer_id)
        assert score["tier"] == "Unknown"


class TestSupportTickets:
    def test_valid_customer(self, sample_customer_id):
        tickets = get_support_tickets(sample_customer_id)
        assert "total_tickets" in tickets
        assert "issues" in tickets

    def test_invalid_customer(self, invalid_customer_id):
        tickets = get_support_tickets(invalid_customer_id)
        assert tickets["total_tickets"] == 0


class TestFraudHistory:
    def test_valid_customer(self, sample_customer_id):
        fraud = get_fraud_history(sample_customer_id)
        assert "total_alerts" in fraud
        assert "status_distribution" in fraud

    def test_invalid_customer(self, invalid_customer_id):
        fraud = get_fraud_history(invalid_customer_id)
        assert fraud["total_alerts"] == 0


class TestFullContext:
    def test_valid_customer(self, sample_customer_id):
        context = get_full_customer_context(sample_customer_id)
        assert "profile" in context
        assert "last_5_transactions" in context
        assert "trust_score" in context
        assert "sentiment_trend" in context
        assert "support_tickets" in context
        assert "fraud_history" in context
        assert "rag_interaction_notes" in context

    def test_invalid_customer(self, invalid_customer_id):
        context = get_full_customer_context(invalid_customer_id)
        assert "error" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
