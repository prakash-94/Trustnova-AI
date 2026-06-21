"""
Embedding Backend for the Banking AI RAG System.

Supports two embedding backends via EMBEDDING_BACKEND env var:
  - "openai"                → OpenAI text-embedding-ada-002 (production)
  - "sentence_transformers" → all-MiniLM-L6-v2 (local / cost-free fallback)

Default: sentence_transformers (for local development without API costs)
"""
import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "sentence_transformers")
OPENAI_EMBEDDING_MODEL = "text-embedding-ada-002"
ST_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=4)
def _get_embeddings_cached(backend: str, local_files_only: bool):
    """Build one embedding client per backend/offline-mode combination."""
    if backend == "openai":
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in .env but EMBEDDING_BACKEND=openai")

        print(f"  Embedding backend: OpenAI ({OPENAI_EMBEDDING_MODEL})")
        return OpenAIEmbeddings(
            model=OPENAI_EMBEDDING_MODEL,
            openai_api_key=api_key,
        )

    if backend in ("sentence_transformers", "sentence-transformers", "st", "local"):
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings

        mode = ", local cache only" if local_files_only else ""
        print(f"  Embedding backend: SentenceTransformers ({ST_MODEL_NAME}{mode})")
        return HuggingFaceEmbeddings(
            model_name=ST_MODEL_NAME,
            model_kwargs={"device": "cpu", "local_files_only": local_files_only},
            encode_kwargs={"normalize_embeddings": True},
        )

    raise ValueError(
        f"Unknown EMBEDDING_BACKEND: '{backend}'. "
        f"Use 'openai' or 'sentence_transformers'."
    )


def get_embeddings(
    backend: Optional[str] = None,
    *,
    local_files_only: bool = False,
):
    """
    Factory function returning a LangChain-compatible embeddings object.

    Args:
        backend: "openai" or "sentence_transformers". Defaults to EMBEDDING_BACKEND env var.
        local_files_only: For local HuggingFace models, fail quickly instead of
            downloading weights. This is useful on latency-sensitive request paths;
            the indexing/setup command remains responsible for downloading the model.

    Returns:
        LangChain Embeddings instance
    """
    resolved_backend = (backend or os.getenv("EMBEDDING_BACKEND", EMBEDDING_BACKEND)).lower().strip()
    return _get_embeddings_cached(resolved_backend, local_files_only)


def clear_embeddings_cache() -> None:
    """Clear cached clients, primarily for configuration changes and tests."""
    _get_embeddings_cached.cache_clear()


def get_embedding_dimension(backend: Optional[str] = None) -> int:
    """Return the embedding vector dimension for the configured backend."""
    backend = (backend or EMBEDDING_BACKEND).lower().strip()

    if backend == "openai":
        return 1536  # text-embedding-ada-002
    elif backend in ("sentence_transformers", "sentence-transformers", "st", "local"):
        return 384   # all-MiniLM-L6-v2
    else:
        return 384   # default
