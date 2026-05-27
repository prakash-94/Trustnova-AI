"""
Document Chunker for the Banking AI RAG System.

Splits documents into optimal chunks for embedding using
RecursiveCharacterTextSplitter with section and page metadata.

Config: chunk_size=500, overlap=50 (per TODO spec)
"""
import re
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


# --- Configuration ---
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50

# Section heading patterns (detect markdown-style and uppercase headings)
SECTION_PATTERNS = [
    re.compile(r"^#{1,4}\s+(.+)", re.MULTILINE),               # ## Section Name
    re.compile(r"^([A-Z][A-Z\s&/]{3,})$", re.MULTILINE),       # ALL CAPS HEADING
    re.compile(r"^(\d+\.\s+[A-Z].+)$", re.MULTILINE),          # 1. Section Name
    re.compile(r"^(Section\s+\d+[\.:].+)$", re.MULTILINE | re.IGNORECASE),  # Section 4.2: ...
]


def detect_section(text: str) -> str:
    """Extract the most recent section heading from chunk text."""
    for pattern in SECTION_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            # Return the last match (most recent heading in the chunk)
            return matches[-1].strip().strip("#").strip()
    return ""


def chunk_documents(
    documents: List[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[Document]:
    """
    Split documents into chunks with enriched metadata.

    Each chunk gets:
    - source_file: original filename
    - doc_type: inferred document type
    - section: detected section heading within the chunk
    - page_number: page number (for PDFs) or chunk index
    - chunk_index: sequential index within the document
    - date: original document date
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_chunks = []
    # Group documents by source file for chunk indexing
    source_groups: dict = {}
    for doc in documents:
        source = doc.metadata.get("source", "unknown")
        if source not in source_groups:
            source_groups[source] = []
        source_groups[source].append(doc)

    for source, docs in source_groups.items():
        chunks = splitter.split_documents(docs)

        for i, chunk in enumerate(chunks):
            # Enrich metadata
            chunk.metadata["chunk_index"] = i
            chunk.metadata["source_file"] = chunk.metadata.get("source", source)

            # Section detection
            section = detect_section(chunk.page_content)
            if section:
                chunk.metadata["section"] = section

            # Page number: use existing page metadata (from PDF) or derive from chunk index
            if "page" in chunk.metadata:
                chunk.metadata["page_number"] = chunk.metadata["page"]
            else:
                chunk.metadata["page_number"] = i // 3  # Approximate 3 chunks per "page"

            all_chunks.append(chunk)

    print(f"  Chunked {len(documents)} documents into {len(all_chunks)} chunks "
          f"(size={chunk_size}, overlap={chunk_overlap})")
    return all_chunks


def chunk_text(
    text: str,
    metadata: Optional[dict] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[Document]:
    """Chunk a raw text string into Documents."""
    doc = Document(page_content=text, metadata=metadata or {})
    return chunk_documents([doc], chunk_size=chunk_size, chunk_overlap=chunk_overlap)
