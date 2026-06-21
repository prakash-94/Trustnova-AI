"""Optional cross-encoder reranking for hybrid retrieval results."""
from __future__ import annotations

import math
import os
from typing import Optional

from langchain_core.documents import Document


RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
_reranker = None
_reranker_unavailable = False


def get_reranker():
    """Return a cached local cross-encoder without downloading on a request."""
    global _reranker, _reranker_unavailable
    if _reranker_unavailable:
        return None
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(
                RERANKER_MODEL,
                device="cpu",
                local_files_only=True,
            )
        except Exception as exc:
            _reranker_unavailable = True
            print(f"[RAG] Cross-encoder reranker unavailable; keeping fused ranks: {exc}")
            return None
    return _reranker


def reset_reranker() -> None:
    """Reset cached state after installing or changing the reranker model."""
    global _reranker, _reranker_unavailable
    _reranker = None
    _reranker_unavailable = False


def _probability(value: float) -> float:
    """Convert a cross-encoder logit to a bounded relevance probability."""
    if 0.0 <= value <= 1.0:
        return value
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-min(value, 50.0)))
    return 1.0 / (1.0 + math.exp(min(-value, 50.0)))


def rerank_results(
    query: str,
    results: list[tuple[Document, float]],
    *,
    top_k: Optional[int] = None,
    model=None,
    reranker_weight: float = 0.6,
) -> list[tuple[Document, float]]:
    """Blend cross-encoder relevance with the hybrid retrieval score."""
    if not results:
        return []
    model = model or get_reranker()
    if model is None:
        return results[:top_k]

    pairs = [(query, doc.page_content) for doc, _ in results]
    predictions = model.predict(pairs)
    reranked: list[tuple[Document, float]] = []
    for (doc, retrieval_score), prediction in zip(results, predictions):
        cross_score = _probability(float(prediction))
        combined = reranker_weight * cross_score + (1.0 - reranker_weight) * retrieval_score
        copied = doc.model_copy(deep=True)
        copied.metadata["reranker_score"] = round(cross_score, 4)
        copied.metadata["combined_relevance"] = round(combined, 4)
        reranked.append((copied, combined))

    reranked.sort(key=lambda item: item[1], reverse=True)
    return reranked[:top_k]
