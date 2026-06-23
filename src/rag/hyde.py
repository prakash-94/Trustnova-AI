"""
HyDE — Hypothetical Document Embeddings for superior vector search.

Priority 3 upgrade over direct query embedding.

Mechanical analogy:
  Old way — searching a parts catalogue by saying "I need a round metal thing
             with threads" → vague → poor match.
  HyDE way — first sketch the ideal part on paper (the hypothetical document),
             then search by the sketch → precise match.

How it works:
  1. Ask the LLM to write a SHORT hypothetical policy paragraph that would
     answer the user's question perfectly.
  2. Embed THAT paragraph instead of the raw question.
  3. Use the hypothetical embedding to search the vector store.

Why it works:
  The hypothetical answer uses the SAME vocabulary as the real policy documents
  (technical terms, section numbers, regulatory language). A raw question like
  "what's the AML rule for wire transfers?" uses different words than the
  document "BSA/AML Compliance Section 4.2: Currency Transaction Reports...".
  HyDE bridges that vocabulary gap.

Graceful degradation:
  - If LLM call fails → fall back to embedding the original query (zero data loss)
  - If embeddings unavailable → return original query string unchanged
"""
from __future__ import annotations

from typing import Optional

# ── System prompt for hypothetical doc generation ─────────────────────────────

_HYDE_SYSTEM = (
    "You are a banking policy expert. Given a question, write a concise "
    "hypothetical excerpt (2-4 sentences) from a banking policy manual or "
    "compliance document that would directly answer this question. "
    "Write in formal banking/regulatory language. "
    "Do NOT answer conversationally — write as if it were a policy document excerpt. "
    "Output ONLY the hypothetical excerpt, nothing else."
)

# Maximum tokens for the hypothetical document (keep it short — just enough
# to carry the right vocabulary for embedding)
_MAX_TOKENS = 150


# ── Public API ────────────────────────────────────────────────────────────────

def generate_hypothetical_document(query: str) -> str:
    """
    Ask the LLM to write a short hypothetical policy paragraph for this query.

    Returns the hypothetical text, or the original query on any failure.
    Uses the 'lookup' task type (cheapest/fastest model).
    """
    try:
        from src.api.llm_router import route

        prompt = (
            f"{_HYDE_SYSTEM}\n\n"
            f"QUESTION: {query}\n\n"
            f"HYPOTHETICAL POLICY EXCERPT:"
        )
        result = route("lookup", prompt)
        doc    = result.get("response", "").strip()

        # Sanity: must be non-empty and not absurdly long
        if not doc or len(doc) > 800:
            return query

        return doc

    except Exception:
        return query   # always fall back to original query


def hyde_embed_query(query: str) -> Optional[list[float]]:
    """
    Generate a hypothetical document, then return its embedding vector.

    Args:
        query: the user's question

    Returns:
        Embedding vector (list of floats) or None if embeddings unavailable.
    """
    try:
        from src.rag.embeddings import get_embeddings

        hypothetical_doc = generate_hypothetical_document(query)
        embedder         = get_embeddings(local_files_only=True)
        embedding        = embedder.embed_query(hypothetical_doc)
        return embedding

    except Exception:
        return None


def hybrid_hyde_search(
    query: str,
    *,
    k: int = 6,
    metadata_filter: dict | None = None,
) -> list:
    """
    Vector search using HyDE embedding + BM25 lexical search, fused via RRF.

    Replaces the standard hybrid_search() for policy/document retrieval.
    Falls back to standard hybrid_search() if HyDE fails.

    Args:
        query:           original user question
        k:               number of results to return
        metadata_filter: optional Chroma/Pinecone metadata filter

    Returns:
        list of (Document, score) tuples — same format as hybrid_search()
    """
    from src.rag.hybrid_retriever import (
        bm25_search, reciprocal_rank_fusion, hybrid_search
    )

    fetch_k = max(k * 2, 10)

    # ── Channel 1: HyDE vector search ────────────────────────────────────────
    vector_results = []
    hyde_embedding = hyde_embed_query(query)

    if hyde_embedding is not None:
        try:
            import os
            from src.rag.vector_store import get_vector_store

            store = get_vector_store()

            # Use the pre-computed HyDE embedding directly for similarity search
            vector_results = _search_by_embedding(
                store, hyde_embedding, k=fetch_k,
                metadata_filter=metadata_filter,
            )
        except Exception:
            # HyDE vector search failed — will rely on BM25 only
            pass

    # If HyDE vector search failed entirely, fall back to standard hybrid
    if not vector_results:
        return hybrid_search(query, k=k, metadata_filter=metadata_filter)

    # ── Channel 2: BM25 lexical search (unchanged) ────────────────────────────
    lexical_results = bm25_search(
        query, k=fetch_k, metadata_filter=metadata_filter
    )

    # ── Fuse and rerank ───────────────────────────────────────────────────────
    fused = reciprocal_rank_fusion(vector_results, lexical_results, k=fetch_k)

    import os
    if os.getenv("RERANKER_ENABLED", "true").lower() in ("1", "true", "yes", "on"):
        from src.rag.reranker import rerank_results
        return rerank_results(query, fused, top_k=k)

    return fused[:k]


# ── Internals ─────────────────────────────────────────────────────────────────

def _search_by_embedding(
    store,
    embedding: list[float],
    *,
    k: int,
    metadata_filter: dict | None,
) -> list:
    """
    Run a similarity search using a pre-computed embedding vector.
    Handles both Chroma and Pinecone backends.
    """
    kwargs: dict = {"k": k}
    if metadata_filter:
        kwargs["filter"] = metadata_filter

    # LangChain Chroma / Pinecone expose similarity_search_by_vector
    if hasattr(store, "similarity_search_by_vector_with_relevance_scores"):
        return store.similarity_search_by_vector_with_relevance_scores(
            embedding, **kwargs
        )
    if hasattr(store, "similarity_search_by_vector"):
        docs = store.similarity_search_by_vector(embedding, **kwargs)
        return [(d, 0.7) for d in docs]   # default score when not returned

    # Last resort: fall back to query-text search
    return store.similarity_search_with_relevance_scores(
        "banking policy", **kwargs   # dummy query — shouldn't reach here
    )
