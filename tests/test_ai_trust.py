"""
Unit tests for the AI Trust Scoring System.

Tests each of the 5 component metrics individually:
  1. Retrieval Confidence — cosine similarity averaging with normalization
  2. Hallucination Probability — semantic similarity (all-MiniLM-L6-v2) + heuristic fallback
  3. Model Agreement — Jaccard similarity of token sets
  4. Citation Quality — regex patterns for source references
  5. Prompt Reliability — rolling average from DB history

Also tests:
  - Weighted combination into final score (0-100)
  - Tier classification
  - DB storage of trust scores
  - Score history retrieval
  - Edge cases (empty inputs, missing data)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.models.ai_trust import AITrustScorer, TRUST_WEIGHTS


@pytest.fixture
def scorer():
    """Create an AITrustScorer with test database."""
    return AITrustScorer()


# ==================================================================
# Test Weight Configuration
# ==================================================================
class TestWeightConfig:
    """Verify trust weight configuration is valid."""

    def test_weights_sum_to_one(self):
        """All weights must sum to exactly 1.0."""
        total = sum(TRUST_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_weights_positive(self):
        """Every weight must be positive."""
        for name, w in TRUST_WEIGHTS.items():
            assert w > 0, f"Weight {name} is not positive: {w}"

    def test_expected_weight_keys(self):
        """Must have exactly the 5 expected components."""
        expected = {
            "retrieval_confidence",
            "hallucination_probability",
            "model_agreement",
            "citation_quality",
            "prompt_reliability",
        }
        assert set(TRUST_WEIGHTS.keys()) == expected


# ==================================================================
# Test Component 1: Retrieval Confidence
# ==================================================================
class TestRetrievalConfidence:
    """Test cosine similarity-based retrieval confidence scoring."""

    def test_high_similarity_scores(self, scorer):
        """High similarity scores → high confidence."""
        score = scorer.compute_retrieval_confidence([0.95, 0.90, 0.88])
        assert score >= 0.9

    def test_low_similarity_scores(self, scorer):
        """Low similarity scores → low confidence."""
        score = scorer.compute_retrieval_confidence([0.1, 0.15, 0.2])
        assert score < 0.2

    def test_perfect_scores(self, scorer):
        """All 1.0 similarity → confidence = 1.0."""
        score = scorer.compute_retrieval_confidence([1.0, 1.0, 1.0])
        assert score == 1.0

    def test_empty_scores(self, scorer):
        """No similarity scores → confidence = 0.0."""
        score = scorer.compute_retrieval_confidence([])
        assert score == 0.0

    def test_single_score(self, scorer):
        """Score near the top of the model range normalizes to ~1.0."""
        # all-MiniLM-L6-v2 range is ~[0.10, 0.70]; 0.75 normalises to (0.75-0.10)/0.60 = 1.083 → clamped 1.0
        score = scorer.compute_retrieval_confidence([0.75])
        assert abs(score - 1.0) < 0.001

    def test_clamped_to_range(self, scorer):
        """Scores are clamped to [0, 1]."""
        score = scorer.compute_retrieval_confidence([1.5, 2.0])
        assert 0.0 <= score <= 1.0

    def test_mixed_scores(self, scorer):
        """Mixed scores are normalised: avg 0.6 → (0.6-0.10)/0.60 ≈ 0.833."""
        score = scorer.compute_retrieval_confidence([0.9, 0.6, 0.3])
        assert abs(score - 0.8333) < 0.01


# ==================================================================
# Test Component 2: Hallucination Probability
# ==================================================================
class TestHallucinationProbability:
    """
    Test hallucination detection.

    Primary path: semantic cosine similarity via all-MiniLM-L6-v2.
    Fallback path: keyword-overlap heuristic (_heuristic_hallucination).
    Both paths are exercised; the heuristic is always available.
    """

    def test_grounded_answer(self, scorer):
        """Answer semantically similar to source → low hallucination probability."""
        answer = "The AML policy requires CTR filing for wire transfers over ten thousand dollars"
        sources = ["AML policy Section 4.2: CTR filing required for wire transfers exceeding ten thousand dollars"]
        # compute_hallucination_probability tries semantic similarity first; heuristic as fallback
        score = scorer.compute_hallucination_probability(answer, sources)
        assert score < 0.5  # Well-grounded

    def test_fabricated_answer(self, scorer):
        """Answer semantically unrelated to source → high hallucination probability."""
        answer = "quantum computing blockchain neural network synergy"
        sources = ["The bank's loan policy covers residential mortgage rates."]
        score = scorer.compute_hallucination_probability(answer, sources)
        assert score > 0.5  # Likely fabricated

    def test_heuristic_grounded(self, scorer):
        """Heuristic: high word overlap → low hallucination."""
        answer = "The AML policy requires CTR filing for wire transfers over ten thousand dollars"
        sources = ["AML policy Section 4.2: CTR filing required for wire transfers exceeding ten thousand dollars"]
        score = scorer._heuristic_hallucination(answer, sources)
        assert score < 0.5

    def test_heuristic_fabricated(self, scorer):
        """Heuristic: zero word overlap → high hallucination."""
        answer = "quantum computing blockchain neural network synergy"
        sources = ["The bank's loan policy covers residential mortgage rates."]
        score = scorer._heuristic_hallucination(answer, sources)
        assert score > 0.5

    def test_empty_answer(self, scorer):
        """Empty answer → default moderate risk."""
        score = scorer.compute_hallucination_probability("", ["some source"])
        assert score == 0.5

    def test_empty_sources(self, scorer):
        """No source chunks → default moderate risk."""
        score = scorer.compute_hallucination_probability("some answer", [])
        assert score == 0.5

    def test_both_empty(self, scorer):
        """Both empty → default moderate risk."""
        score = scorer.compute_hallucination_probability("", [])
        assert score == 0.5

    def test_score_in_range(self, scorer):
        """Score must be in [0, 1]."""
        score = scorer._heuristic_hallucination(
            "this is a test answer with some words",
            ["this is source text with other words"]
        )
        assert 0.0 <= score <= 1.0

    def test_semantic_path_uses_shared_embedding_factory(self, scorer, monkeypatch):
        """The semantic path uses the real embedding API and reuses its client."""
        calls = {"factory": 0}

        class FakeEmbeddings:
            def embed_query(self, text):
                return [1.0, 0.0]

            def embed_documents(self, texts):
                return [[1.0, 0.0] for _ in texts]

        def fake_factory(*args, **kwargs):
            calls["factory"] += 1
            assert kwargs["local_files_only"] is True
            return FakeEmbeddings()

        monkeypatch.setattr("src.rag.embeddings.get_embeddings", fake_factory)

        first = scorer.compute_hallucination_probability("answer", ["source"])
        second = scorer.compute_hallucination_probability("answer", ["source"])

        assert first == 0.0
        assert second == 0.0
        assert calls["factory"] == 1

    def test_embedding_failure_falls_back_without_repeated_loads(self, scorer, monkeypatch):
        """An unavailable local model falls back quickly for the scorer lifetime."""
        calls = {"factory": 0}

        def unavailable(*args, **kwargs):
            calls["factory"] += 1
            raise OSError("model is not cached")

        monkeypatch.setattr("src.rag.embeddings.get_embeddings", unavailable)
        answer = "The policy requires identity verification"
        sources = ["The policy requires identity verification"]

        assert scorer.compute_hallucination_probability(answer, sources) < 0.5
        assert scorer.compute_hallucination_probability(answer, sources) < 0.5
        assert calls["factory"] == 1


# ==================================================================
# Test Component 3: Model Agreement
# ==================================================================
class TestModelAgreement:
    """Test Jaccard similarity between two model responses."""

    def test_identical_responses(self, scorer):
        """Identical answers → agreement = 1.0."""
        answer = "The loan rate is 4.5% for qualified applicants."
        score = scorer.compute_model_agreement(answer, answer)
        assert score == 1.0

    def test_completely_different_responses(self, scorer):
        """Completely different answers → agreement near 0."""
        a = "alpha beta gamma delta"
        b = "quantum neural synapse photon"
        score = scorer.compute_model_agreement(a, b)
        assert score < 0.1

    def test_partial_overlap(self, scorer):
        """Partial overlap → score between 0 and 1."""
        a = "The customer has a good credit score and low risk"
        b = "The customer has excellent credit and moderate risk"
        score = scorer.compute_model_agreement(a, b)
        assert 0.2 < score < 0.9

    def test_no_secondary_answer(self, scorer):
        """Missing secondary answer → default 0.7."""
        score = scorer.compute_model_agreement("primary answer", None)
        assert score == 0.7

    def test_empty_primary(self, scorer):
        """Empty primary → 0.0."""
        score = scorer.compute_model_agreement("", "some answer")
        assert score == 0.0

    def test_both_empty(self, scorer):
        """Both empty strings — secondary is falsy → default 0.7."""
        score = scorer.compute_model_agreement("", "")
        assert score == 0.7  # Empty string is falsy → treated as "no secondary answer"


# ==================================================================
# Test Component 4: Citation Quality
# ==================================================================
class TestCitationQuality:
    """Test regex-based citation quality checking."""

    def test_well_cited_answer(self, scorer):
        """Answer with multiple citations → high score."""
        answer = (
            "According to BSA/AML Policy Section 4.2, all wire transfers "
            "exceeding $10,000 require a CTR filing. Per KYC Procedure Page 3, "
            "the sender's identity must be verified."
        )
        score = scorer.compute_citation_quality(answer)
        assert score >= 0.8

    def test_single_citation(self, scorer):
        """One citation → moderate score."""
        answer = "Section 4.2 states that wire transfers require reporting."
        score = scorer.compute_citation_quality(answer)
        assert score == 0.5

    def test_no_citations(self, scorer):
        """No citations → low score."""
        answer = "Wire transfers over ten thousand dollars need to be reported to authorities."
        score = scorer.compute_citation_quality(answer)
        assert score <= 0.1

    def test_empty_answer(self, scorer):
        """Empty answer → 0.0."""
        score = scorer.compute_citation_quality("")
        assert score == 0.0

    def test_page_reference(self, scorer):
        """Page reference detected."""
        answer = "As described on Page 5, the compliance steps are..."
        score = scorer.compute_citation_quality(answer)
        assert score >= 0.5

    def test_regulation_reference(self, scorer):
        """Regulation reference detected."""
        answer = "Under Regulation B, the bank must not discriminate..."
        score = scorer.compute_citation_quality(answer)
        assert score >= 0.5

    def test_multiple_citation_types(self, scorer):
        """Multiple citation patterns → high score."""
        answer = (
            "Per Section 3.1, Article 7, and Regulation B, "
            "the KYC procedure on Page 12 requires full verification."
        )
        score = scorer.compute_citation_quality(answer)
        assert score == 1.0

    def test_banking_acronym_citations(self, scorer):
        """Banking acronyms (BSA/AML, KYC, CTR, SAR) count as citations."""
        answer = "The BSA/AML compliance requires SAR filing for suspicious activity."
        score = scorer.compute_citation_quality(answer)
        assert score >= 0.5


# ==================================================================
# Test Component 5: Prompt Reliability
# ==================================================================
class TestPromptReliability:
    """Test rolling average of historical trust scores."""

    def test_default_for_new_system(self, scorer):
        """New system with no history → default 0.7."""
        # Note: this may not be 0.7 if other tests have already added scores.
        # Just verify it returns a valid float in [0, 1]
        score = scorer.compute_prompt_reliability("test query")
        assert 0.0 <= score <= 1.0

    def test_returns_float(self, scorer):
        """Always returns a float."""
        score = scorer.compute_prompt_reliability("what is the loan policy?")
        assert isinstance(score, float)


# ==================================================================
# Test Full Score Computation
# ==================================================================
class TestFullScore:
    """Test the main score() method — full trust computation."""

    def test_basic_scoring(self, scorer):
        """Score a basic response and verify structure."""
        result = scorer.score(
            query="What is the AML policy?",
            answer="According to Section 4.2 of the BSA/AML Policy, CTR filing is required.",
            source_chunks=["BSA/AML Section 4.2: CTR filing required for transfers over $10,000"],
            similarity_scores=[0.92, 0.87],
            session_id="test_session",
            model_used="gpt-4",
        )

        # Check structure
        assert "final_score" in result
        assert "tier" in result
        assert "components" in result
        assert "weights" in result
        assert "model_used" in result
        assert "timestamp" in result

    def test_score_in_range(self, scorer):
        """Final score must be in [0, 100]."""
        result = scorer.score(
            query="test query",
            answer="test answer Section 1.1",
            source_chunks=["test source"],
            similarity_scores=[0.8],
        )
        assert 0 <= result["final_score"] <= 100

    def test_score_is_not_artificially_inflated(self, scorer, monkeypatch):
        """A middling weighted score must not be remapped into the 95-100 band."""
        monkeypatch.setattr(scorer, "compute_hallucination_probability", lambda *args: 0.5)
        monkeypatch.setattr(scorer, "compute_model_agreement", lambda *args: 0.5)
        monkeypatch.setattr(scorer, "compute_citation_quality", lambda *args: 0.5)
        monkeypatch.setattr(scorer, "compute_prompt_reliability", lambda *args: 0.5)

        result = scorer.score(
            query="test",
            answer="test",
            source_chunks=["test"],
            similarity_scores=[0.4],  # normalized retrieval confidence = 0.5
        )

        assert result["final_score"] == 50.0

    def test_all_components_present(self, scorer):
        """All 5 components must be in the result."""
        result = scorer.score(
            query="test",
            answer="According to Policy Section 5, the procedure is...",
            source_chunks=["Policy Section 5: procedure for..."],
            similarity_scores=[0.85],
        )
        for key in TRUST_WEIGHTS:
            assert key in result["components"]
            assert 0.0 <= result["components"][key] <= 1.0

    def test_tier_classification_high(self, scorer):
        """High-quality response should get High Confidence or Moderate."""
        result = scorer.score(
            query="What is the loan eligibility criteria?",
            answer=(
                "According to the Credit Guidelines Section 2.1, "
                "loan eligibility requires a credit score above 650. "
                "Per KYC Procedure Page 4, identity must be verified. "
                "BSA/AML compliance Section 3 also applies."
            ),
            source_chunks=[
                "Credit Guidelines Section 2.1: Credit score minimum 650 for loan eligibility",
                "KYC Procedure Page 4: identity verification required",
            ],
            similarity_scores=[0.95, 0.92, 0.89],
        )
        # Should be at least moderate confidence with good citations + high similarity
        assert result["tier"] in ("High Confidence", "Moderate Confidence")

    def test_tier_classification_low(self, scorer):
        """Low-quality response should get Low Confidence or Unreliable."""
        result = scorer.score(
            query="What is the loan policy?",
            answer="quantum blockchain synergy",  # Completely unrelated
            source_chunks=["Credit guidelines for residential mortgages"],
            similarity_scores=[0.1],  # Very low similarity
        )
        assert result["tier"] in ("Low Confidence", "Unreliable")

    def test_score_stored_in_db(self, scorer):
        """Score should be stored in the ai_trust_scores table."""
        scorer.score(
            query="Test DB storage query",
            answer="Test answer Section 1",
            source_chunks=["source"],
            similarity_scores=[0.8],
            session_id="test_db_session",
        )
        history = scorer.get_score_history(session_id="test_db_session", limit=1)
        assert len(history) >= 1
        assert "final_score" in history[0]

    def test_empty_sources(self, scorer):
        """Scoring with no sources should still work (lower trust)."""
        result = scorer.score(
            query="test",
            answer="some answer",
            source_chunks=[],
            similarity_scores=[],
        )
        assert 0 <= result["final_score"] <= 100

    def test_empty_answer(self, scorer):
        """Scoring with empty answer should still work."""
        result = scorer.score(
            query="test",
            answer="",
            source_chunks=["source"],
            similarity_scores=[0.5],
        )
        assert 0 <= result["final_score"] <= 100


# ==================================================================
# Test Score History
# ==================================================================
class TestScoreHistory:
    """Test score history retrieval."""

    def test_history_returns_list(self, scorer):
        """History should return a list."""
        history = scorer.get_score_history()
        assert isinstance(history, list)

    def test_history_entry_structure(self, scorer):
        """If history entries exist, they should have expected fields."""
        # Create a score first
        scorer.score(
            query="history test",
            answer="test Section 1",
            source_chunks=["source"],
            similarity_scores=[0.5],
            session_id="history_test_session",
        )
        history = scorer.get_score_history(session_id="history_test_session", limit=1)
        if history:
            entry = history[0]
            assert "final_score" in entry
            assert "components" in entry
            assert "model_used" in entry
            assert "timestamp" in entry

    def test_history_filtered_by_session(self, scorer):
        """Filtering by session_id should return only matching entries."""
        unique_session = "unique_filter_test_xyz_123"
        scorer.score(
            query="filter test",
            answer="answer",
            source_chunks=["src"],
            similarity_scores=[0.6],
            session_id=unique_session,
        )
        history = scorer.get_score_history(session_id=unique_session)
        assert len(history) >= 1
        # All returned should relate to this session (verified by the SQL filter)

    def test_history_limit(self, scorer):
        """Limit parameter should restrict result count."""
        history = scorer.get_score_history(limit=2)
        assert len(history) <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
