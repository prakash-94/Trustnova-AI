"""Hybrid lexical/vector retrieval for TrustNova policy documents."""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from langchain_core.documents import Document


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[./-][a-z0-9]+)*", re.IGNORECASE)
_vector_retrieval_unavailable = False


def _tokenize(text: str) -> list[str]:
    """Keep banking identifiers such as BSA/AML and 31-CFR intact."""
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _metadata_matches(metadata: dict, metadata_filter: Optional[dict]) -> bool:
    """Apply the equality/$in subset of Chroma filters used by TrustNova RBAC."""
    if not metadata_filter:
        return True
    if "$and" in metadata_filter:
        return all(_metadata_matches(metadata, part) for part in metadata_filter["$and"])
    for key, expected in metadata_filter.items():
        actual = metadata.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$eq" in expected and actual != expected["$eq"]:
                return False
        elif actual != expected:
            return False
    return True


@lru_cache(maxsize=1)
def load_policy_chunks() -> tuple[Document, ...]:
    """Load the small local policy corpus once for lexical retrieval."""
    from src.rag.chunker import chunk_documents

    docs_dir = Path(os.getenv("DOCS_DIR", "data/raw/banking_docs"))
    documents = []
    for path in sorted(docs_dir.glob("*.txt")):
        name = path.name.lower()
        if "compliance" in name:
            doc_type = "compliance"
        elif "loan" in name:
            doc_type = "loan_policy"
        elif "mortgage" in name:
            doc_type = "mortgage"
        elif "wire" in name:
            doc_type = "wire_transfer"
        elif "fraud" in name or "risk" in name:
            doc_type = "risk_fraud_security"
        elif "fee" in name:
            doc_type = "fee_schedule"
        else:
            doc_type = "general"
        documents.append(Document(
            page_content=path.read_text(encoding="utf-8"),
            metadata={
                "source": path.name,
                "source_file": path.name,
                "doc_type": doc_type,
                "document_version": str(path.stat().st_mtime_ns),
                "access_scope": "internal",
            },
        ))
    return tuple(chunk_documents(documents))


def clear_policy_cache() -> None:
    """Refresh lexical documents after an upload or re-index operation."""
    load_policy_chunks.cache_clear()


def reset_retrieval_state() -> None:
    """Retry external retrieval dependencies after setup/configuration changes."""
    global _vector_retrieval_unavailable
    _vector_retrieval_unavailable = False
    clear_policy_cache()


def bm25_search(
    query: str,
    *,
    k: int = 10,
    metadata_filter: Optional[dict] = None,
    documents: Optional[Iterable[Document]] = None,
) -> list[tuple[Document, float]]:
    """Return BM25-ranked policy chunks with scores normalized to [0, 1]."""
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    corpus = [
        doc for doc in (documents if documents is not None else load_policy_chunks())
        if _metadata_matches(doc.metadata, metadata_filter)
    ]
    if not corpus:
        return []

    tokenized = [_tokenize(doc.page_content) for doc in corpus]
    lengths = [len(tokens) for tokens in tokenized]
    avg_length = sum(lengths) / len(lengths) or 1.0
    document_frequency = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))

    n_docs = len(corpus)
    k1, b = 1.5, 0.75
    scored: list[tuple[Document, float]] = []
    for doc, tokens, length in zip(corpus, tokenized, lengths):
        frequencies = Counter(tokens)
        score = 0.0
        for term in query_terms:
            tf = frequencies.get(term, 0)
            if not tf:
                continue
            df = document_frequency[term]
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1.0 - b + b * length / avg_length)
            score += idf * (tf * (k1 + 1.0)) / denominator
        if score > 0:
            scored.append((doc, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored:
        return []
    max_score = scored[0][1]
    return [(doc, score / max_score) for doc, score in scored[:k]]


def _document_key(doc: Document) -> tuple:
    return (
        doc.metadata.get("source", ""),
        doc.metadata.get("chunk_index", ""),
        doc.page_content,
    )


def reciprocal_rank_fusion(
    vector_results: list[tuple[Document, float]],
    lexical_results: list[tuple[Document, float]],
    *,
    k: int,
    rank_constant: int = 60,
) -> list[tuple[Document, float]]:
    """Fuse result ranks while retaining an interpretable relevance score."""
    records: dict[tuple, dict] = {}
    for channel, results in (("vector", vector_results), ("lexical", lexical_results)):
        for rank, (doc, relevance) in enumerate(results, 1):
            key = _document_key(doc)
            record = records.setdefault(key, {"doc": doc, "rrf": 0.0, "scores": {}, "channels": []})
            record["rrf"] += 1.0 / (rank_constant + rank)
            record["scores"][channel] = max(0.0, min(1.0, float(relevance)))
            record["channels"].append(channel)

    ranked = sorted(records.values(), key=lambda record: record["rrf"], reverse=True)[:k]
    output: list[tuple[Document, float]] = []
    for record in ranked:
        doc = record["doc"].model_copy(deep=True)
        doc.metadata["retrieval_channels"] = ",".join(record["channels"])
        doc.metadata["fusion_score"] = round(record["rrf"], 6)
        # Preserve cosine relevance when available; exact lexical matches remain
        # useful evidence when the vector service is unavailable.
        relevance = max(record["scores"].values())
        output.append((doc, relevance))
    return output


def hybrid_search(
    query: str,
    *,
    k: int = 5,
    metadata_filter: Optional[dict] = None,
) -> list[tuple[Document, float]]:
    """Retrieve from vector and lexical channels, tolerating either being offline."""
    fetch_k = max(k * 2, 10)
    global _vector_retrieval_unavailable
    vector_results: list[tuple[Document, float]] = []
    vector_backend = os.getenv("VECTOR_DB", "chroma").lower().strip()
    if vector_backend not in ("lexical", "none", "disabled") and not _vector_retrieval_unavailable:
        try:
            from src.rag.vector_store import get_vector_store

            store = get_vector_store()
            kwargs: dict = {"k": fetch_k}
            if metadata_filter:
                kwargs["filter"] = metadata_filter
            vector_results = store.similarity_search_with_relevance_scores(query, **kwargs)
        except Exception as exc:
            _vector_retrieval_unavailable = True
            print(f"[RAG] Vector retrieval unavailable; using lexical search: {exc}")

    lexical_results = bm25_search(
        query,
        k=fetch_k,
        metadata_filter=metadata_filter,
    )
    fused = reciprocal_rank_fusion(vector_results, lexical_results, k=fetch_k)
    if os.getenv("RERANKER_ENABLED", "true").lower() in ("1", "true", "yes", "on"):
        from src.rag.reranker import rerank_results

        return rerank_results(query, fused, top_k=k)
    return fused[:k]
