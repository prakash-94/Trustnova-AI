"""
Phase 4 Session Memory Persistence Verification Tests.

Verifies that:
  1. Sessions persist in SQLite (not in-memory only)
  2. New SessionMemory instance reads data written by previous instance
  3. Feedback events are stored persistently
  4. Session history survives "restart" (new object creation)
  5. CRUD operations work correctly
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")


# ============================================================
# Session Memory CRUD Tests
# ============================================================
class TestSessionMemoryCRUD:
    """Test basic CRUD operations."""

    def _fresh_memory(self):
        """Create a fresh SessionMemory instance (simulates restart)."""
        from src.api.memory import SessionMemory
        return SessionMemory(db_url=DATABASE_URL)

    def test_create_session(self):
        """Creating a session should return a valid session ID."""
        mem = self._fresh_memory()
        sid = mem.create_session(banker_id="test_banker", customer_id="test_cust")

        assert isinstance(sid, str)
        assert len(sid) > 0

        # Cleanup
        mem.delete_session(sid)

    def test_append_and_retrieve(self):
        """Messages appended should be retrievable."""
        mem = self._fresh_memory()
        sid = mem.create_session(banker_id="test_banker")

        mem.append_to_session(sid, "user", "Hello, what is the AML policy?")
        mem.append_to_session(sid, "assistant", "According to Section 4.1...", model_used="gpt-4")
        mem.append_to_session(sid, "user", "What about international transfers?")

        history = mem.get_session_history(sid)
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello, what is the AML policy?"
        assert history[1]["role"] == "assistant"
        assert history[1]["model_used"] == "gpt-4"
        assert history[2]["role"] == "user"

        # Cleanup
        mem.delete_session(sid)

    def test_last_n_history(self):
        """Should return only the last N messages when specified."""
        mem = self._fresh_memory()
        sid = mem.create_session(banker_id="test_banker")

        for i in range(10):
            mem.append_to_session(sid, "user", f"Message {i}")

        last_3 = mem.get_session_history(sid, last_n=3)
        assert len(last_3) == 3
        assert last_3[0]["content"] == "Message 7"
        assert last_3[2]["content"] == "Message 9"

        # Cleanup
        mem.delete_session(sid)

    def test_store_feedback(self):
        """Feedback events should be stored in session history."""
        mem = self._fresh_memory()
        sid = mem.create_session(banker_id="test_banker")

        mem.append_to_session(sid, "user", "What is the CTR threshold?")
        mem.append_to_session(sid, "assistant", "The threshold is $5,000.", model_used="gpt-4")

        feedback = mem.store_feedback(
            session_id=sid,
            response_id="resp_001",
            feedback_type="reject",
            prompt="What is the CTR threshold?",
            model_used="gpt-4",
            trust_score=72.5,
            correction_text="The correct threshold is $10,000, not $5,000.",
        )

        assert feedback["role"] == "feedback"
        assert feedback["feedback_type"] == "reject"
        assert feedback["correction_text"] == "The correct threshold is $10,000, not $5,000."

        # Verify it's in the history
        history = mem.get_session_history(sid)
        assert len(history) == 3  # user + assistant + feedback
        assert history[2]["role"] == "feedback"

        # Cleanup
        mem.delete_session(sid)

    def test_list_sessions(self):
        """Should list sessions filtered by banker."""
        mem = self._fresh_memory()
        sid1 = mem.create_session(banker_id="banker_A")
        sid2 = mem.create_session(banker_id="banker_A")
        sid3 = mem.create_session(banker_id="banker_B")

        sessions_a = mem.list_sessions(banker_id="banker_A")
        sessions_b = mem.list_sessions(banker_id="banker_B")

        assert len(sessions_a) >= 2
        assert len(sessions_b) >= 1

        # Cleanup
        for sid in [sid1, sid2, sid3]:
            mem.delete_session(sid)

    def test_delete_session(self):
        """Deleted sessions should not be retrievable."""
        mem = self._fresh_memory()
        sid = mem.create_session(banker_id="test_delete")
        mem.append_to_session(sid, "user", "Test message")

        deleted = mem.delete_session(sid)
        assert deleted is True

        history = mem.get_session_history(sid)
        assert history == []

    def test_get_session_info(self):
        """Session info should return metadata about the session."""
        mem = self._fresh_memory()
        sid = mem.create_session(banker_id="info_test", customer_id="cust_xyz")

        mem.append_to_session(sid, "user", "Hello")
        mem.append_to_session(sid, "assistant", "Hi there")

        info = mem.get_session_info(sid)
        assert info is not None
        assert info["session_id"] == sid
        assert "created_at" in info
        assert "updated_at" in info

        # Cleanup
        mem.delete_session(sid)


# ============================================================
# Persistence Across Restarts (Key Verification)
# ============================================================
class TestMemoryPersistence:
    """
    Verify that session memory persists across API restarts.

    This is the critical Phase 4 deliverable test: data written by one
    SessionMemory instance must be readable by a completely new instance.
    """

    def test_persistence_across_instances(self):
        """
        Data written by Instance 1 must survive and be readable by Instance 2.
        This simulates an API restart.
        """
        from src.api.memory import SessionMemory

        # === Instance 1: Write data ===
        mem1 = SessionMemory(db_url=DATABASE_URL)
        sid = mem1.create_session(
            banker_id="persist_test_banker",
            customer_id="persist_test_customer",
            session_id="persist_test_session_001",
        )
        mem1.append_to_session(sid, "user", "What is the AML reporting threshold?")
        mem1.append_to_session(
            sid, "assistant",
            "According to BSA/AML Section 4.1, the CTR filing threshold is $10,000.",
            model_used="gpt-4",
        )
        mem1.store_feedback(
            session_id=sid,
            response_id="resp_persist_001",
            feedback_type="approve",
            prompt="What is the AML reporting threshold?",
            model_used="gpt-4",
            trust_score=95.0,
        )

        # Verify Instance 1 can read its own data
        history_1 = mem1.get_session_history(sid)
        assert len(history_1) == 3

        # === Destroy Instance 1 (simulate restart) ===
        del mem1

        # === Instance 2: Read data written by Instance 1 ===
        mem2 = SessionMemory(db_url=DATABASE_URL)
        history_2 = mem2.get_session_history(sid)

        # Must have all 3 messages
        assert len(history_2) == 3, f"Expected 3 messages, got {len(history_2)}"

        # Verify content integrity
        assert history_2[0]["role"] == "user"
        assert history_2[0]["content"] == "What is the AML reporting threshold?"

        assert history_2[1]["role"] == "assistant"
        assert "CTR filing threshold" in history_2[1]["content"]
        assert history_2[1]["model_used"] == "gpt-4"

        assert history_2[2]["role"] == "feedback"
        assert history_2[2]["feedback_type"] == "approve"
        assert history_2[2]["trust_score"] == 95.0

        # Cleanup
        mem2.delete_session(sid)

    def test_module_singleton_persistence(self):
        """
        The get_memory() singleton should return consistent data.
        """
        from src.api.memory import get_memory

        mem = get_memory()
        sid = mem.create_session(
            banker_id="singleton_test",
            session_id="singleton_session_001",
        )
        mem.append_to_session(sid, "user", "Singleton test message")

        # Get a "fresh" reference via the module function
        mem_again = get_memory()
        history = mem_again.get_session_history(sid)

        assert len(history) >= 1
        assert history[-1]["content"] == "Singleton test message"

        # Cleanup
        mem.delete_session(sid)

    def test_concurrent_sessions_isolated(self):
        """Multiple sessions should not leak data between each other."""
        from src.api.memory import SessionMemory

        mem = SessionMemory(db_url=DATABASE_URL)
        sid_a = mem.create_session(banker_id="banker_A", session_id="isolation_a")
        sid_b = mem.create_session(banker_id="banker_B", session_id="isolation_b")

        mem.append_to_session(sid_a, "user", "Message for session A only")
        mem.append_to_session(sid_b, "user", "Message for session B only")

        history_a = mem.get_session_history(sid_a)
        history_b = mem.get_session_history(sid_b)

        assert len(history_a) == 1
        assert len(history_b) == 1
        assert history_a[0]["content"] == "Message for session A only"
        assert history_b[0]["content"] == "Message for session B only"

        # Cleanup
        mem.delete_session(sid_a)
        mem.delete_session(sid_b)

    def test_data_in_sqlite_not_memory(self):
        """
        Verify data is stored in the actual SQLite file, not just in RAM.
        Read directly from the DB to confirm.
        """
        from src.api.memory import SessionMemory

        mem = SessionMemory(db_url=DATABASE_URL)
        sid = mem.create_session(
            banker_id="raw_db_test",
            session_id="raw_db_session_001",
        )
        mem.append_to_session(sid, "user", "Direct DB verification test")

        # Read directly from SQLite, bypassing the SessionMemory class
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT messages FROM sessions WHERE session_id = :sid"
            ), {"sid": sid})
            row = result.fetchone()

        assert row is not None, "Session not found in raw DB query"
        messages = json.loads(row[0])
        assert len(messages) >= 1
        assert messages[-1]["content"] == "Direct DB verification test"

        # Cleanup
        mem.delete_session(sid)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
