"""Unit tests for optional cross-encoder reranking."""
from langchain_core.documents import Document

from src.rag.reranker import rerank_results


class FakeCrossEncoder:
    def predict(self, pairs):
        return [0.1 if "generic" in text else 0.95 for _, text in pairs]


def test_cross_encoder_can_promote_more_relevant_evidence():
    generic = Document(page_content="generic banking content", metadata={"source": "generic.txt"})
    exact = Document(page_content="BSA AML CTR filing requirement", metadata={"source": "aml.txt"})

    results = rerank_results(
        "What are the CTR filing requirements?",
        [(generic, 0.95), (exact, 0.70)],
        model=FakeCrossEncoder(),
        reranker_weight=0.8,
    )

    assert results[0][0].metadata["source"] == "aml.txt"
    assert results[0][0].metadata["reranker_score"] == 0.95


def test_missing_model_preserves_original_order(monkeypatch):
    first = Document(page_content="first")
    second = Document(page_content="second")
    monkeypatch.setattr("src.rag.reranker.get_reranker", lambda: None)

    results = rerank_results("query", [(first, 0.9), (second, 0.8)], top_k=1)

    assert results == [(first, 0.9)]
