"""
Unit tests for the Customer Intelligence Engine (Phase 7).

Tests:
  - Sentiment Analysis: batch processing, monthly trends, alert detection
  - Risk Profiling: profile structure, risk assessment, retention prediction
  - Product Recommendations: rule triggers, top 3 selection, deduplication
  - Integration: customer context includes risk profile + recommendations
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
from src.intelligence.sentiment import SentimentAnalyzer
from src.intelligence.risk_profile import RiskProfiler
from src.intelligence.recommender import ProductRecommender


# ==================================================================
# Fixtures
# ==================================================================

@pytest.fixture
def analyzer():
    return SentimentAnalyzer()


@pytest.fixture
def profiler():
    return RiskProfiler()


@pytest.fixture
def recommender():
    return ProductRecommender()


@pytest.fixture
def sample_customer_id():
    """Get a real customer ID from the database."""
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///./banking.db")
    df = pd.read_sql("SELECT customer_id FROM customers LIMIT 1", engine)
    assert not df.empty
    return df.iloc[0]["customer_id"]


@pytest.fixture
def five_customer_ids():
    """Get 5 customer IDs for broader testing."""
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///./banking.db")
    df = pd.read_sql("SELECT customer_id FROM customers LIMIT 5", engine)
    return df["customer_id"].tolist()


# ==================================================================
# Sentiment Analysis Tests
# ==================================================================

class TestSentimentAnalyzer:
    """Test the SentimentAnalyzer pipeline."""

    def test_score_to_label_positive(self, analyzer):
        """Positive score → 'Positive' label."""
        assert analyzer._score_to_label(0.5) == "Positive"

    def test_score_to_label_negative(self, analyzer):
        """Negative score → 'Negative' label."""
        assert analyzer._score_to_label(-0.5) == "Negative"

    def test_score_to_label_neutral(self, analyzer):
        """Neutral score → 'Neutral' label."""
        assert analyzer._score_to_label(0.0) == "Neutral"

    def test_score_to_label_boundary_positive(self, analyzer):
        """Score at +0.2 is still Neutral."""
        assert analyzer._score_to_label(0.2) == "Neutral"

    def test_score_to_label_boundary_negative(self, analyzer):
        """Score at -0.2 is still Neutral."""
        assert analyzer._score_to_label(-0.2) == "Neutral"

    def test_batch_process_interactions(self, analyzer):
        """Should process interactions into sentiment_scores table."""
        count = analyzer.batch_process_interactions()
        assert count > 0  # We have 4,500 interactions

    def test_batch_process_support_tickets(self, analyzer):
        """Should process support tickets."""
        count = analyzer.batch_process_support_tickets()
        assert count > 0  # We have 3,000 tickets

    def test_batch_process_complaints(self, analyzer):
        """Should process complaints."""
        count = analyzer.batch_process_complaints()
        assert count > 0  # We have 1,200 complaints

    def test_batch_process_chat_transcripts(self, analyzer):
        """Should process chat transcripts."""
        count = analyzer.batch_process_chat_transcripts()
        assert count > 0  # We have 600 transcripts

    def test_batch_analyze_all(self, analyzer):
        """Should process all sources and return totals."""
        results = analyzer.batch_analyze_all()
        assert "total" in results
        assert results["total"] > 0
        assert results["interactions"] > 0
        assert results["support_tickets"] > 0
        assert results["complaints"] > 0

    def test_monthly_trend_structure(self, analyzer, sample_customer_id):
        """Monthly trend should return list of month records."""
        # First ensure we have sentiment data
        analyzer.batch_analyze_all()
        trend = analyzer.compute_monthly_trend(sample_customer_id)
        assert isinstance(trend, list)
        if trend:
            entry = trend[0]
            assert "month" in entry
            assert "avg_score" in entry
            assert "count" in entry
            assert "label" in entry

    def test_monthly_trend_scores_in_range(self, analyzer, sample_customer_id):
        """Monthly average scores should be in [-1, 1]."""
        analyzer.batch_analyze_all()
        trend = analyzer.compute_monthly_trend(sample_customer_id)
        for entry in trend:
            assert -1.0 <= entry["avg_score"] <= 1.0

    def test_customer_sentiment_summary(self, analyzer, sample_customer_id):
        """Summary should have expected structure."""
        analyzer.batch_analyze_all()
        summary = analyzer.get_customer_sentiment_summary(sample_customer_id)
        assert "customer_id" in summary
        assert "avg_sentiment" in summary
        assert "distribution" in summary
        assert "trend_direction" in summary
        assert summary["trend_direction"] in (
            "improving", "declining", "stable", "insufficient_data"
        )


class TestAlertDetection:
    """Test declining sentiment alert detection."""

    def test_detect_declining_returns_list(self, analyzer):
        """Should return a list of flagged customers."""
        analyzer.batch_analyze_all()
        flagged = analyzer.detect_declining_sentiment()
        assert isinstance(flagged, list)

    def test_flagged_customer_structure(self, analyzer):
        """Flagged customers should have expected fields."""
        analyzer.batch_analyze_all()
        flagged = analyzer.detect_declining_sentiment()
        if flagged:
            entry = flagged[0]
            assert "customer_id" in entry
            assert "consecutive_declining_months" in entry
            assert entry["consecutive_declining_months"] >= 2

    def test_generate_alerts(self, analyzer):
        """Should create alert records."""
        analyzer.batch_analyze_all()
        flagged = analyzer.detect_declining_sentiment()
        if flagged:
            count = analyzer.generate_alerts(flagged)
            assert count > 0
        # If no flagged customers, that's also valid (good sentiment)


# ==================================================================
# Risk Profile Tests
# ==================================================================

class TestRiskProfiler:
    """Test the RiskProfiler engine."""

    def test_profile_structure(self, profiler, sample_customer_id):
        """Risk profile should have all required fields per TODO spec."""
        profile = profiler.generate_risk_profile(sample_customer_id)
        assert "customer_id" in profile
        assert "risk_level" in profile
        assert "sentiment" in profile
        assert "fraud_risk" in profile
        assert "retention_probability" in profile
        assert "risk_factors" in profile

    def test_risk_level_valid(self, profiler, sample_customer_id):
        """Risk level must be Low, Medium, or High."""
        profile = profiler.generate_risk_profile(sample_customer_id)
        assert profile["risk_level"] in ("Low", "Medium", "High")

    def test_sentiment_valid(self, profiler, sample_customer_id):
        """Sentiment must be Positive, Neutral, or Negative."""
        profile = profiler.generate_risk_profile(sample_customer_id)
        assert profile["sentiment"] in ("Positive", "Neutral", "Negative")

    def test_fraud_risk_valid(self, profiler, sample_customer_id):
        """Fraud risk must be Low, Medium, or High."""
        profile = profiler.generate_risk_profile(sample_customer_id)
        assert profile["fraud_risk"] in ("Low", "Medium", "High")

    def test_retention_probability_range(self, profiler, sample_customer_id):
        """Retention probability must be in [0, 1]."""
        profile = profiler.generate_risk_profile(sample_customer_id)
        assert 0 <= profile["retention_probability"] <= 1

    def test_risk_factors_is_list(self, profiler, sample_customer_id):
        """Risk factors must be a list of strings."""
        profile = profiler.generate_risk_profile(sample_customer_id)
        assert isinstance(profile["risk_factors"], list)
        for factor in profile["risk_factors"]:
            assert isinstance(factor, str)

    def test_invalid_customer(self, profiler):
        """Invalid customer should return error."""
        profile = profiler.generate_risk_profile("NONEXISTENT")
        assert "error" in profile

    def test_batch_profile(self, profiler):
        """Batch profiling should return a DataFrame."""
        batch = profiler.batch_profile(limit=5)
        assert isinstance(batch, pd.DataFrame)
        assert len(batch) == 5
        assert "risk_level" in batch.columns


class TestRetentionModel:
    """Test the logistic regression retention model."""

    def test_train_retention_model(self, profiler):
        """Training should succeed and return metrics."""
        result = profiler.train_retention_model()
        assert "accuracy" in result
        assert "feature_coefficients" in result
        assert "model_path" in result
        assert result["accuracy"] > 0.5  # Better than random

    def test_predict_after_training(self, profiler, sample_customer_id):
        """After training, predictions should work."""
        profiler.train_retention_model()
        prob = profiler.predict_retention(sample_customer_id)
        assert 0 <= prob <= 1

    def test_feature_coefficients_complete(self, profiler):
        """All 5 features should have coefficients."""
        result = profiler.train_retention_model()
        expected_features = {
            "avg_sentiment",
            "support_ticket_count",
            "fraud_flag_count",
            "interaction_count",
            "balance_normalized",
        }
        assert set(result["feature_coefficients"].keys()) == expected_features

    def test_model_saved_to_disk(self, profiler):
        """Model should be saved to models/retention_model.pkl."""
        profiler.train_retention_model()
        assert os.path.exists("models/retention_model.pkl")


# ==================================================================
# Product Recommendation Tests
# ==================================================================

class TestProductRecommender:
    """Test the rule-based product recommendation engine."""

    def test_returns_list(self, recommender, sample_customer_id):
        """Recommendations should be a list."""
        recs = recommender.recommend(sample_customer_id)
        assert isinstance(recs, list)

    def test_max_three_recommendations(self, recommender, sample_customer_id):
        """Should return at most 3 recommendations."""
        recs = recommender.recommend(sample_customer_id)
        assert len(recs) <= 3

    def test_recommendation_structure(self, recommender, sample_customer_id):
        """Each recommendation should have product, reason, confidence."""
        recs = recommender.recommend(sample_customer_id)
        if recs:
            rec = recs[0]
            assert "product" in rec
            assert "reason" in rec
            assert "confidence" in rec
            assert "category" in rec

    def test_confidence_in_range(self, recommender, sample_customer_id):
        """Confidence should be in [0, 1]."""
        recs = recommender.recommend(sample_customer_id)
        for rec in recs:
            assert 0 <= rec["confidence"] <= 1

    def test_sorted_by_confidence(self, recommender, sample_customer_id):
        """Recommendations should be sorted by confidence (descending)."""
        recs = recommender.recommend(sample_customer_id)
        if len(recs) >= 2:
            for i in range(len(recs) - 1):
                assert recs[i]["confidence"] >= recs[i + 1]["confidence"]

    def test_reason_is_nonempty_string(self, recommender, sample_customer_id):
        """Reason should be a non-empty string."""
        recs = recommender.recommend(sample_customer_id)
        for rec in recs:
            assert isinstance(rec["reason"], str)
            assert len(rec["reason"]) > 10

    def test_invalid_customer_empty_list(self, recommender):
        """Invalid customer should return empty list."""
        recs = recommender.recommend("NONEXISTENT")
        assert recs == []

    def test_multiple_customers_get_recs(self, recommender, five_customer_ids):
        """Multiple customers should all get recommendations."""
        for cid in five_customer_ids:
            recs = recommender.recommend(cid)
            assert isinstance(recs, list)
            # At least some should have recommendations
        # Verify at least one got recs
        all_recs = [recommender.recommend(cid) for cid in five_customer_ids]
        assert any(len(r) > 0 for r in all_recs)

    def test_no_duplicate_products(self, recommender, five_customer_ids):
        """No duplicate product names in a single customer's recs."""
        for cid in five_customer_ids:
            recs = recommender.recommend(cid)
            products = [r["product"] for r in recs]
            assert len(products) == len(set(products))


# ==================================================================
# Integration Tests
# ==================================================================

class TestIntegration:
    """Test that Phase 7 modules integrate with existing customer context."""

    def test_customer_context_includes_risk_profile(self, sample_customer_id):
        """Full customer context should include risk_profile."""
        from src.rag.customer_context import get_full_customer_context
        context = get_full_customer_context(sample_customer_id)
        assert "risk_profile" in context
        assert "risk_level" in context["risk_profile"]

    def test_customer_context_includes_recommendations(self, sample_customer_id):
        """Full customer context should include recommendations."""
        from src.rag.customer_context import get_full_customer_context
        context = get_full_customer_context(sample_customer_id)
        assert "recommendations" in context
        assert isinstance(context["recommendations"], list)

    def test_formatted_context_includes_risk(self, sample_customer_id):
        """Formatted context string should include risk profile section."""
        from src.rag.customer_context import get_full_customer_context, format_customer_context
        context = get_full_customer_context(sample_customer_id)
        formatted = format_customer_context(context)
        assert "RISK PROFILE" in formatted

    def test_formatted_context_includes_recommendations(self, sample_customer_id):
        """Formatted context string should include product recommendations."""
        from src.rag.customer_context import get_full_customer_context, format_customer_context
        context = get_full_customer_context(sample_customer_id)
        formatted = format_customer_context(context)
        assert "PRODUCT RECOMMENDATIONS" in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
