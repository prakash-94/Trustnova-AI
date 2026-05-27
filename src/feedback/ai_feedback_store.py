"""
AI Feedback Storage — Phase 8.

Expanded feedback table that stores full response context for every
banker approve/reject/edit action. This data powers the analyzer,
retrieval optimizer, and prompt optimizer modules.

Table: ai_feedback
  - session_id, response_id, feedback_type, prompt, response_text,
    model_used, trust_score, correction_text, retrieved_chunks (JSON),
    doc_type, prompt_template, timestamp
"""
import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")


class AIFeedbackStore:
    """
    Stores and retrieves AI response feedback with full context.

    Every feedback event captures the complete interaction context:
    the original prompt, the AI's response, which model was used,
    the trust score, the retrieved source chunks, and any banker corrections.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create ai_feedback table if it doesn't exist."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    prompt TEXT,
                    response_text TEXT,
                    model_used TEXT,
                    trust_score REAL DEFAULT 0,
                    correction_text TEXT,
                    retrieved_chunks TEXT,
                    doc_type TEXT,
                    prompt_template TEXT,
                    timestamp TEXT NOT NULL
                )
            """))
            conn.commit()

    def store(
        self,
        session_id: str,
        response_id: str,
        feedback_type: str,
        prompt: str = "",
        response_text: str = "",
        model_used: str = "",
        trust_score: float = 0.0,
        correction_text: str = "",
        retrieved_chunks: List[str] = None,
        doc_type: str = "",
        prompt_template: str = "general",
    ) -> Dict:
        """
        Store a feedback event with full context.

        Args:
            session_id: Session this feedback belongs to
            response_id: ID of the specific AI response
            feedback_type: 'approve', 'reject', or 'edit'
            prompt: The original user prompt
            response_text: The AI's response that was rated
            model_used: Which LLM generated the response
            trust_score: AI trust score at time of feedback
            correction_text: Banker's corrected version (for 'edit')
            retrieved_chunks: Source chunks used in RAG context
            doc_type: Document type(s) referenced
            prompt_template: Which prompt template was used

        Returns:
            Dict with stored feedback details
        """
        timestamp = datetime.now().isoformat()
        chunks_json = json.dumps(retrieved_chunks or [])

        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO ai_feedback
                (session_id, response_id, feedback_type, prompt, response_text,
                 model_used, trust_score, correction_text, retrieved_chunks,
                 doc_type, prompt_template, timestamp)
                VALUES (:sid, :rid, :ftype, :prompt, :resp, :model, :trust,
                        :correction, :chunks, :dtype, :template, :ts)
            """), {
                "sid": session_id,
                "rid": response_id,
                "ftype": feedback_type,
                "prompt": prompt[:2000],
                "resp": response_text[:5000],
                "model": model_used,
                "trust": trust_score,
                "correction": correction_text[:5000],
                "chunks": chunks_json,
                "dtype": doc_type,
                "template": prompt_template,
                "ts": timestamp,
            })
            conn.commit()

        return {
            "status": "stored",
            "session_id": session_id,
            "response_id": response_id,
            "feedback_type": feedback_type,
            "timestamp": timestamp,
        }

    def get_all_feedback(self, limit: int = 1000) -> pd.DataFrame:
        """Get all feedback records as a DataFrame."""
        return pd.read_sql(
            f"SELECT * FROM ai_feedback ORDER BY timestamp DESC LIMIT {limit}",
            self.engine,
        )

    def get_feedback_by_type(self, feedback_type: str, limit: int = 500) -> pd.DataFrame:
        """Get feedback filtered by type (approve/reject/edit)."""
        return pd.read_sql(
            text("SELECT * FROM ai_feedback WHERE feedback_type = :ft "
                 "ORDER BY timestamp DESC LIMIT :lim"),
            self.engine,
            params={"ft": feedback_type, "lim": limit},
        )

    def get_feedback_by_model(self, model: str) -> pd.DataFrame:
        """Get feedback filtered by model."""
        return pd.read_sql(
            text("SELECT * FROM ai_feedback WHERE model_used = :m ORDER BY timestamp DESC"),
            self.engine,
            params={"m": model},
        )

    def get_feedback_by_template(self, template: str) -> pd.DataFrame:
        """Get feedback filtered by prompt template."""
        return pd.read_sql(
            text("SELECT * FROM ai_feedback WHERE prompt_template = :t ORDER BY timestamp DESC"),
            self.engine,
            params={"t": template},
        )

    def get_rejection_count(self) -> int:
        """Get total number of rejected responses."""
        df = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM ai_feedback WHERE feedback_type = 'reject'",
            self.engine,
        )
        return int(df.iloc[0]["cnt"]) if not df.empty else 0

    def get_total_count(self) -> int:
        """Get total number of feedback records."""
        df = pd.read_sql("SELECT COUNT(*) as cnt FROM ai_feedback", self.engine)
        return int(df.iloc[0]["cnt"]) if not df.empty else 0

    def get_corrections(self, limit: int = 100) -> List[Dict]:
        """Get all edit corrections with their original prompts."""
        df = pd.read_sql(
            text("SELECT prompt, response_text, correction_text, model_used, "
                 "prompt_template, trust_score, timestamp "
                 "FROM ai_feedback WHERE feedback_type = 'edit' "
                 "AND correction_text != '' ORDER BY timestamp DESC LIMIT :lim"),
            self.engine,
            params={"lim": limit},
        )
        return df.to_dict(orient="records")
