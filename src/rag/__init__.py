"""
Banking AI RAG Module.

Sub-modules:
- chunker:          Document chunking with metadata (section, page)
- embeddings:       Dual-backend embedding (OpenAI / SentenceTransformers)
- vector_store:     Dual-backend vector store (ChromaDB / Pinecone)
- document_loader:  Multi-format document ingestion pipeline
- qa_chain:         Conversational RAG QA chain with source citations
- customer_context: Structured + unstructured customer context retrieval
"""
