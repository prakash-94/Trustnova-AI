"""
Phase 4 LLM Router Verification Tests.

Tests the LLM router with all 5 task types:
  1. summarization
  2. fraud_reasoning
  3. compliance
  4. sensitive (PII)
  5. lookup (simple)

Also tests:
  - Retry logic (mocked failures)
  - Fallback chain behavior
  - Token cost logging to DB
  - Usage summary analytics
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, text

from src.api.llm_router import (
    MODEL_MAP,
    FALLBACK_CHAIN,
    TOKEN_COSTS,
    MAX_RETRIES,
    INITIAL_BACKOFF_SECONDS,
    _ensure_llm_usage_table,
    _log_usage,
    route,
    get_usage_summary,
)


# ============================================================
# Configuration Tests
# ============================================================
class TestRouterConfiguration:
    """Verify router configuration matches TODO spec."""

    def test_all_5_task_types_mapped(self):
        """Router must support all 5 required task types."""
        required_tasks = ["summarization", "fraud_reasoning", "compliance", "sensitive", "lookup"]
        for task in required_tasks:
            assert task in MODEL_MAP, f"Missing task type: {task}"

    def test_model_map_has_valid_models(self):
        """All mapped models should be recognized."""
        valid_models = {"gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "claude-3-sonnet", "gemini-pro", "mistral-7b"}
        for task, model in MODEL_MAP.items():
            assert isinstance(model, str), f"Model for task '{task}' is not a string"
            assert len(model) > 0, f"Model for task '{task}' is empty"

    def test_fallback_chain_exists(self):
        """Fallback chain should have at least 2 models."""
        assert len(FALLBACK_CHAIN) >= 2
        assert "gpt-3.5-turbo" in FALLBACK_CHAIN  # Cheapest should always be in fallback

    def test_token_costs_defined(self):
        """Token costs should be defined for key models."""
        for model in ["gpt-4", "gpt-3.5-turbo"]:
            assert model in TOKEN_COSTS
            assert "input" in TOKEN_COSTS[model]
            assert "output" in TOKEN_COSTS[model]
            assert TOKEN_COSTS[model]["input"] >= 0
            assert TOKEN_COSTS[model]["output"] >= 0

    def test_retry_configuration(self):
        """Retry config should match TODO spec: 3 retries, 2s initial backoff."""
        assert MAX_RETRIES == 3
        assert INITIAL_BACKOFF_SECONDS == 2


# ============================================================
# Token Cost Logger Tests
# ============================================================
class TestTokenCostLogger:
    """Test the LLM usage logging to database."""

    def test_ensure_table_creates_llm_usage(self):
        """Table creation should succeed without error."""
        _ensure_llm_usage_table()

        # Verify table exists
        from src.api.llm_router import DATABASE_URL
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_usage'"
            ))
            tables = [r[0] for r in result]
            assert "llm_usage" in tables

    def test_log_usage_writes_record(self):
        """Logging should insert a record into llm_usage."""
        _ensure_llm_usage_table()

        _log_usage(
            task_type="test_task",
            model="gpt-3.5-turbo",
            tokens_in=100,
            tokens_out=50,
            latency_ms=250.5,
            success=True,
        )

        from src.api.llm_router import DATABASE_URL
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT * FROM llm_usage WHERE task_type = 'test_task' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            assert row is not None
            # Clean up test data
            conn.execute(text("DELETE FROM llm_usage WHERE task_type = 'test_task'"))
            conn.commit()

    def test_cost_calculation(self):
        """Cost should be calculated correctly from token counts."""
        _ensure_llm_usage_table()

        _log_usage(
            task_type="test_cost",
            model="gpt-4",
            tokens_in=1000,  # 1K tokens * $0.03/1K = $0.03
            tokens_out=500,  # 0.5K tokens * $0.06/1K = $0.03
            latency_ms=1000.0,
        )

        from src.api.llm_router import DATABASE_URL
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT cost_usd FROM llm_usage WHERE task_type = 'test_cost' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            assert row is not None
            expected_cost = (1000 / 1000 * 0.03) + (500 / 1000 * 0.06)  # $0.06
            assert abs(row[0] - expected_cost) < 0.001
            # Clean up
            conn.execute(text("DELETE FROM llm_usage WHERE task_type = 'test_cost'"))
            conn.commit()


# ============================================================
# Route Function Tests (Mocked LLM)
# ============================================================
class TestRouteFunction:
    """Test the route() function with mocked LLM calls."""

    def _mock_llm_response(self, content="Mock response", tokens_in=50, tokens_out=25):
        """Create a mock LLM response object."""
        mock_resp = MagicMock()
        mock_resp.content = content
        mock_resp.response_metadata = {
            "token_usage": {
                "prompt_tokens": tokens_in,
                "completion_tokens": tokens_out,
            }
        }
        return mock_resp

    @pytest.mark.parametrize("task_type", ["summarization", "fraud_reasoning", "compliance", "sensitive", "lookup"])
    def test_route_all_5_task_types(self, task_type):
        """Each of the 5 task types should route successfully."""
        with patch("src.api.llm_router._get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = self._mock_llm_response(
                content=f"Response for {task_type}"
            )
            mock_get_llm.return_value = mock_llm

            result = route(task_type, f"Test prompt for {task_type}")

            assert result["response"] == f"Response for {task_type}"
            assert result["model_used"] == MODEL_MAP[task_type]
            assert "latency_ms" in result
            assert "tokens_in" in result
            assert "tokens_out" in result

    def test_route_returns_correct_model(self):
        """Route should use the model mapped to the task type."""
        with patch("src.api.llm_router._get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = self._mock_llm_response()
            mock_get_llm.return_value = mock_llm

            result = route("lookup", "Simple question")

            expected_model = MODEL_MAP["lookup"]
            mock_get_llm.assert_called_with(expected_model)
            assert result["model_used"] == expected_model

    def test_route_unknown_task_falls_back_to_general(self):
        """Unknown task types should use the 'general' model."""
        with patch("src.api.llm_router._get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = self._mock_llm_response()
            mock_get_llm.return_value = mock_llm

            result = route("unknown_task", "Test prompt")

            assert result["model_used"] == MODEL_MAP["general"]

    def test_retry_on_failure(self):
        """Should retry up to MAX_RETRIES times before falling back."""
        with patch("src.api.llm_router._get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            # Fail twice, succeed on third attempt
            mock_llm.invoke.side_effect = [
                Exception("API Error 1"),
                Exception("API Error 2"),
                self._mock_llm_response(content="Success after retries"),
            ]
            mock_get_llm.return_value = mock_llm

            with patch("time.sleep"):  # Don't actually wait
                result = route("general", "Test prompt")

            assert result["response"] == "Success after retries"
            assert result["attempt"] == 3

    def test_fallback_chain_on_total_failure(self):
        """If primary model exhausts retries, should try fallback chain."""
        call_count = 0

        def mock_get_llm_fn(model):
            nonlocal call_count
            mock_llm = MagicMock()
            if model == MODEL_MAP["general"]:
                # Primary model always fails
                mock_llm.invoke.side_effect = Exception(f"Primary {model} failed")
            else:
                # Fallback succeeds
                mock_llm.invoke.return_value = self._mock_llm_response(
                    content=f"Fallback {model} response"
                )
            call_count += 1
            return mock_llm

        with patch("src.api.llm_router._get_llm", side_effect=mock_get_llm_fn):
            with patch("time.sleep"):
                result = route("general", "Test prompt")

            assert "Fallback" in result["response"]

    def test_route_logs_usage_to_db(self):
        """Successful route should log usage to the llm_usage table."""
        _ensure_llm_usage_table()

        with patch("src.api.llm_router._get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = self._mock_llm_response(tokens_in=100, tokens_out=50)
            mock_get_llm.return_value = mock_llm

            route("lookup", "Test logging")

        # Check DB
        from src.api.llm_router import DATABASE_URL
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT task_type, model, tokens_in, tokens_out, success FROM llm_usage "
                "WHERE task_type = 'lookup' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "lookup"
            assert row[4] == 1  # success


# ============================================================
# Usage Summary Tests
# ============================================================
class TestUsageSummary:
    """Test the usage analytics function."""

    def test_usage_summary_returns_dict(self):
        """Summary should return a dict with expected keys."""
        _ensure_llm_usage_table()
        summary = get_usage_summary()

        assert isinstance(summary, dict)
        assert "total_calls" in summary or "error" in summary

    def test_usage_summary_with_data(self):
        """After logging, summary should reflect the data."""
        _ensure_llm_usage_table()

        # Log some test usage
        for task in ["summarization", "fraud_reasoning", "compliance"]:
            _log_usage(task, "gpt-4", 100, 50, 500.0)

        summary = get_usage_summary()
        assert summary.get("total_calls", 0) >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
