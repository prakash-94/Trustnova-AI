"""Focused tests for hybrid policy retrieval."""
from langchain_core.documents import Document

from src.rag.hybrid_retriever import bm25_search, reciprocal_rank_fusion


def _doc(text: str, source: str, doc_type: str = "general", index: int = 0) -> Document:
    return Document(
        page_content=text,
        metadata={"source": source, "doc_type": doc_type, "chunk_index": index},
    )


def test_bm25_prioritizes_exact_banking_identifiers():
    documents = [
        _doc("Residential mortgage rates and loan eligibility", "loans.txt"),
        _doc("BSA/AML Section 4.2 requires CTR filing", "aml.txt", "compliance"),
    ]

    results = bm25_search("BSA/AML CTR", documents=documents)

    assert results[0][0].metadata["source"] == "aml.txt"
    assert results[0][1] == 1.0


def test_bm25_applies_rbac_metadata_filter():
    documents = [
        _doc("CTR filing requirements", "public.txt", "general"),
        _doc("CTR filing requirements", "restricted.txt", "compliance"),
    ]

    results = bm25_search(
        "CTR filing",
        documents=documents,
        metadata_filter={"doc_type": {"$in": ["general"]}},
    )

    assert [doc.metadata["source"] for doc, _ in results] == ["public.txt"]


def test_rank_fusion_rewards_results_found_by_both_channels():
    shared = _doc("shared result", "shared.txt")
    vector_only = _doc("semantic result", "vector.txt")
    lexical_only = _doc("exact result", "lexical.txt")

    results = reciprocal_rank_fusion(
        [(vector_only, 0.9), (shared, 0.8)],
        [(shared, 1.0), (lexical_only, 0.7)],
        k=3,
    )

    assert results[0][0].metadata["source"] == "shared.txt"
    assert results[0][0].metadata["retrieval_channels"] == "vector,lexical"


def test_rank_fusion_deduplicates_chunks():
    same = _doc("same text", "policy.txt", index=3)

    results = reciprocal_rank_fusion([(same, 0.8)], [(same, 1.0)], k=5)

    assert len(results) == 1


def test_vector_failure_uses_circuit_breaker(monkeypatch):
    import src.rag.hybrid_retriever as hybrid

    attempts = {"count": 0}
    monkeypatch.setenv("VECTOR_DB", "chroma")

    def failing_store():
        attempts["count"] += 1
        raise OSError("offline")

    monkeypatch.setattr("src.rag.vector_store.get_vector_store", failing_store)
    monkeypatch.setattr(hybrid, "bm25_search", lambda *args, **kwargs: [])
    hybrid.reset_retrieval_state()

    hybrid.hybrid_search("first", k=2)
    hybrid.hybrid_search("second", k=2)

    assert attempts["count"] == 1
    hybrid.reset_retrieval_state()
