"""
Vector Store Backend for the Banking AI RAG System.

Supports two vector store backends via VECTOR_DB env var:
  - "chroma"   → ChromaDB local persistent store (development)
  - "pinecone" → Pinecone serverless (production)

Default: chroma (for local development without external API)
"""
import os
from typing import List, Optional

import pandas as pd
from dotenv import load_dotenv
from langchain_core.documents import Document

from src.rag.embeddings import get_embeddings, get_embedding_dimension

load_dotenv()

# --- Configuration ---
VECTOR_DB = os.getenv("VECTOR_DB", "chroma")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "banking_docs")
CHROMA_INTERACTIONS_COLLECTION = "banking_interactions"
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "banking-index")


def get_vector_store(collection_name: Optional[str] = None):
    """
    Factory function returning a LangChain-compatible vector store.

    Args:
        collection_name: Override collection/index name.

    Returns:
        LangChain VectorStore instance
    """
    backend = VECTOR_DB.lower().strip()
    embeddings = get_embeddings()

    if backend == "chroma":
        from langchain_chroma import Chroma

        persist_dir = CHROMA_PERSIST_DIR
        col_name = collection_name or CHROMA_COLLECTION

        os.makedirs(persist_dir, exist_ok=True)
        print(f"  Vector DB: ChromaDB (persist={persist_dir}, collection={col_name})")

        return Chroma(
            collection_name=col_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )

    elif backend == "pinecone":
        from langchain_community.vectorstores import Pinecone as PineconeVectorStore
        from pinecone import Pinecone, ServerlessSpec

        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY not set in .env but VECTOR_DB=pinecone")

        index_name = collection_name or PINECONE_INDEX_NAME
        pc = Pinecone(api_key=api_key)

        # Create index if it doesn't exist
        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            dim = get_embedding_dimension()
            print(f"  Creating Pinecone index: {index_name} (dim={dim})")
            pc.create_index(
                name=index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

        index = pc.Index(index_name)
        print(f"  Vector DB: Pinecone (index={index_name})")

        return PineconeVectorStore(
            index=index,
            embedding=embeddings,
            text_key="text",
        )

    else:
        raise ValueError(
            f"Unknown VECTOR_DB: '{backend}'. Use 'chroma' or 'pinecone'."
        )


def index_documents(chunks: List[Document], collection_name: Optional[str] = None) -> int:
    """
    Index document chunks into the vector store.

    Args:
        chunks: List of LangChain Document objects with metadata
        collection_name: Optional override for collection/index name

    Returns:
        Number of chunks indexed
    """
    if not chunks:
        print("  No chunks to index.")
        return 0

    backend = VECTOR_DB.lower().strip()
    embeddings = get_embeddings()

    if backend == "chroma":
        from langchain_chroma import Chroma

        persist_dir = CHROMA_PERSIST_DIR
        col_name = collection_name or CHROMA_COLLECTION
        os.makedirs(persist_dir, exist_ok=True)

        # ChromaDB: use from_documents for batch indexing
        texts = [c.page_content for c in chunks]
        metadatas = [c.metadata for c in chunks]

        # Clean metadata values (ChromaDB requires str/int/float/bool)
        clean_metadatas = []
        for m in metadatas:
            clean = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    clean[k] = v
                elif v is None:
                    clean[k] = ""
                else:
                    clean[k] = str(v)
            clean_metadatas.append(clean)

        Chroma.from_texts(
            texts=texts,
            metadatas=clean_metadatas,
            embedding=embeddings,
            collection_name=col_name,
            persist_directory=persist_dir,
        )
        print(f"  Indexed {len(chunks)} chunks into ChromaDB ({col_name})")

    elif backend == "pinecone":
        from pinecone import Pinecone

        api_key = os.getenv("PINECONE_API_KEY")
        pc = Pinecone(api_key=api_key)
        index_name = collection_name or PINECONE_INDEX_NAME
        index = pc.Index(index_name)

        # Batch embed and upsert
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c.page_content for c in batch]
            vectors = embeddings.embed_documents(texts)

            upsert_data = []
            for j, (chunk, vector) in enumerate(zip(batch, vectors)):
                doc_id = f"doc_{i + j}"
                meta = {
                    "text": chunk.page_content[:1000],  # Pinecone metadata limit
                    "source": chunk.metadata.get("source", "unknown"),
                    "doc_type": chunk.metadata.get("doc_type", "general"),
                    "section": chunk.metadata.get("section", ""),
                }
                # Add customer_id if present (for interaction notes)
                if "customer_id" in chunk.metadata:
                    meta["customer_id"] = str(chunk.metadata["customer_id"])
                upsert_data.append({"id": doc_id, "values": vector, "metadata": meta})

            index.upsert(vectors=upsert_data)
            print(f"  Upserted batch {i // batch_size + 1} ({len(batch)} chunks)")

        print(f"  Indexed {len(chunks)} chunks into Pinecone ({index_name})")

    return len(chunks)


def index_interactions(
    interactions_path: str = "data/raw/interactions.csv",
    complaints_path: str = "data/raw/complaints.csv",
    collection_name: Optional[str] = None,
) -> int:
    """
    Index banker notes and complaint transcripts into the vector store.

    Each record gets customer_id as metadata for filtered retrieval.

    Returns:
        Total number of records indexed
    """
    total = 0
    chunks = []

    # 1. Banker interaction notes
    if os.path.exists(interactions_path):
        df = pd.read_csv(interactions_path)
        for _, row in df.iterrows():
            doc = Document(
                page_content=str(row["banker_note"]),
                metadata={
                    "source": "banker_notes",
                    "doc_type": "interaction_note",
                    "customer_id": str(row["customer_id"]),
                    "channel": str(row.get("channel", "")),
                    "topic": str(row.get("topic", "")),
                    "sentiment_label": str(row.get("sentiment_label", "")),
                    "timestamp": str(row.get("timestamp", "")),
                },
            )
            chunks.append(doc)
        print(f"  Loaded {len(df)} banker notes")
    else:
        print(f"  WARNING: {interactions_path} not found")

    # 2. Complaint transcripts
    if os.path.exists(complaints_path):
        df = pd.read_csv(complaints_path)
        for _, row in df.iterrows():
            # Combine transcript + resolution for richer context
            text = f"Complaint: {row['transcript_text']}\nResolution: {row['resolution_text']}"
            doc = Document(
                page_content=text,
                metadata={
                    "source": "complaints",
                    "doc_type": "complaint_transcript",
                    "customer_id": str(row["customer_id"]),
                    "category": str(row.get("category", "")),
                    "timestamp": str(row.get("timestamp", "")),
                },
            )
            chunks.append(doc)
        print(f"  Loaded {len(df)} complaint transcripts")
    else:
        print(f"  WARNING: {complaints_path} not found")

    if chunks:
        col = collection_name or CHROMA_INTERACTIONS_COLLECTION
        total = index_documents(chunks, collection_name=col)

    return total


def similarity_search(query: str, k: int = 5, filter_dict: Optional[dict] = None) -> List[Document]:
    """
    Search banking policy documents (CHROMA_COLLECTION).

    Args:
        query: Search query text
        k: Number of results to return
        filter_dict: Optional metadata filter

    Returns:
        List of matching Document objects
    """
    store = get_vector_store()  # defaults to banking_docs

    if filter_dict:
        return store.similarity_search(query, k=k, filter=filter_dict)
    else:
        return store.similarity_search(query, k=k)


def similarity_search_interactions(query: str, k: int = 5, filter_dict: Optional[dict] = None) -> List[Document]:
    """
    Search customer interaction notes and complaints (CHROMA_INTERACTIONS_COLLECTION).

    Args:
        query: Search query text
        k: Number of results to return
        filter_dict: Optional metadata filter (e.g., {"customer_id": "abc123"})

    Returns:
        List of matching Document objects
    """
    store = get_vector_store(collection_name=CHROMA_INTERACTIONS_COLLECTION)

    if filter_dict:
        return store.similarity_search(query, k=k, filter=filter_dict)
    else:
        return store.similarity_search(query, k=k)


def get_collection_stats() -> dict:
    """
    Return metadata about indexed documents in the vector store.

    For ChromaDB: queries the collection to get unique source files and chunk counts.
    For Pinecone: returns index stats via the Pinecone API.

    Returns:
        dict with 'documents' (list of per-source metadata) and 'total_chunks' (int)
    """
    backend = VECTOR_DB.lower().strip()

    try:
        if backend == "chroma":
            from langchain_chroma import Chroma
            embeddings = get_embeddings()
            store = Chroma(
                collection_name=CHROMA_COLLECTION,
                embedding_function=embeddings,
                persist_directory=CHROMA_PERSIST_DIR,
            )
            # Get all document metadata from the collection
            collection = store._collection
            result = collection.get(include=["metadatas"])
            metadatas = result.get("metadatas", []) or []

            # Aggregate per-source stats
            source_stats: dict = {}
            for meta in metadatas:
                src = meta.get("source", "unknown")
                if src not in source_stats:
                    source_stats[src] = {
                        "source": src,
                        "doc_type": meta.get("doc_type", "general"),
                        "chunk_count": 0,
                    }
                source_stats[src]["chunk_count"] += 1

            documents = sorted(source_stats.values(), key=lambda x: x["chunk_count"], reverse=True)
            total_chunks = sum(d["chunk_count"] for d in documents)

            return {"documents": documents, "total_chunks": total_chunks}

        elif backend == "pinecone":
            from pinecone import Pinecone
            api_key = os.getenv("PINECONE_API_KEY")
            pc = Pinecone(api_key=api_key)
            index_name = PINECONE_INDEX_NAME
            index = pc.Index(index_name)
            stats = index.describe_index_stats()
            total = int(stats.get("total_vector_count", 0))
            return {
                "documents": [{"source": index_name, "doc_type": "pinecone_index", "chunk_count": total}],
                "total_chunks": total,
            }

    except Exception as e:
        print(f"  [VectorStore] get_collection_stats error: {e}")

    return {"documents": [], "total_chunks": 0}
