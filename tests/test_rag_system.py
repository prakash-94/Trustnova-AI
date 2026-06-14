"""
RAG System Integration Tests.

Tests the full RAG pipeline:
- Vector store search returning relevant results
- Source citations in results
- Customer context retrieval
- 10 banking questions with cited answers

Requires: ChromaDB indexed (run: python -m src.rag.document_loader)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd

from src.rag.vector_store import similarity_search, similarity_search_interactions, get_vector_store
from src.rag.chunker import chunk_documents, detect_section
from src.rag.embeddings import get_embeddings, get_embedding_dimension
from src.rag.customer_context import get_db_engine


# --- Fixture: Sample customer ID ---
@pytest.fixture
def sample_customer_id():
    engine = get_db_engine()
    df = pd.read_sql("SELECT customer_id FROM customers LIMIT 1", engine)
    assert not df.empty
    return df.iloc[0]["customer_id"]


# ============================================================
# Embedding Backend Tests
# ============================================================
class TestEmbeddings:
    def test_get_embeddings_returns_object(self):
        emb = get_embeddings()
        assert emb is not None

    def test_embedding_dimension(self):
        dim = get_embedding_dimension()
        assert dim == 384  # all-MiniLM-L6-v2

    def test_embed_query(self):
        emb = get_embeddings()
        vector = emb.embed_query("What is the AML policy?")
        assert len(vector) == 384
        assert all(isinstance(v, float) for v in vector)


# ============================================================
# Chunker Tests
# ============================================================
class TestChunker:
    def test_section_detection_markdown(self):
        text = "## AML Policy\nThis section covers anti-money laundering."
        section = detect_section(text)
        assert "AML Policy" in section

    def test_section_detection_numbered(self):
        text = "1. Introduction\nWelcome to the bank."
        section = detect_section(text)
        assert "Introduction" in section

    def test_chunk_documents_output(self):
        from langchain_core.documents import Document
        docs = [Document(page_content="A" * 1200, metadata={"source": "test.txt"})]
        chunks = chunk_documents(docs, chunk_size=500, chunk_overlap=50)
        assert len(chunks) >= 2
        assert all("chunk_index" in c.metadata for c in chunks)
        assert all("source_file" in c.metadata for c in chunks)


# ============================================================
# Vector Store Search Tests
# ============================================================
class TestVectorStore:
    def test_vector_store_initialized(self):
        store = get_vector_store()
        assert store is not None

    def test_similarity_search_returns_results(self):
        results = similarity_search("AML policy", k=3)
        assert len(results) > 0
        assert hasattr(results[0], "page_content")
        assert hasattr(results[0], "metadata")

    def test_search_metadata_has_source(self):
        results = similarity_search("wire transfer limits", k=3)
        for doc in results:
            assert "source" in doc.metadata or "source_file" in doc.metadata


# ============================================================
# 10 Banking Questions — RAG Retrieval Test
# ============================================================
BANKING_QUESTIONS = [
    {
        "question": "What is the AML policy for large cash deposits?",
        "expected_sources": [
            "compliance_guide", "wire_transfers",
            "compliance_aml_kyc", "risk_fraud_security",
        ],
    },
    {
        "question": "What are the KYC requirements for new business accounts?",
        "expected_sources": [
            "business_banking", "compliance_guide",
            "compliance_aml_kyc", "operations_procedures",
        ],
    },
    {
        "question": "What credit score is needed for a premium credit card?",
        "expected_sources": [
            "credit_cards", "products_services_guide", "loan_policies",
        ],
    },
    {
        "question": "What are the wire transfer limits and fees?",
        "expected_sources": ["wire_transfers", "fee_schedule", "operations_procedures"],
    },
    {
        "question": "Explain the mortgage pre-approval process.",
        "expected_sources": ["mortgage_guide", "loan_policies", "products_services_guide"],
    },
    {
        "question": "What savings account options do you offer?",
        "expected_sources": [
            "savings_products", "products_services_guide", "fee_schedule",
        ],
    },
    {
        "question": "What are the fees for international transactions?",
        "expected_sources": ["fee_schedule", "wire_transfers", "operations_procedures"],
    },
    {
        "question": "How does the mobile banking app work?",
        "expected_sources": ["digital_banking", "products_services_guide", "faq_general"],
    },
    {
        "question": "What are the loan interest rates?",
        "expected_sources": ["loan_policies", "products_services_guide", "mortgage_guide"],
    },
    {
        "question": "What wealth management services are available?",
        "expected_sources": ["wealth_management", "products_services_guide"],
    },
]


class TestBankingQuestions:
    """Test that RAG retrieves relevant documents for 10 banking questions."""

    @pytest.mark.parametrize(
        "qa",
        BANKING_QUESTIONS,
        ids=[q["question"][:50] for q in BANKING_QUESTIONS],
    )
    def test_retrieval_returns_relevant_sources(self, qa):
        """Each question should retrieve at least one relevant source document."""
        results = similarity_search(qa["question"], k=5)
        assert len(results) > 0, f"No results for: {qa['question']}"

        # Check that at least one expected source appears in results
        retrieved_sources = [
            doc.metadata.get("source", doc.metadata.get("source_file", ""))
            for doc in results
        ]
        retrieved_str = " ".join(retrieved_sources).lower()

        found_match = any(
            expected.lower() in retrieved_str
            for expected in qa["expected_sources"]
        )

        assert found_match, (
            f"Question: {qa['question']}\n"
            f"Expected sources containing: {qa['expected_sources']}\n"
            f"Got: {retrieved_sources}"
        )

    def test_all_questions_have_content(self):
        """Verify all 10 questions return non-empty content."""
        for qa in BANKING_QUESTIONS:
            results = similarity_search(qa["question"], k=3)
            assert len(results) > 0
            assert len(results[0].page_content) > 20


# ============================================================
# Customer-Filtered Retrieval Test
# ============================================================
class TestCustomerRetrieval:
    def test_customer_filtered_search(self, sample_customer_id):
        """Test that customer-filtered search works."""
        results = similarity_search_interactions(
            query=f"interaction notes for customer",
            k=3,
            filter_dict={"customer_id": sample_customer_id},
        )
        # May or may not have results depending on data, but shouldn't error
        assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
