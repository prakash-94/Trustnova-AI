"""
Session Memory System for the Banking AI Copilot.

Provides DB-backed conversation memory that persists across API restarts.
Stores full conversation history per banker session with metadata.

Table schema:
  sessions: session_id, banker_id, customer_id, messages (JSON),
            model_used, created_at, updated_at
"""
import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import create_engine, text
from src.models.database import auto_pk
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")


class SessionMemory:
    """
    DB-backed session memory for the Banking AI Copilot.

    Each session stores:
    - session_id: Unique session identifier
    - banker_id: The banker using the copilot
    - customer_id: The customer being discussed (optional)
    - messages: JSON array of conversation turns [{role, content, timestamp, model_used}]
    - model_used: Last model used in the session
    - created_at / updated_at: Timestamps
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_sessions_table()

    def _ensure_sessions_table(self):
        """Create the sessions table if it doesn't exist."""
        with self.engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS sessions (
                    id {auto_pk},
                    session_id TEXT UNIQUE NOT NULL,
                    banker_id TEXT NOT NULL DEFAULT 'default',
                    customer_id TEXT,
                    messages TEXT NOT NULL DEFAULT '[]',
                    model_used TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """))
            conn.commit()

    def create_session(
        self,
        banker_id: str = "default",
        customer_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Create a new session and return its ID.

        Args:
            banker_id: The banker's identifier
            customer_id: Optional customer being discussed
            session_id: Optional pre-defined session ID

        Returns:
            The session_id string
        """
        sid = session_id or str(uuid4())[:8]
        now = datetime.now().isoformat()

        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT OR IGNORE INTO sessions 
                (session_id, banker_id, customer_id, messages, created_at, updated_at)
                VALUES (:sid, :bid, :cid, '[]', :now, :now)
            """), {
                "sid": sid,
                "bid": banker_id,
                "cid": customer_id or "",
                "now": now,
            })
            conn.commit()

        return sid

    def get_session_history(
        self,
        session_id: str,
        last_n: Optional[int] = None,
    ) -> List[Dict]:
        """
        Retrieve conversation history for a session.

        Args:
            session_id: The session identifier
            last_n: If specified, return only the last N messages

        Returns:
            List of message dicts [{role, content, timestamp, model_used}]
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT messages FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
            row = result.fetchone()

        if not row:
            return []

        messages = json.loads(row[0])

        if last_n is not None:
            messages = messages[-last_n:]

        return messages

    def append_to_session(
        self,
        session_id: str,
        role: str,
        content: str,
        model_used: Optional[str] = None,
    ) -> Dict:
        """
        Append a message to a session's conversation history.

        Args:
            session_id: The session identifier
            role: "user" or "assistant"
            content: The message content
            model_used: The LLM model that generated the response (for assistant messages)

        Returns:
            The appended message dict
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if model_used:
            message["model_used"] = model_used

        # Retrieve existing messages
        messages = self.get_session_history(session_id)
        messages.append(message)

        now = datetime.now().isoformat()

        with self.engine.connect() as conn:
            # Check if session exists
            result = conn.execute(
                text("SELECT session_id FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )

            if result.fetchone():
                # Update existing session
                conn.execute(text("""
                    UPDATE sessions 
                    SET messages = :msgs, model_used = :model, updated_at = :now
                    WHERE session_id = :sid
                """), {
                    "msgs": json.dumps(messages),
                    "model": model_used or "",
                    "now": now,
                    "sid": session_id,
                })
            else:
                # Create new session on the fly
                conn.execute(text("""
                    INSERT INTO sessions 
                    (session_id, banker_id, messages, model_used, created_at, updated_at)
                    VALUES (:sid, 'default', :msgs, :model, :now, :now)
                """), {
                    "sid": session_id,
                    "msgs": json.dumps(messages),
                    "model": model_used or "",
                    "now": now,
                })

            conn.commit()

        return message

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get metadata about a session."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT session_id, banker_id, customer_id, messages,
                           model_used, created_at, updated_at
                    FROM sessions WHERE session_id = :sid
                """),
                {"sid": session_id},
            )
            row = result.fetchone()

        if not row:
            return None

        messages = json.loads(row[3])  # messages is now column index 3
        return {
            "session_id": row[0],
            "banker_id": row[1],
            "customer_id": row[2] if row[2] else None,
            "message_count": len(messages),
            "model_used": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def list_sessions(
        self,
        banker_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """List recent sessions, optionally filtered by banker."""
        with self.engine.connect() as conn:
            if banker_id:
                result = conn.execute(
                    text("""
                        SELECT session_id, banker_id, customer_id, 
                               model_used, created_at, updated_at
                        FROM sessions 
                        WHERE banker_id = :bid
                        ORDER BY updated_at DESC 
                        LIMIT :limit
                    """),
                    {"bid": banker_id, "limit": limit},
                )
            else:
                result = conn.execute(
                    text("""
                        SELECT session_id, banker_id, customer_id,
                               model_used, created_at, updated_at
                        FROM sessions 
                        ORDER BY updated_at DESC 
                        LIMIT :limit
                    """),
                    {"limit": limit},
                )

            rows = result.fetchall()

        return [
            {
                "session_id": r[0],
                "banker_id": r[1],
                "customer_id": r[2],
                "model_used": r[3],
                "created_at": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its history."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
            conn.commit()
            return result.rowcount > 0

    def store_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_type: str,
        prompt: str = "",
        model_used: str = "",
        trust_score: float = 0.0,
        correction_text: str = "",
    ) -> Dict:
        """
        Store feedback event in session memory.

        Args:
            session_id: The session this feedback belongs to
            response_id: ID of the specific response being rated
            feedback_type: "approve", "reject", or "edit"
            prompt: The original prompt
            model_used: The model that generated the response
            trust_score: The AI trust score of the response
            correction_text: Banker's corrected text (for "edit" type)

        Returns:
            Dict with feedback details
        """
        feedback_msg = {
            "role": "feedback",
            "feedback_type": feedback_type,
            "response_id": response_id,
            "prompt": prompt[:500],  # Truncate for storage
            "model_used": model_used,
            "trust_score": trust_score,
            "correction_text": correction_text,
            "timestamp": datetime.now().isoformat(),
        }

        messages = self.get_session_history(session_id)
        messages.append(feedback_msg)

        with self.engine.connect() as conn:
            conn.execute(text("""
                UPDATE sessions 
                SET messages = :msgs, updated_at = :now
                WHERE session_id = :sid
            """), {
                "msgs": json.dumps(messages),
                "now": datetime.now().isoformat(),
                "sid": session_id,
            })
            conn.commit()

        return feedback_msg


# Module-level singleton for convenience
_memory_instance = None


def get_memory() -> SessionMemory:
    """Get or create the global SessionMemory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = SessionMemory()
    return _memory_instance


# --- CLI ---
if __name__ == "__main__":
    mem = SessionMemory()

    print("Session Memory — Quick Test")
    print("=" * 50)

    # Create session
    sid = mem.create_session(banker_id="banker_001", customer_id="cust_123")
    print(f"Created session: {sid}")

    # Add messages
    mem.append_to_session(sid, "user", "What is the AML policy for wire transfers?")
    mem.append_to_session(
        sid, "assistant",
        "According to AML Policy Section 4.2, wire transfers exceeding $10,000 require CTR filing.",
        model_used="gpt-4",
    )
    mem.append_to_session(sid, "user", "What about international transfers?")

    # Retrieve
    history = mem.get_session_history(sid)
    print(f"\nSession has {len(history)} messages:")
    for msg in history:
        print(f"  [{msg['role']}] {msg['content'][:60]}...")

    # List sessions
    sessions = mem.list_sessions()
    print(f"\nTotal sessions: {len(sessions)}")

    print("\nDone!")
