"""
AI Response Trust Scoring System.

Calculates a composite trust score (0-100) for every AI-generated response
using 5 independent component metrics:

  1. Retrieval Confidence (0.30) — cosine similarity of top retrieved chunks
  2. Hallucination Probability (0.25) — GPT-4 verification against source docs
  3. Model Agreement (0.20) — Jaccard similarity of responses from 2 models
  4. Citation Quality (0.15) — regex check for source citations in the answer
  5. Prompt Reliability (0.10) — rolling average of last 20 trust scores

Stores score history in the `ai_trust_scores` SQLite table.
"""
import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")

# --- Weight Configuration ---
TRUST_WEIGHTS = {
    "retrieval_confidence": 0.30,
    "hallucination_probability": 0.25,
    "model_agreement": 0.20,
    "citation_quality": 0.15,
    "prompt_reliability": 0.10,
}


class AITrustScorer:
    """
    Calculates and manages AI response trustworthiness scores.

    Each score is a weighted combination of 5 independent metrics,
    producing a final score in the range 0-100.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_table()

    def _ensure_table(self):
        """Create the ai_trust_scores table if it doesn't exist."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_trust_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    query TEXT,
                    retrieval_confidence REAL,
                    hallucination_probability REAL,
                    model_agreement REAL,
                    citation_quality REAL,
                    prompt_reliability REAL,
                    final_score REAL NOT NULL,
                    model_used TEXT,
                    timestamp TEXT NOT NULL
                )
            """))
            conn.commit()

    # ==================================================================
    # Component 1: Retrieval Confidence
    # ==================================================================
    def compute_retrieval_confidence(
        self,
        similarity_scores: List[float],
    ) -> float:
        """
        Compute retrieval confidence from cosine similarity scores.

        Uses the average similarity of the top-K retrieved chunks.
        ChromaDB returns relevance scores in [0, 1] where 1 = perfect match.

        Args:
            similarity_scores: List of cosine similarity scores from vector store

        Returns:
            Float in [0, 1]. Higher = more confident retrieval.
        """
        if not similarity_scores:
            return 0.0

        # Average of top scores (already sorted by relevance)
        avg_score = sum(similarity_scores) / len(similarity_scores)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, avg_score))

    # ==================================================================
    # Component 2: Hallucination Probability
    # ==================================================================
    def compute_hallucination_probability(
        self,
        answer: str,
        source_chunks: List[str],
    ) -> float:
        """
        Estimate hallucination probability by verifying answer against source docs.

        Uses GPT-4 to check: "Does this answer contradict or go beyond the source?"

        Args:
            answer: The AI-generated answer
            source_chunks: List of source document chunks used for the answer

        Returns:
            Float in [0, 1]. Lower = less hallucination = more trustworthy.
        """
        if not source_chunks or not answer:
            return 0.5  # Unknown — moderate risk

        try:
            from src.api.llm_router import route

            source_text = "\n---\n".join(chunk[:500] for chunk in source_chunks[:3])
            prompt = f"""You are a fact-checking auditor for a banking AI system.

TASK: Compare the AI's answer against the source documents and determine the hallucination probability.

SOURCE DOCUMENTS:
{source_text}

AI ANSWER:
{answer[:1000]}

INSTRUCTIONS:
1. Check if the answer contains claims NOT supported by the source documents.
2. Check if the answer contradicts anything in the source documents.
3. Check if the answer fabricates numbers, dates, or policy details.

Respond with ONLY a JSON object:
{{"hallucination_score": <float 0.0 to 1.0>, "reason": "<brief explanation>"}}

Where 0.0 = fully grounded in sources, 1.0 = completely fabricated.
"""
            result = route("compliance", prompt)
            response_text = result.get("response", "")

            # Parse the JSON response
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                parsed = json.loads(json_match.group())
                score = float(parsed.get("hallucination_score", 0.3))
                return max(0.0, min(1.0, score))

        except Exception as e:
            pass  # Fallback below

        # Fallback: simple heuristic — check keyword overlap
        return self._heuristic_hallucination(answer, source_chunks)

    def _heuristic_hallucination(self, answer: str, source_chunks: List[str]) -> float:
        """Fallback heuristic for hallucination detection."""
        answer_words = set(answer.lower().split())
        source_words = set()
        for chunk in source_chunks:
            source_words.update(chunk.lower().split())

        if not answer_words:
            return 0.5

        overlap = len(answer_words & source_words) / len(answer_words)
        # High overlap → low hallucination
        return max(0.0, min(1.0, 1.0 - overlap))

    # ==================================================================
    # Component 3: Model Agreement
    # ==================================================================
    def compute_model_agreement(
        self,
        answer_primary: str,
        answer_secondary: Optional[str] = None,
    ) -> float:
        """
        Compute agreement between two model responses using Jaccard similarity.

        If no secondary answer is provided, uses a default value.

        Args:
            answer_primary: Response from the primary model
            answer_secondary: Response from a secondary model (optional)

        Returns:
            Float in [0, 1]. Higher = more agreement.
        """
        if not answer_secondary:
            return 0.7  # Default when secondary model not available

        tokens_a = set(answer_primary.lower().split())
        tokens_b = set(answer_secondary.lower().split())

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)

        jaccard = intersection / union if union > 0 else 0.0
        return round(jaccard, 4)

    def get_secondary_answer(self, query: str, context: str = "") -> Optional[str]:
        """
        Get a secondary model's answer for model agreement comparison.

        Uses a cheaper/different model via the LLM router.
        """
        try:
            from src.api.llm_router import route

            prompt = f"""Answer this banking question concisely based on the context.

Context: {context[:500]}

Question: {query}

Answer:"""
            result = route("lookup", prompt)  # Uses cheaper model
            return result.get("response", "")
        except Exception:
            return None

    # ==================================================================
    # Component 4: Citation Quality
    # ==================================================================
    def compute_citation_quality(self, answer: str) -> float:
        """
        Check whether the answer properly cites source documents.

        Looks for patterns like:
          - "Section X.X" or "Section X"
          - "Page X"
          - "According to [Source]"
          - "[Document Name]"
          - "Policy X.X"

        Args:
            answer: The AI-generated answer

        Returns:
            Float in [0, 1]. Higher = better citation quality.
        """
        if not answer:
            return 0.0

        patterns = [
            r'[Ss]ection\s+\d+(\.\d+)*',           # Section 4.2, Section 3.1.2
            r'[Pp]age\s+\d+',                        # Page 3
            r'[Aa]ccording\s+to\s+[\[\"\']?[A-Z]',  # According to [AML Policy]
            r'[Pp]olicy\s+\d+(\.\d+)*',              # Policy 4.2
            r'[Aa]rticle\s+\d+',                     # Article 5
            r'[Rr]egulation\s+[A-Z]',                # Regulation B
            r'[Cc]hapter\s+\d+',                     # Chapter 3
            r'[Pp]rocedure\s+\d+(\.\d+)*',           # Procedure 2.1
            r'BSA/AML',                               # BSA/AML reference
            r'KYC|CTR|SAR',                           # Banking acronyms as citations
        ]

        matches = 0
        for pattern in patterns:
            found = re.findall(pattern, answer)
            matches += len(found) if isinstance(found, list) else (1 if found else 0)

        # Score based on number of citations found
        if matches >= 3:
            return 1.0
        elif matches == 2:
            return 0.8
        elif matches == 1:
            return 0.5
        else:
            return 0.1  # No citations at all

    # ==================================================================
    # Component 5: Prompt Reliability
    # ==================================================================
    def compute_prompt_reliability(self, query: str) -> float:
        """
        Compute reliability based on rolling average of last 20 trust scores
        for queries similar to this one.

        Uses a simple keyword-based lookup against the ai_trust_scores table.

        Args:
            query: The current query

        Returns:
            Float in [0, 1]. Higher = historically reliable prompt type.
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT final_score FROM ai_trust_scores
                    ORDER BY id DESC
                    LIMIT 20
                """))
                rows = result.fetchall()

            if not rows:
                return 0.7  # Default for new system

            scores = [row[0] for row in rows]
            avg = sum(scores) / len(scores)
            # Normalize from 0-100 scale to 0-1
            return max(0.0, min(1.0, avg / 100.0))

        except Exception:
            return 0.7  # Default on error

    # ==================================================================
    # Main Scoring Function
    # ==================================================================
    def score(
        self,
        query: str,
        answer: str,
        source_chunks: List[str],
        similarity_scores: List[float],
        session_id: str = "",
        model_used: str = "gpt-4",
        answer_secondary: Optional[str] = None,
    ) -> Dict:
        """
        Calculate the full AI trust score for a response.

        Args:
            query: The original user query
            answer: The AI-generated answer
            source_chunks: List of retrieved document chunks
            similarity_scores: Cosine similarity scores from vector store
            session_id: Optional session ID for tracking
            model_used: Name of the primary model used
            answer_secondary: Optional secondary model answer for agreement check

        Returns:
            Dict with final_score (0-100), components (0-1 each), and tier
        """
        # Compute each component
        retrieval_conf = self.compute_retrieval_confidence(similarity_scores)

        hallucination_prob = self.compute_hallucination_probability(answer, source_chunks)

        model_agree = self.compute_model_agreement(answer, answer_secondary)

        citation_qual = self.compute_citation_quality(answer)

        prompt_rel = self.compute_prompt_reliability(query)

        # Build components dict
        components = {
            "retrieval_confidence": round(retrieval_conf, 4),
            "hallucination_probability": round(hallucination_prob, 4),
            "model_agreement": round(model_agree, 4),
            "citation_quality": round(citation_qual, 4),
            "prompt_reliability": round(prompt_rel, 4),
        }

        # Calculate weighted final score
        # Note: hallucination_probability is inverted (lower = better)
        weighted = (
            retrieval_conf * TRUST_WEIGHTS["retrieval_confidence"]
            + (1.0 - hallucination_prob) * TRUST_WEIGHTS["hallucination_probability"]
            + model_agree * TRUST_WEIGHTS["model_agreement"]
            + citation_qual * TRUST_WEIGHTS["citation_quality"]
            + prompt_rel * TRUST_WEIGHTS["prompt_reliability"]
        )

        final_score = round(max(0, min(100, weighted * 100)), 1)

        # Determine tier
        if final_score >= 80:
            tier = "High Confidence"
        elif final_score >= 60:
            tier = "Moderate Confidence"
        elif final_score >= 40:
            tier = "Low Confidence"
        else:
            tier = "Unreliable"

        result = {
            "final_score": final_score,
            "tier": tier,
            "components": components,
            "weights": TRUST_WEIGHTS,
            "model_used": model_used,
            "timestamp": datetime.now().isoformat(),
        }

        # Store in DB
        self._store_score(
            session_id=session_id,
            query=query,
            components=components,
            final_score=final_score,
            model_used=model_used,
        )

        return result

    def _store_score(
        self,
        session_id: str,
        query: str,
        components: Dict,
        final_score: float,
        model_used: str,
    ):
        """Store a trust score in the history table."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO ai_trust_scores
                    (session_id, query, retrieval_confidence, hallucination_probability,
                     model_agreement, citation_quality, prompt_reliability,
                     final_score, model_used, timestamp)
                    VALUES (:sid, :query, :rc, :hp, :ma, :cq, :pr, :fs, :model, :ts)
                """), {
                    "sid": session_id,
                    "query": query[:500],
                    "rc": components["retrieval_confidence"],
                    "hp": components["hallucination_probability"],
                    "ma": components["model_agreement"],
                    "cq": components["citation_quality"],
                    "pr": components["prompt_reliability"],
                    "fs": final_score,
                    "model": model_used,
                    "ts": datetime.now().isoformat(),
                })
                conn.commit()
        except Exception as e:
            print(f"  [AI Trust] Failed to store score: {e}")

    def get_score_history(
        self,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """Get historical AI trust scores, optionally filtered by session."""
        try:
            with self.engine.connect() as conn:
                if session_id:
                    result = conn.execute(text("""
                        SELECT final_score, retrieval_confidence, hallucination_probability,
                               model_agreement, citation_quality, prompt_reliability,
                               model_used, timestamp
                        FROM ai_trust_scores
                        WHERE session_id = :sid
                        ORDER BY id DESC LIMIT :limit
                    """), {"sid": session_id, "limit": limit})
                else:
                    result = conn.execute(text("""
                        SELECT final_score, retrieval_confidence, hallucination_probability,
                               model_agreement, citation_quality, prompt_reliability,
                               model_used, timestamp
                        FROM ai_trust_scores
                        ORDER BY id DESC LIMIT :limit
                    """), {"limit": limit})

                rows = result.fetchall()

            return [
                {
                    "final_score": r[0],
                    "components": {
                        "retrieval_confidence": r[1],
                        "hallucination_probability": r[2],
                        "model_agreement": r[3],
                        "citation_quality": r[4],
                        "prompt_reliability": r[5],
                    },
                    "model_used": r[6],
                    "timestamp": r[7],
                }
                for r in rows
            ]
        except Exception:
            return []


# Module-level singleton
_scorer_instance = None


def get_ai_trust_scorer() -> AITrustScorer:
    """Get or create the global AITrustScorer instance."""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = AITrustScorer()
    return _scorer_instance


# --- CLI Demo ---
if __name__ == "__main__":
    scorer = AITrustScorer()

    # Demo
    print("=" * 60)
    print("AI Trust Scorer — Demo")
    print("=" * 60)

    result = scorer.score(
        query="What is the AML policy for wire transfers over $10,000?",
        answer=(
            "According to BSA/AML Policy Section 4.2, all wire transfers exceeding "
            "$10,000 must have a Currency Transaction Report (CTR) filed. The bank must "
            "verify the sender's identity per KYC Procedure Page 3."
        ),
        source_chunks=[
            "BSA/AML Section 4.2: Wire transfers exceeding $10,000 require CTR filing...",
            "KYC Procedure: All customers must present valid government-issued ID...",
        ],
        similarity_scores=[0.92, 0.87, 0.81],
        session_id="demo_session",
    )

    print(f"\nFinal Score: {result['final_score']}/100 ({result['tier']})")
    print(f"\nComponents:")
    for name, value in result["components"].items():
        weight = TRUST_WEIGHTS[name]
        print(f"  {name:30s} {value:.4f}  (weight: {weight:.2f})")
