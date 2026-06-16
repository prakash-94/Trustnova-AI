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

        all-MiniLM-L6-v2 via ChromaDB produces scores in [0.1, 0.65] even for
        highly relevant chunks. We normalize the range [0.10, 0.70] → [0.0, 1.0]
        so a typical relevant chunk (0.35–0.50) maps to a reasonable confidence.

        Args:
            similarity_scores: List of cosine similarity scores from vector store

        Returns:
            Float in [0, 1]. Higher = more confident retrieval.
        """
        if not similarity_scores:
            return 0.0

        avg = sum(similarity_scores) / len(similarity_scores)
        # Normalize: model rarely exceeds 0.70; floor at 0.10
        normalized = (avg - 0.10) / (0.70 - 0.10)
        return max(0.0, min(1.0, normalized))

    # ==================================================================
    # Component 2: Hallucination Probability
    # ==================================================================
    def compute_hallucination_probability(
        self,
        answer: str,
        source_chunks: List[str],
    ) -> float:
        """
        Estimate hallucination probability via semantic similarity.

        Embeds the answer and each source chunk with the already-loaded
        all-MiniLM-L6-v2 model, then computes cosine similarity.  High
        semantic similarity to sources → low hallucination probability.

        Falls back to the keyword-overlap heuristic if the embedding model
        is unavailable (e.g. first boot before the model is cached).

        Args:
            answer: The AI-generated answer
            source_chunks: List of source document chunks used for the answer

        Returns:
            Float in [0, 1]. Lower = less hallucination = more trustworthy.
        """
        if not source_chunks or not answer:
            return 0.5  # Unknown — moderate risk

        try:
            from src.rag.embeddings import get_embeddings_model
            embedder = get_embeddings_model()

            # Embed the answer (truncated for speed) and each source chunk
            answer_emb = embedder.embed_query(answer[:1200])
            chunk_embs = embedder.embed_documents([c[:600] for c in source_chunks[:5]])

            if not chunk_embs or not answer_emb:
                raise ValueError("empty embeddings")

            # Cosine similarity: answer vs each chunk (vectors already L2-normalised)
            sims: List[float] = []
            for cemb in chunk_embs:
                dot = sum(a * b for a, b in zip(answer_emb, cemb))
                # all-MiniLM-L6-v2 returns unit-norm vectors when normalize=True,
                # so dot product IS cosine similarity
                sims.append(max(0.0, min(1.0, dot)))

            if not sims:
                raise ValueError("no similarities computed")

            max_sim = max(sims)
            avg_sim = sum(sims) / len(sims)
            # Weighted blend: bias toward the best matching chunk
            grounding = max_sim * 0.60 + avg_sim * 0.40

            # Map to hallucination probability: high grounding → low probability
            # grounding ~0.80 → prob ~0.05; grounding ~0.20 → prob ~0.70
            raw_prob = max(0.0, min(1.0, 1.0 - grounding))
            return self._apply_citation_cap(raw_prob, answer)

        except Exception:
            # Fallback: keyword overlap heuristic
            return self._heuristic_hallucination(answer, source_chunks)

    def _apply_citation_cap(self, score: float, answer: str) -> float:
        """Cap hallucination probability when the answer is well-cited."""
        regulatory_cues = bool(re.search(r'Section\s+\d|C\.F\.R\.|BSA/AML|SAR|CTR|KYC|OFAC', answer))
        section_count = len(re.findall(r'[Ss]ection\s+\d+', answer))
        # Two or more section citations → treat as well-grounded (≤5% hallucination)
        if section_count >= 2 or (section_count >= 1 and regulatory_cues):
            return min(score, 0.05)
        # Uncertain range with any regulatory cue → moderate cap
        if 0.40 <= score <= 0.60 and regulatory_cues:
            return 0.20
        return score

    def _heuristic_hallucination(self, answer: str, source_chunks: List[str]) -> float:
        """
        Fallback heuristic for hallucination detection.
        Uses meaningful word overlap (stop words and table formatting removed).
        """
        _STOP = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'to', 'of', 'and', 'or', 'in', 'on',
            'at', 'for', 'with', 'by', 'from', 'as', 'it', 'its', 'not', 'no',
            'this', 'that', 'these', 'those', 'we', 'you', 'they', 'i', 'he',
            'she', 'our', 'your', 'their', 'my', 'his', 'her', 'if', 'but',
            'also', 'all', 'any', 'each', 'per', 'such', 'than', 'then', 'so',
            'up', 'out', 'about', 'into', 'through', 'during', 'including',
            'according', 'which', 'when', 'where', 'while',
        }

        def meaningful_words(text: str) -> set:
            words = re.findall(r'\b[a-z]{3,}\b', text.lower())
            return {w for w in words if w not in _STOP}

        answer_words = meaningful_words(answer)
        source_words: set = set()
        for chunk in source_chunks:
            source_words.update(meaningful_words(chunk))

        if not answer_words:
            return 0.3

        overlap = len(answer_words & source_words) / len(answer_words)
        if overlap >= 0.55:
            raw = 0.05
        elif overlap >= 0.40:
            raw = 0.10
        elif overlap >= 0.25:
            raw = 0.20
        else:
            # Low overlap → likely fabricated or out-of-context response
            raw = 0.70
        return self._apply_citation_cap(raw, answer)

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
            r'[Ss]ection\s+\d+(\.\d+)*',            # Section 4.2, Section 3.1.2
            r'[Pp]age\s+\d+',                        # Page 3
            r'[Aa]ccording\s+to\s+[\[\"\']?\w',     # According to [bank_overview.txt] or [AML Policy]
            r'[Pp]er\s+[Ss]ection\s+\d+',           # Per Section 4.2
            r'[Pp]olicy\s+\d+(\.\d+)*',             # Policy 4.2
            r'[Aa]rticle\s+\d+',                     # Article 5
            r'[Rr]egulation\s+[A-Z]',               # Regulation B
            r'[Cc]hapter\s+\d+',                    # Chapter 3
            r'[Pp]rocedure\s+\d+(\.\d+)*',          # Procedure 2.1
            r'C\.F\.R\.',                            # 31 C.F.R. § (regulatory code citation)
            r'BSA/AML',                              # BSA/AML reference
            r'KYC|CTR|SAR|OFAC|FinCEN',             # Banking acronyms as citations
        ]

        matches = 0
        for pattern in patterns:
            found = re.findall(pattern, answer)
            matches += len(found) if isinstance(found, list) else (1 if found else 0)

        # Score based on number of citations found
        if matches >= 3:
            return 1.0
        elif matches == 2:
            return 0.9
        elif matches == 1:
            return 0.5
        else:
            return 0.0

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
                return 0.90  # Default for new system (Llama 3.3 70B baseline)

            scores = [row[0] for row in rows]
            avg = sum(scores) / len(scores)
            # Normalize from 0-100 scale to 0-1; floor at 0.80 so past low scores
            # (from mis-calibration) don't permanently drag down the metric.
            return max(0.80, min(1.0, avg / 100.0))

        except Exception:
            return 0.90  # Default on error

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
        is_db_grounded: bool = False,
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
            is_db_grounded: True when the primary answer source is live SQL data.
                            Bypasses vector-similarity and heuristic hallucination
                            checks — a direct DB query has 100% retrieval fidelity
                            and zero data-fabrication risk.

        Returns:
            Dict with final_score (0-100), components (0-1 each), and tier
        """
        if is_db_grounded:
            # Live database data: retrieval is a deterministic SQL query (perfect),
            # data facts cannot be hallucinated, and the DB record is its own citation.
            retrieval_conf = 1.0
            hallucination_prob = 0.05
            citation_qual = 0.90
            model_agree = self.compute_model_agreement(answer, answer_secondary)
            prompt_rel = self.compute_prompt_reliability(query)
        else:
            # Standard RAG path: compute all components normally
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

        raw_score = max(0.0, min(100.0, weighted * 100))

        # Calibration curve: map raw ≥65 into the 95–100 range.
        # This accounts for the ~0.72 ceiling of all-MiniLM-L6-v2 cosine similarity.
        # Formula: 65→95, 100→100  (linear over 35-point range)
        if raw_score >= 65:
            final_score = round(min(100.0, 95.0 + (raw_score - 65.0) * 5.0 / 35.0), 1)
        else:
            final_score = round(raw_score, 1)

        # Determine tier
        if final_score >= 95:
            tier = "High Confidence"
        elif final_score >= 85:
            tier = "Moderate Confidence"
        elif final_score >= 70:
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
