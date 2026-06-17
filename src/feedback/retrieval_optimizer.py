"""
Retrieval Optimizer — Phase 8.

Tracks which retrieved chunks appeared in approved vs rejected responses.
Computes per-chunk quality scores and applies negative feedback weighting
to downrank chunks that consistently appear in rejected answers.

Tables:
  chunk_feedback — per-chunk feedback signals:
    chunk_hash, chunk_text, source, positive_count, negative_count, weight, updated_at

Workflow:
  1. On approve: increment positive_count for all chunks in that response
  2. On reject: increment negative_count for all chunks in that response
  3. On retrieval: multiply retrieval scores by chunk weight to re-rank
"""
import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from src.models.database import auto_pk
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")

# Weight bounds
MIN_WEIGHT = 0.3   # Never fully suppress a chunk
MAX_WEIGHT = 1.5   # Bonus for consistently approved chunks
DEFAULT_WEIGHT = 1.0


class RetrievalOptimizer:
    """
    Optimizes retrieval quality using banker feedback signals.

    Tracks which chunks appeared in approved vs rejected responses
    and adjusts retrieval weights accordingly. Chunks that frequently
    appear in rejected answers get downranked in future retrievals.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create chunk_feedback table if it doesn't exist."""
        with self.engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS chunk_feedback (
                    id {auto_pk},
                    chunk_hash TEXT UNIQUE NOT NULL,
                    chunk_text TEXT,
                    source TEXT,
                    positive_count INTEGER DEFAULT 0,
                    negative_count INTEGER DEFAULT 0,
                    weight REAL DEFAULT 1.0,
                    updated_at TEXT NOT NULL
                )
            """))
            conn.commit()

    # ==================================================================
    # Feedback Recording
    # ==================================================================

    def log_feedback_for_chunks(
        self,
        chunks: List[str],
        feedback_type: str,
        source: str = "",
    ) -> int:
        """
        Record feedback signal for all chunks in a response.

        Args:
            chunks: List of retrieved text chunks
            feedback_type: 'approve', 'reject', or 'edit'
            source: Source document reference

        Returns:
            Number of chunk records updated
        """
        if not chunks:
            return 0

        is_positive = feedback_type == "approve"
        updated = 0

        with self.engine.connect() as conn:
            for chunk_text in chunks:
                chunk_hash = self._hash_chunk(chunk_text)

                # Upsert: try update first, then insert
                existing = conn.execute(
                    text("SELECT id FROM chunk_feedback WHERE chunk_hash = :h"),
                    {"h": chunk_hash},
                ).fetchone()

                now = datetime.now().isoformat()

                if existing:
                    if is_positive:
                        conn.execute(text("""
                            UPDATE chunk_feedback
                            SET positive_count = positive_count + 1, updated_at = :now
                            WHERE chunk_hash = :h
                        """), {"h": chunk_hash, "now": now})
                    else:
                        conn.execute(text("""
                            UPDATE chunk_feedback
                            SET negative_count = negative_count + 1, updated_at = :now
                            WHERE chunk_hash = :h
                        """), {"h": chunk_hash, "now": now})
                else:
                    pos = 1 if is_positive else 0
                    neg = 0 if is_positive else 1
                    conn.execute(text("""
                        INSERT INTO chunk_feedback
                        (chunk_hash, chunk_text, source, positive_count,
                         negative_count, weight, updated_at)
                        VALUES (:h, :text, :src, :pos, :neg, :w, :now)
                    """), {
                        "h": chunk_hash,
                        "text": chunk_text[:2000],
                        "src": source,
                        "pos": pos,
                        "neg": neg,
                        "w": DEFAULT_WEIGHT,
                        "now": now,
                    })

                updated += 1

            conn.commit()

        # Recompute weights for affected chunks
        self._recompute_weights([self._hash_chunk(c) for c in chunks])

        return updated

    # ==================================================================
    # Weight Computation
    # ==================================================================

    def _recompute_weights(self, chunk_hashes: List[str] = None):
        """
        Recompute retrieval weights based on feedback signals.

        Weight formula:
          weight = base + (positive_rate - negative_rate) * adjustment
          where positive_rate = pos / (pos + neg), negative_rate = neg / (pos + neg)

        Clamped to [MIN_WEIGHT, MAX_WEIGHT].
        """
        with self.engine.connect() as conn:
            if chunk_hashes:
                placeholders = ",".join(f"'{h}'" for h in chunk_hashes)
                df = pd.read_sql(
                    f"SELECT chunk_hash, positive_count, negative_count "
                    f"FROM chunk_feedback WHERE chunk_hash IN ({placeholders})",
                    self.engine,
                )
            else:
                df = pd.read_sql(
                    "SELECT chunk_hash, positive_count, negative_count FROM chunk_feedback",
                    self.engine,
                )

            if df.empty:
                return

            now = datetime.now().isoformat()
            for _, row in df.iterrows():
                pos = int(row["positive_count"])
                neg = int(row["negative_count"])
                total = pos + neg

                if total == 0:
                    weight = DEFAULT_WEIGHT
                else:
                    # Net quality score: -1 (all negative) to +1 (all positive)
                    net_score = (pos - neg) / total
                    # Map to weight range
                    weight = DEFAULT_WEIGHT + net_score * 0.5

                weight = max(MIN_WEIGHT, min(MAX_WEIGHT, weight))

                conn.execute(text("""
                    UPDATE chunk_feedback SET weight = :w, updated_at = :now
                    WHERE chunk_hash = :h
                """), {"w": round(weight, 4), "h": row["chunk_hash"], "now": now})

            conn.commit()

    def recompute_all_weights(self):
        """Recompute weights for all chunks in the database."""
        self._recompute_weights()

    # ==================================================================
    # Retrieval Re-ranking
    # ==================================================================

    def apply_weights_to_retrieval(
        self,
        results: List[Dict],
        text_key: str = "text",
    ) -> List[Dict]:
        """
        Re-rank retrieval results using feedback-derived weights.

        Args:
            results: List of retrieval result dicts with text and score
            text_key: Key name for the text content in each result

        Returns:
            Re-ranked results with adjusted scores
        """
        if not results:
            return results

        # Get weights for all chunks
        weights = self.get_chunk_weights()

        for result in results:
            chunk_text = result.get(text_key, "")
            chunk_hash = self._hash_chunk(chunk_text)

            if chunk_hash in weights:
                weight = weights[chunk_hash]
                original_score = result.get("score", 1.0)
                result["original_score"] = original_score
                result["feedback_weight"] = weight
                result["adjusted_score"] = round(original_score * weight, 4)
            else:
                result["feedback_weight"] = DEFAULT_WEIGHT
                result["adjusted_score"] = result.get("score", 1.0)

        # Sort by adjusted score (descending)
        results.sort(key=lambda x: x.get("adjusted_score", 0), reverse=True)

        return results

    def get_chunk_weights(self) -> Dict[str, float]:
        """Get all chunk weights as a hash -> weight mapping."""
        df = pd.read_sql("SELECT chunk_hash, weight FROM chunk_feedback", self.engine)
        if df.empty:
            return {}
        return dict(zip(df["chunk_hash"], df["weight"]))

    # ==================================================================
    # Reporting
    # ==================================================================

    def get_downranked_chunks(self, threshold: float = 0.8) -> List[Dict]:
        """
        Get chunks that have been downranked below the given threshold.

        These are chunks that consistently appear in rejected responses.
        """
        df = pd.read_sql(
            text("SELECT chunk_hash, chunk_text, source, positive_count, "
                 "negative_count, weight, updated_at FROM chunk_feedback "
                 "WHERE weight < :threshold ORDER BY weight ASC"),
            self.engine,
            params={"threshold": threshold},
        )
        return df.to_dict(orient="records")

    def get_boosted_chunks(self, threshold: float = 1.2) -> List[Dict]:
        """Get chunks that have been boosted above the given threshold."""
        df = pd.read_sql(
            text("SELECT chunk_hash, chunk_text, source, positive_count, "
                 "negative_count, weight, updated_at FROM chunk_feedback "
                 "WHERE weight > :threshold ORDER BY weight DESC"),
            self.engine,
            params={"threshold": threshold},
        )
        return df.to_dict(orient="records")

    def get_health_report(self) -> Dict:
        """
        Get overall retrieval health report.

        Returns total chunks tracked, weight distribution, and flagged chunks.
        """
        df = pd.read_sql(
            "SELECT positive_count, negative_count, weight FROM chunk_feedback",
            self.engine,
        )

        if df.empty:
            return {
                "total_chunks_tracked": 0,
                "message": "No chunk feedback data yet",
            }

        return {
            "total_chunks_tracked": len(df),
            "total_positive_signals": int(df["positive_count"].sum()),
            "total_negative_signals": int(df["negative_count"].sum()),
            "avg_weight": round(float(df["weight"].mean()), 4),
            "min_weight": round(float(df["weight"].min()), 4),
            "max_weight": round(float(df["weight"].max()), 4),
            "downranked_count": int((df["weight"] < 0.8).sum()),
            "boosted_count": int((df["weight"] > 1.2).sum()),
            "neutral_count": int(((df["weight"] >= 0.8) & (df["weight"] <= 1.2)).sum()),
        }

    # ==================================================================
    # Helpers
    # ==================================================================

    def _hash_chunk(self, text: str) -> str:
        """Generate a stable hash for a chunk of text."""
        return hashlib.md5(text.strip().encode()).hexdigest()[:16]


# --- CLI ---
if __name__ == "__main__":
    optimizer = RetrievalOptimizer()

    print("=" * 60)
    print("Retrieval Optimizer - Health Report")
    print("=" * 60)

    report = optimizer.get_health_report()
    print(f"\nTotal chunks tracked: {report.get('total_chunks_tracked', 0)}")

    if report.get("total_chunks_tracked", 0) > 0:
        print(f"  Positive signals: {report['total_positive_signals']}")
        print(f"  Negative signals: {report['total_negative_signals']}")
        print(f"  Avg weight:       {report['avg_weight']}")
        print(f"  Downranked:       {report['downranked_count']}")
        print(f"  Boosted:          {report['boosted_count']}")
        print(f"  Neutral:          {report['neutral_count']}")

        downranked = optimizer.get_downranked_chunks()
        if downranked:
            print(f"\nDownranked chunks:")
            for c in downranked[:5]:
                print(f"  [{c['weight']:.2f}] {c['chunk_text'][:80]}...")
    else:
        print("No chunk feedback data yet.")
        print("Submit feedback through /feedback to start tracking retrieval quality.")

    print("=" * 60)
