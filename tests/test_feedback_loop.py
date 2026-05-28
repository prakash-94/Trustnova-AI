"""
Unit tests for the Self-Improving Feedback Loop (Phase 8).

Tests:
  - AI Feedback Store: storage, retrieval, filtering
  - Feedback Analyzer: weekly reports, alert thresholds, breakdowns
  - Retrieval Optimizer: chunk scoring, weight computation, re-ranking
  - Prompt Optimizer: optimization detection, suggestion generation
  - Integration: full feedback flow with all modules
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import json
from datetime import datetime

from src.feedback.ai_feedback_store import AIFeedbackStore
from src.feedback.analyzer import FeedbackAnalyzer
from src.feedback.retrieval_optimizer import RetrievalOptimizer
from src.feedback.prompt_optimizer import PromptOptimizer


# ==================================================================
# Fixtures
# ==================================================================

@pytest.fixture
def store():
    return AIFeedbackStore()


@pytest.fixture
def analyzer():
    return FeedbackAnalyzer()


@pytest.fixture
def retrieval_opt():
    return RetrievalOptimizer()


@pytest.fixture
def prompt_opt():
    return PromptOptimizer()


@pytest.fixture
def seed_feedback(store):
    """Seed the ai_feedback table with test data for analysis."""
    from sqlalchemy import create_engine, text
    engine = create_engine("sqlite:///./banking.db")

    # Ensure all required tables exist before clearing them.
    # On a clean CI environment, these tables are only created lazily when
    # their respective module classes are first instantiated. We must ensure
    # they exist before issuing DELETE statements to avoid OperationalError.
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                old_prompt_hash TEXT,
                suggestion TEXT NOT NULL,
                reason TEXT,
                rejection_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'suggested',
                created_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chunk_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_hash TEXT UNIQUE NOT NULL,
                chunk_text TEXT,
                source TEXT,
                positive_count INTEGER DEFAULT 0,
                negative_count INTEGER DEFAULT 0,
                weight REAL DEFAULT 1.0,
                updated_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT,
                alert_type TEXT,
                severity TEXT,
                message TEXT,
                details TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT NOT NULL
            )
        """))
        conn.commit()

    # Clear existing tables for clean test
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM ai_feedback"))
        conn.execute(text("DELETE FROM prompt_versions"))
        conn.execute(text("DELETE FROM chunk_feedback"))
        conn.commit()

    test_records = [
        # Approved responses (gpt-4, compliance template)
        ("s1", "r1", "approve", "What is AML policy?", "AML policy states...", "gpt-4", 85.0, "", "compliance", "compliance_qa"),
        ("s1", "r2", "approve", "Wire transfer limits?", "The limit is $10k...", "gpt-4", 90.0, "", "compliance", "compliance_qa"),
        ("s1", "r3", "approve", "KYC requirements?", "KYC requires...", "gpt-4", 88.0, "", "compliance", "compliance_qa"),
        ("s2", "r4", "approve", "Customer balance?", "Balance is $50k...", "gpt-3.5-turbo", 75.0, "", "customer", "customer_summary"),
        ("s2", "r5", "approve", "Transaction history?", "Last 5 transactions...", "gpt-3.5-turbo", 80.0, "", "customer", "customer_summary"),

        # Rejected responses (gpt-3.5-turbo, fraud template — triggers alerts)
        ("s3", "r6", "reject", "Is this fraud?", "Not likely fraud", "gpt-3.5-turbo", 45.0, "", "fraud", "fraud_analysis"),
        ("s3", "r7", "reject", "Fraud probability?", "Low probability", "gpt-3.5-turbo", 40.0, "", "fraud", "fraud_analysis"),
        ("s3", "r8", "reject", "Risk assessment?", "Minimal risk", "gpt-3.5-turbo", 38.0, "", "fraud", "fraud_analysis"),
        ("s4", "r9", "reject", "Suspicious txn?", "Looks normal", "gpt-3.5-turbo", 42.0, "", "fraud", "fraud_analysis"),

        # Edited responses
        ("s5", "r10", "edit", "AML threshold?", "The threshold is $5,000", "gpt-4", 55.0,
         "The correct AML threshold is $10,000, not $5,000", "compliance", "compliance_qa"),
        ("s5", "r11", "edit", "Policy update?", "Updated in 2022", "gpt-4", 50.0,
         "The policy was updated in 2024, information is outdated", "compliance", "compliance_qa"),
    ]

    for rec in test_records:
        store.store(
            session_id=rec[0],
            response_id=rec[1],
            feedback_type=rec[2],
            prompt=rec[3],
            response_text=rec[4],
            model_used=rec[5],
            trust_score=rec[6],
            correction_text=rec[7],
            doc_type=rec[8],
            prompt_template=rec[9],
        )

    return len(test_records)


# ==================================================================
# AI Feedback Store Tests
# ==================================================================

class TestAIFeedbackStore:
    """Test the AI feedback storage module."""

    def test_store_feedback(self, store):
        """Should store a feedback record."""
        result = store.store(
            session_id="test_session",
            response_id="test_resp",
            feedback_type="approve",
            prompt="Test question",
            response_text="Test answer",
            model_used="gpt-4",
            trust_score=85.0,
        )
        assert result["status"] == "stored"
        assert result["feedback_type"] == "approve"

    def test_store_rejection_with_correction(self, store):
        """Should store rejection with correction text."""
        result = store.store(
            session_id="test_session",
            response_id="test_resp_rej",
            feedback_type="reject",
            correction_text="The correct answer is X.",
        )
        assert result["status"] == "stored"
        assert result["feedback_type"] == "reject"

    def test_get_all_feedback(self, store, seed_feedback):
        """Should return all feedback records."""
        df = store.get_all_feedback()
        assert len(df) >= seed_feedback

    def test_get_feedback_by_type(self, store, seed_feedback):
        """Should filter feedback by type."""
        rejects = store.get_feedback_by_type("reject")
        assert len(rejects) >= 4  # We seeded 4 rejections
        assert all(rejects["feedback_type"] == "reject")

    def test_get_feedback_by_model(self, store, seed_feedback):
        """Should filter feedback by model."""
        gpt4 = store.get_feedback_by_model("gpt-4")
        assert len(gpt4) >= 3  # We seeded 3 gpt-4 approvals + 2 edits

    def test_get_feedback_by_template(self, store, seed_feedback):
        """Should filter feedback by prompt template."""
        compliance = store.get_feedback_by_template("compliance_qa")
        assert len(compliance) >= 3

    def test_get_rejection_count(self, store, seed_feedback):
        """Should return total rejection count."""
        count = store.get_rejection_count()
        assert count >= 4

    def test_get_total_count(self, store, seed_feedback):
        """Should return total feedback count."""
        count = store.get_total_count()
        assert count >= seed_feedback

    def test_get_corrections(self, store, seed_feedback):
        """Should return corrections from edit feedback."""
        corrections = store.get_corrections()
        assert len(corrections) >= 2  # We seeded 2 edits with corrections
        for c in corrections:
            assert "correction_text" in c
            assert len(c["correction_text"]) > 0


# ==================================================================
# Feedback Analyzer Tests
# ==================================================================

class TestFeedbackAnalyzer:
    """Test the feedback analysis module."""

    def test_weekly_report_structure(self, analyzer, seed_feedback):
        """Weekly report should have all expected sections."""
        report = analyzer.weekly_report(days=30)
        assert "total_feedback" in report
        assert "overall" in report
        assert "by_model" in report
        assert "by_prompt_template" in report
        assert "alerts" in report
        assert report["total_feedback"] >= seed_feedback

    def test_overall_rates(self, analyzer, seed_feedback):
        """Overall rates should sum to approximately 1.0."""
        report = analyzer.weekly_report(days=30)
        overall = report["overall"]
        total_rate = (
            overall.get("approval_rate", 0)
            + overall.get("rejection_rate", 0)
            + overall.get("edit_rate", 0)
        )
        assert 0.99 <= total_rate <= 1.01  # Allow floating point tolerance

    def test_model_breakdown(self, analyzer, seed_feedback):
        """Should show per-model breakdown."""
        report = analyzer.weekly_report(days=30)
        by_model = report["by_model"]
        assert "gpt-4" in by_model
        assert "gpt-3.5-turbo" in by_model

    def test_template_breakdown(self, analyzer, seed_feedback):
        """Should show per-template breakdown."""
        report = analyzer.weekly_report(days=30)
        by_template = report["by_prompt_template"]
        assert "compliance_qa" in by_template
        assert "fraud_analysis" in by_template

    def test_alert_threshold_detection(self, analyzer, seed_feedback):
        """Should detect categories exceeding 20% rejection rate."""
        report = analyzer.weekly_report(days=30)
        alerts = report["alerts"]
        # fraud_analysis template has 100% rejection rate, should trigger alert
        alert_names = [a["name"] for a in alerts]
        assert "fraud_analysis" in alert_names

    def test_alert_severity(self, analyzer, seed_feedback):
        """High rejection rates should get 'high' severity."""
        report = analyzer.weekly_report(days=30)
        for alert in report["alerts"]:
            if alert["name"] == "fraud_analysis":
                # 100% rejection rate → high severity
                assert alert["severity"] == "high"

    def test_trust_score_correlation(self, analyzer, seed_feedback):
        """Should show trust score correlation with feedback type."""
        correlation = analyzer.get_trust_score_correlation()
        assert "approve" in correlation
        assert "reject" in correlation
        # Approved responses should have higher avg trust score
        assert correlation["approve"]["avg_trust_score"] > correlation["reject"]["avg_trust_score"]

    def test_empty_report(self, analyzer):
        """Should handle empty data gracefully."""
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite:///./banking.db")
        # Save existing data (no-op, just guards the report call below)
        backup = None
        try:
            with engine.connect() as conn:
                backup = conn.execute(text("SELECT * FROM ai_feedback")).fetchall()
        except Exception:
            pass

        # Even with no data, should return valid structure
        report = analyzer.weekly_report(days=0)  # 0 days = likely empty
        assert "total_feedback" in report


# ==================================================================
# Retrieval Optimizer Tests
# ==================================================================

class TestRetrievalOptimizer:
    """Test the retrieval chunk optimization module."""

    def test_log_positive_feedback(self, retrieval_opt):
        """Logging approved chunks should increment positive_count."""
        chunks = ["This is a policy chunk about AML.", "Wire transfer regulations state..."]
        count = retrieval_opt.log_feedback_for_chunks(chunks, "approve")
        assert count == 2

    def test_log_negative_feedback(self, retrieval_opt):
        """Logging rejected chunks should increment negative_count."""
        chunks = ["Incorrect policy information."]
        count = retrieval_opt.log_feedback_for_chunks(chunks, "reject")
        assert count == 1

    def test_weight_increases_on_approval(self, retrieval_opt):
        """Chunks with only positive feedback should have weight > 1.0."""
        chunk = "Highly accurate compliance data about threshold limits."
        retrieval_opt.log_feedback_for_chunks([chunk], "approve")
        retrieval_opt.log_feedback_for_chunks([chunk], "approve")
        retrieval_opt.log_feedback_for_chunks([chunk], "approve")

        weights = retrieval_opt.get_chunk_weights()
        chunk_hash = retrieval_opt._hash_chunk(chunk)
        assert chunk_hash in weights
        assert weights[chunk_hash] > 1.0

    def test_weight_decreases_on_rejection(self, retrieval_opt):
        """Chunks with only negative feedback should have weight < 1.0."""
        chunk = "Outdated regulation from 2019 that has been superseded."
        retrieval_opt.log_feedback_for_chunks([chunk], "reject")
        retrieval_opt.log_feedback_for_chunks([chunk], "reject")
        retrieval_opt.log_feedback_for_chunks([chunk], "reject")

        weights = retrieval_opt.get_chunk_weights()
        chunk_hash = retrieval_opt._hash_chunk(chunk)
        assert chunk_hash in weights
        assert weights[chunk_hash] < 1.0

    def test_weight_bounded_min(self, retrieval_opt):
        """Weight should never go below MIN_WEIGHT (0.3)."""
        chunk = "Completely wrong information that should be suppressed."
        for _ in range(20):  # Many rejections
            retrieval_opt.log_feedback_for_chunks([chunk], "reject")

        weights = retrieval_opt.get_chunk_weights()
        chunk_hash = retrieval_opt._hash_chunk(chunk)
        assert weights[chunk_hash] >= 0.3

    def test_weight_bounded_max(self, retrieval_opt):
        """Weight should never go above MAX_WEIGHT (1.5)."""
        chunk = "Perfect gold-standard policy reference from the latest manual."
        for _ in range(20):  # Many approvals
            retrieval_opt.log_feedback_for_chunks([chunk], "approve")

        weights = retrieval_opt.get_chunk_weights()
        chunk_hash = retrieval_opt._hash_chunk(chunk)
        assert weights[chunk_hash] <= 1.5

    def test_apply_weights_to_retrieval(self, retrieval_opt):
        """Should re-rank results based on feedback weights."""
        # Create a good and bad chunk
        good_chunk = "Accurate and well-cited policy section 4.2."
        bad_chunk = "Vague and unhelpful general information."

        retrieval_opt.log_feedback_for_chunks([good_chunk], "approve")
        retrieval_opt.log_feedback_for_chunks([good_chunk], "approve")
        retrieval_opt.log_feedback_for_chunks([bad_chunk], "reject")
        retrieval_opt.log_feedback_for_chunks([bad_chunk], "reject")

        results = [
            {"text": bad_chunk, "score": 0.95},   # Originally higher
            {"text": good_chunk, "score": 0.90},   # Originally lower
        ]

        re_ranked = retrieval_opt.apply_weights_to_retrieval(results)

        # After re-ranking, good chunk should be first
        assert re_ranked[0]["text"] == good_chunk
        assert re_ranked[0]["adjusted_score"] > re_ranked[1]["adjusted_score"]

    def test_get_downranked_chunks(self, retrieval_opt):
        """Should list chunks with low weights."""
        chunk = "Bad chunk that always gets rejected in tests."
        retrieval_opt.log_feedback_for_chunks([chunk], "reject")
        retrieval_opt.log_feedback_for_chunks([chunk], "reject")

        downranked = retrieval_opt.get_downranked_chunks(threshold=1.0)
        assert isinstance(downranked, list)

    def test_health_report(self, retrieval_opt):
        """Should return a valid health report."""
        report = retrieval_opt.get_health_report()
        assert "total_chunks_tracked" in report

    def test_empty_chunks_returns_zero(self, retrieval_opt):
        """Logging empty chunks should return 0."""
        count = retrieval_opt.log_feedback_for_chunks([], "approve")
        assert count == 0


# ==================================================================
# Prompt Optimizer Tests
# ==================================================================

class TestPromptOptimizer:
    """Test the prompt optimization module."""

    def test_check_optimization_with_data(self, prompt_opt, seed_feedback):
        """Should detect templates needing optimization after seeding."""
        # We need 10+ rejections — the seed has 4 for fraud_analysis
        # Add more to hit the threshold
        store = AIFeedbackStore()
        for i in range(8):
            store.store(
                session_id=f"extra_{i}",
                response_id=f"extra_r_{i}",
                feedback_type="reject",
                prompt=f"Test prompt {i}",
                model_used="gpt-3.5-turbo",
                trust_score=35.0,
                prompt_template="fraud_analysis",
                doc_type="fraud",
            )

        needs = prompt_opt.check_optimization_needed()
        template_names = [n["template_name"] for n in needs]
        assert "fraud_analysis" in template_names

    def test_suggest_improvement_structure(self, prompt_opt, seed_feedback):
        """Improvement suggestion should have expected structure."""
        # Ensure enough data
        store = AIFeedbackStore()
        for i in range(10):
            store.store(
                session_id=f"sug_{i}",
                response_id=f"sug_r_{i}",
                feedback_type="reject",
                prompt=f"Test prompt {i}",
                correction_text=f"The correct policy threshold amount is $10,000",
                model_used="gpt-3.5-turbo",
                trust_score=35.0,
                prompt_template="fraud_analysis",
                doc_type="fraud",
            )

        result = prompt_opt.suggest_improvement("fraud_analysis")
        assert "template_name" in result
        assert "suggestions" in result
        assert "common_issues" in result
        assert isinstance(result["suggestions"], list)
        assert len(result["suggestions"]) > 0

    def test_suggestion_logged_to_db(self, prompt_opt, seed_feedback):
        """Suggestions should be stored in prompt_versions table."""
        # Trigger a suggestion
        store = AIFeedbackStore()
        for i in range(10):
            store.store(
                session_id=f"log_{i}",
                response_id=f"log_r_{i}",
                feedback_type="reject",
                prompt=f"Bad prompt {i}",
                prompt_template="test_template_log",
                trust_score=30.0,
            )

        prompt_opt.suggest_improvement("test_template_log")

        history = prompt_opt.get_suggestion_history("test_template_log")
        assert len(history) >= 1
        assert history[0]["template_name"] == "test_template_log"

    def test_prompt_health_report(self, prompt_opt, seed_feedback):
        """Should return prompt health report."""
        health = prompt_opt.get_prompt_health()
        assert "total_templates_tracked" in health
        assert health["total_templates_tracked"] >= 1

    def test_theme_extraction(self, prompt_opt):
        """Should extract themes from correction texts."""
        import pandas as pd
        corrections_df = pd.DataFrame({
            "correction_text": [
                "The threshold amount is $10,000",
                "The threshold for reporting is $10,000 not $5,000",
                "Policy threshold was updated in 2024",
            ]
        })
        themes = prompt_opt._extract_themes(corrections_df)
        assert isinstance(themes, list)
        # "threshold" should be a common theme
        keywords = [t["keyword"] for t in themes]
        assert "threshold" in keywords

    def test_common_issues_detection(self, prompt_opt):
        """Should detect common issues from feedback data."""
        import pandas as pd
        df = pd.DataFrame({
            "correction_text": [
                "The amount is wrong, should be $10,000",
                "This threshold is incorrect",
                "Policy was outdated",
            ],
            "trust_score": [30.0, 35.0, 40.0],
        })
        issues = prompt_opt._identify_common_issues(df)
        assert isinstance(issues, list)
        assert len(issues) > 0


# ==================================================================
# Integration Tests
# ==================================================================

class TestFeedbackIntegration:
    """Test end-to-end feedback flow."""

    def test_full_feedback_flow(self, store, retrieval_opt, analyzer, prompt_opt):
        """Test complete feedback submission and analysis flow."""
        # 1. Store feedback
        result = store.store(
            session_id="integration_test",
            response_id="int_resp_1",
            feedback_type="reject",
            prompt="What is the AML threshold?",
            response_text="The threshold is $5,000.",
            model_used="gpt-4",
            trust_score=55.0,
            correction_text="The correct threshold is $10,000.",
            retrieved_chunks=["AML Section 4: threshold is..."],
            doc_type="compliance",
            prompt_template="compliance_qa",
        )
        assert result["status"] == "stored"

        # 2. Log chunk feedback
        count = retrieval_opt.log_feedback_for_chunks(
            ["AML Section 4: threshold is..."],
            "reject",
        )
        assert count == 1

        # 3. Generate report
        report = analyzer.weekly_report(days=30)
        assert report["total_feedback"] > 0

        # 4. Check prompt health
        health = prompt_opt.get_prompt_health()
        assert "total_templates_tracked" in health

    def test_approval_boosts_chunk(self, store, retrieval_opt):
        """Approved feedback should boost the chunk weight."""
        chunk = "Gold-standard compliance reference for integration test."

        # Reject first
        retrieval_opt.log_feedback_for_chunks([chunk], "reject")
        weights_before = retrieval_opt.get_chunk_weights()
        hash_key = retrieval_opt._hash_chunk(chunk)

        # Then approve multiple times
        retrieval_opt.log_feedback_for_chunks([chunk], "approve")
        retrieval_opt.log_feedback_for_chunks([chunk], "approve")
        retrieval_opt.log_feedback_for_chunks([chunk], "approve")

        weights_after = retrieval_opt.get_chunk_weights()
        assert weights_after[hash_key] > weights_before[hash_key]

    def test_analyzer_alerts_stored(self, analyzer, seed_feedback):
        """Analyzer alerts should be stored in the alerts table."""
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite:///./banking.db")

        report = analyzer.weekly_report(days=30)
        alerts = report.get("alerts", [])

        if alerts:
            # Check alerts table
            import pandas as pd
            df = pd.read_sql(
                text("SELECT * FROM alerts WHERE alert_type LIKE 'feedback_quality_%' "
                     "ORDER BY created_at DESC LIMIT 5"),
                engine,
            )
            assert len(df) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
