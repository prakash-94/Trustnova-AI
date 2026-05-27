"""
Unit tests for TrustScoreCalculator.

Tests edge cases for score calculation including:
- Normal customers
- New accounts (low age)
- High fraud history
- Extreme sentiments
- Missing interactions
- Tier boundary conditions
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
from src.models.trust_scorer import TrustScoreCalculator, WEIGHTS, TIERS


@pytest.fixture
def calculator():
    return TrustScoreCalculator()


@pytest.fixture
def sample_customer_id(calculator):
    df = pd.read_sql("SELECT customer_id FROM customers LIMIT 1", calculator.engine)
    assert not df.empty
    return df.iloc[0]["customer_id"]


class TestNormalization:
    """Test individual normalization functions."""

    def test_account_age_new(self, calculator):
        """Brand new account (1 day) should score very low."""
        score = calculator._normalize_account_age(1)
        assert 0 <= score <= 1  # ~0.03%

    def test_account_age_old(self, calculator):
        """10+ year account should score 100."""
        score = calculator._normalize_account_age(5000)
        assert score == 100

    def test_account_age_mid(self, calculator):
        """5-year account should be ~50."""
        score = calculator._normalize_account_age(1825)
        assert 45 <= score <= 55

    def test_credit_score_minimum(self, calculator):
        """Credit score 300 = 0."""
        score = calculator._normalize_credit_score(300)
        assert score == 0

    def test_credit_score_maximum(self, calculator):
        """Credit score 850 = 100."""
        score = calculator._normalize_credit_score(850)
        assert score == 100

    def test_credit_score_below_range(self, calculator):
        """Credit score below 300 should clamp to 0."""
        score = calculator._normalize_credit_score(200)
        assert score == 0

    def test_fraud_history_clean(self, calculator):
        """No fraud = 100."""
        score = calculator._normalize_fraud_history(0)
        assert score == 100

    def test_fraud_history_one(self, calculator):
        """1 fraud incident = 75."""
        score = calculator._normalize_fraud_history(1)
        assert score == 75

    def test_fraud_history_many(self, calculator):
        """4+ fraud incidents = 0."""
        score = calculator._normalize_fraud_history(4)
        assert score == 0

    def test_fraud_history_excessive(self, calculator):
        """10 fraud incidents should clamp to 0, not go negative."""
        score = calculator._normalize_fraud_history(10)
        assert score == 0

    def test_sentiment_positive(self, calculator):
        """Positive sentiment (1.0) = 100."""
        score = calculator._normalize_sentiment(1.0)
        assert score == 100

    def test_sentiment_negative(self, calculator):
        """Negative sentiment (-1.0) = 0."""
        score = calculator._normalize_sentiment(-1.0)
        assert score == 0

    def test_sentiment_neutral(self, calculator):
        """Neutral sentiment (0.0) = 50."""
        score = calculator._normalize_sentiment(0.0)
        assert score == 50

    def test_interaction_count_zero(self, calculator):
        """No interactions = 0."""
        score = calculator._normalize_interaction_count(0)
        assert score == 0

    def test_interaction_count_max(self, calculator):
        """20+ interactions = 100."""
        score = calculator._normalize_interaction_count(25)
        assert score == 100


class TestWeights:
    """Test that weights are correct and sum to 1.0."""

    def test_weights_sum(self):
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_weights_positive(self):
        for w in WEIGHTS.values():
            assert w > 0


class TestTierMapping:
    """Test tier boundary conditions."""

    def test_tier_high_risk_low(self, calculator):
        assert calculator._get_tier(0) == "High Risk"

    def test_tier_high_risk_boundary(self, calculator):
        assert calculator._get_tier(40) == "High Risk"

    def test_tier_moderate_low(self, calculator):
        assert calculator._get_tier(41) == "Moderate"

    def test_tier_moderate_high(self, calculator):
        assert calculator._get_tier(70) == "Moderate"

    def test_tier_trusted_low(self, calculator):
        assert calculator._get_tier(71) == "Trusted"

    def test_tier_trusted_high(self, calculator):
        assert calculator._get_tier(100) == "Trusted"


class TestCalculate:
    """Test the full calculate() method."""

    def test_valid_customer(self, calculator, sample_customer_id):
        result = calculator.calculate(sample_customer_id)
        assert "score" in result
        assert "tier" in result
        assert "components" in result
        assert 0 <= result["score"] <= 100
        assert result["tier"] in ["High Risk", "Moderate", "Trusted"]

    def test_invalid_customer(self, calculator):
        result = calculator.calculate("NONEXISTENT")
        assert "error" in result
        assert result["score"] == 0

    def test_score_stored_in_history(self, calculator, sample_customer_id):
        calculator.calculate(sample_customer_id)
        history = calculator.get_score_history(sample_customer_id, limit=1)
        assert len(history) >= 1

    def test_components_present(self, calculator, sample_customer_id):
        result = calculator.calculate(sample_customer_id)
        for key in WEIGHTS:
            assert key in result["components"]
            assert 0 <= result["components"][key] <= 100


class TestUpdateOnEvent:
    """Test event-driven recalculation."""

    def test_event_recalculates(self, calculator, sample_customer_id):
        result = calculator.update_on_event({
            "customer_id": sample_customer_id,
            "event_type": "general"
        })
        assert "score" in result
        assert result.get("triggered_by") == "general"

    def test_event_missing_customer(self, calculator):
        result = calculator.update_on_event({"event_type": "general"})
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
