from langchain_core.documents import Document

from src.rag.evaluate_retrieval import evaluate_retrieval


def test_evaluation_reports_hit_rate_and_mrr():
    cases = [
        {"query": "aml", "relevant_sources": ["aml.txt"]},
        {"query": "loans", "relevant_sources": ["loans.txt"]},
    ]

    def fake_search(query, k):
        if query == "aml":
            return [
                (Document(page_content="x", metadata={"source": "other.txt"}), 0.9),
                (Document(page_content="x", metadata={"source": "aml.txt"}), 0.8),
            ]
        return [(Document(page_content="x", metadata={"source": "other.txt"}), 0.7)]

    report = evaluate_retrieval(cases, fake_search, k=2)

    assert report["hit_rate@2"] == 0.5
    assert report["mrr"] == 0.25
    assert report["details"][0]["first_relevant_rank"] == 2
