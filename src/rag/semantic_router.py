"""
Semantic Router — embedding-based intent classification.

Priority 2 upgrade over the regex classifier in intent_classifier.py.

Why it beats keywords:
  "Is he underwater on any obligations?"  → regex misses 'loan' intent
                                          → semantic finds it (similarity to
                                            "what loans does the customer owe")

  "Delinquency situation for this client" → regex misses 'loan'+'fraud'
                                          → semantic finds both

How it works:
  1. Each intent has a bank of prototype queries (human-written examples).
  2. On first call, embed all prototypes and average per intent → one vector per intent.
     (cached via lru_cache — computed ONCE per server lifetime)
  3. Embed the incoming query.
  4. Cosine similarity query-vector vs. every intent-vector.
  5. Return top intents whose similarity exceeds CONFIDENCE_THRESHOLD.
  6. If embeddings unavailable → fall back to regex classify_intents() silently.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import List

# ── Intent prototype queries ──────────────────────────────────────────────────
# More examples per intent = better coverage. Cover both formal and casual phrasing.

INTENT_PROTOTYPES: dict[str, list[str]] = {
    "risk": [
        "show me high risk customers",
        "which customers have critical AML risk rating",
        "list customers with elevated risk profile",
        "what is the risk assessment for this client",
        "show risk distribution across portfolio",
        "pull up the risk score",
        "who are the risky clients",
        "customers flagged at high risk level",
        "AML risk classification for this account",
        "credit risk exposure",
    ],
    "fraud": [
        "show fraud alerts",
        "which transactions are suspicious",
        "list flagged transactions",
        "any active fraud cases",
        "show me the fraud queue",
        "suspicious activity detected on account",
        "fraud investigation status",
        "is this transaction fraudulent",
        "open fraud alerts for this customer",
        "anomaly detected in spending",
    ],
    "customer": [
        "show customer profile",
        "tell me about this client",
        "customer 360 view",
        "what is the customer history",
        "pull up customer details",
        "who is this customer",
        "give me the client overview",
        "customer information summary",
        "full profile for this person",
        "KYC status and background",
    ],
    "transaction": [
        "show recent transactions",
        "transaction history for this customer",
        "payment history last 30 days",
        "spending patterns and purchases",
        "latest transfers and withdrawals",
        "show me what the customer spent",
        "purchase activity this month",
        "deposit and withdrawal history",
        "transaction summary",
        "money movement for this account",
    ],
    "account": [
        "what is the account balance",
        "show account details",
        "checking account status and balance",
        "savings account overview",
        "how much money is in the account",
        "account information and type",
        "current balance on this account",
        "account opened date and status",
        "show all accounts for this customer",
        "account standing and balance sheet",
    ],
    "loan": [
        "show loan portfolio",
        "what active loans does this customer have",
        "outstanding debt and obligations",
        "mortgage status and balance",
        "is the customer underwater on any obligations",
        "delinquency situation for this client",
        "what does the customer owe the bank",
        "loan repayment status",
        "outstanding balance on the loan",
        "any delinquent or defaulted loans",
        "installment payment history",
        "show me the borrowing situation",
        "credit exposure and debt load",
    ],
    "trust_score": [
        "what is the trust score",
        "show customer trust rating",
        "AI trust metrics for this client",
        "trust score history and trend",
        "how trustworthy is this customer",
        "trust tier and confidence level",
        "customer reliability score",
    ],
    "stats": [
        "institution wide summary statistics",
        "portfolio overview and dashboard",
        "how many customers do we have total",
        "total loan value across the bank",
        "risk dashboard and breakdown",
        "overall bank performance metrics",
        "customer count and distribution",
        "fraud rate across the institution",
    ],
    "trustnova_features": [
        "what can TrustNova AI do",
        "explain the platform features",
        "how does the AI system work",
        "what capabilities does the copilot have",
        "TrustNova platform overview",
        "what does the system support",
        "features available in TrustNova",
    ],
    "kyc": [
        "what is the KYC status for this customer",
        "has the customer completed identity verification",
        "KYC documents submitted and approved",
        "customer due diligence status",
        "what identity documents are on file",
        "CDD level for this customer",
        "enhanced due diligence required",
        "is KYC complete for this account",
        "know your customer compliance check",
    ],
    "aml": [
        "show AML alerts for this customer",
        "any suspicious activity reports filed",
        "SAR or CTR filing status",
        "anti money laundering alert",
        "AML flag on this customer",
        "cash transaction report",
        "structuring activity detected",
        "AML watchlist match",
        "currency transaction report threshold",
    ],
    "policy": [
        "what is the policy for this",
        "explain the compliance rule",
        "what are the regulatory requirements",
        "how does the AML policy work",
        "what is the threshold for flagging",
        "banking regulation and procedure",
        "compliance workflow and guidelines",
        "what documentation is required by policy",
        "BSA AML compliance rule",
        "what triggers an SAR filing",
    ],
    "general": [
        "help me understand this",
        "explain banking policy",
        "what is the policy on this",
        "how does this banking rule work",
        "what are the compliance requirements",
        "explain the regulation",
        "banking guidelines and procedures",
    ],
}

# Minimum cosine similarity to accept an intent match
CONFIDENCE_THRESHOLD = 0.40
# Maximum intents to return
MAX_INTENTS = 3


# ── Cached intent vectors ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_intent_vectors() -> dict[str, list[float]] | None:
    """
    Compute and cache one averaged embedding vector per intent.
    Returns None if the embedding model is not available locally.
    Runs once per server process — subsequent calls return the cached dict.
    """
    try:
        import numpy as np
        from src.rag.embeddings import get_embeddings

        embedder = get_embeddings(local_files_only=True)
        vectors: dict[str, list[float]] = {}

        for intent, examples in INTENT_PROTOTYPES.items():
            embeddings = embedder.embed_documents(examples)  # list[list[float]]
            arr = np.array(embeddings, dtype=float)
            avg = arr.mean(axis=0)
            norm = np.linalg.norm(avg)
            vectors[intent] = (avg / norm).tolist() if norm > 0 else avg.tolist()

        print(f"[SemanticRouter] Intent vectors ready — {len(vectors)} intents loaded")
        return vectors

    except Exception as exc:
        print(f"[SemanticRouter] Embedding unavailable, using regex fallback: {exc}")
        return None


def precompute_intent_vectors() -> bool:
    """
    Trigger eager precomputation of intent vectors at server startup.
    Clears any stale cache first so prototype changes take effect on restart.
    Returns True if successful. Call from main.py startup event.
    """
    _get_intent_vectors.cache_clear()
    return _get_intent_vectors() is not None


# ── Public API ────────────────────────────────────────────────────────────────

def semantic_route(query: str, top_k: int = MAX_INTENTS) -> list[str]:
    """
    Classify query into 1–3 intents using semantic similarity.

    Falls back to regex classify_intents() if embeddings are unavailable.

    Args:
        query: raw or rewritten banker query
        top_k: max intents to return (default: 3)

    Returns:
        Ordered list of intent strings, best match first.
    """
    vectors = _get_intent_vectors()
    if vectors is None:
        return _regex_fallback(query, top_k)

    try:
        import numpy as np
        from src.rag.embeddings import get_embeddings

        embedder  = get_embeddings(local_files_only=True)
        q_emb     = embedder.embed_query(query)
        q_vec     = np.array(q_emb, dtype=float)
        q_norm    = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        scores: list[tuple[str, float]] = []
        for intent, vec in vectors.items():
            i_vec = np.array(vec, dtype=float)
            sim   = float(np.dot(q_vec, i_vec))
            scores.append((intent, sim))

        scores.sort(key=lambda x: x[1], reverse=True)

        # Keep intents that clear the confidence threshold
        results = [
            intent for intent, sim in scores[:top_k]
            if sim >= CONFIDENCE_THRESHOLD
        ]

        # Always return at least one intent
        if not results:
            results = [scores[0][0]] if scores else ["general"]

        # Never return 'stats' alongside a more specific intent
        if len(results) > 1 and "stats" in results:
            results.remove("stats")

        return results

    except Exception:
        return _regex_fallback(query, top_k)


def semantic_route_with_scores(query: str) -> list[tuple[str, float]]:
    """
    Same as semantic_route but returns (intent, similarity_score) pairs.
    Useful for debugging and logging.
    """
    vectors = _get_intent_vectors()
    if vectors is None:
        intents = _regex_fallback(query, MAX_INTENTS)
        return [(i, 1.0) for i in intents]

    try:
        import numpy as np
        from src.rag.embeddings import get_embeddings

        embedder = get_embeddings(local_files_only=True)
        q_emb    = embedder.embed_query(query)
        q_vec    = np.array(q_emb, dtype=float)
        norm     = np.linalg.norm(q_vec)
        if norm > 0:
            q_vec = q_vec / norm

        scores = [
            (intent, float(np.dot(q_vec, np.array(vec, dtype=float))))
            for intent, vec in vectors.items()
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:MAX_INTENTS]

    except Exception:
        intents = _regex_fallback(query, MAX_INTENTS)
        return [(i, 1.0) for i in intents]


# ── Regex fallback ────────────────────────────────────────────────────────────

def _regex_fallback(query: str, top_k: int) -> list[str]:
    """Use the existing regex classifier as a safe fallback."""
    from src.rag.intent_classifier import classify_intents
    return classify_intents(query, max_intents=top_k)
