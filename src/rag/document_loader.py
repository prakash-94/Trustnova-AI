"""
Document Loader Pipeline for the Banking AI RAG System.

Loads banking documents from multiple formats, chunks them,
and indexes into the configured vector store.

Supported formats: TXT, PDF, CSV, JSON
Uses: chunker.py (splitting), embeddings.py (vectors), vector_store.py (storage)
"""
import os
import sys
import glob
import json as json_lib
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_community.document_loaders import TextLoader, PyPDFLoader, CSVLoader

from src.rag.chunker import chunk_documents
from src.rag.vector_store import index_documents, index_interactions

load_dotenv()

# --- Configuration ---
DOCS_DIR = os.getenv("DOCS_DIR", "data/raw/banking_docs")


def get_doc_type(filename: str) -> str:
    """Infer document type from filename."""
    name = filename.lower()
    if "faq" in name:
        return "faq"
    elif "loan" in name:
        return "loan_policy"
    elif "compliance" in name:
        return "compliance"
    elif "savings" in name or "deposit" in name:
        return "product_sheet"
    elif "credit" in name:
        return "product_sheet"
    elif "mortgage" in name:
        return "mortgage"
    elif "digital" in name or "mobile" in name:
        return "digital_banking"
    elif "wire" in name or "international" in name:
        return "wire_transfer"
    elif "business" in name:
        return "business_banking"
    elif "wealth" in name or "investment" in name:
        return "wealth_management"
    elif "fee" in name:
        return "fee_schedule"
    else:
        return "general"


def _add_metadata(docs: List[Document], filepath: str) -> List[Document]:
    """Add standard metadata to loaded documents."""
    filename = os.path.basename(filepath)
    doc_type = get_doc_type(filename)
    modified = datetime.fromtimestamp(os.path.getmtime(filepath))
    for doc in docs:
        doc.metadata["source"] = filename
        doc.metadata["source_file"] = filename
        doc.metadata["doc_type"] = doc_type
        doc.metadata["date"] = modified.strftime("%Y-%m-%d")
        doc.metadata["effective_date"] = modified.strftime("%Y-%m-%d")
        doc.metadata["document_version"] = modified.strftime("%Y%m%d%H%M%S")
        doc.metadata["last_modified"] = modified.isoformat()
        doc.metadata["access_scope"] = "internal"
    return docs


def load_txt_files(docs_dir: str) -> List[Document]:
    """Load all .txt files from the docs directory."""
    documents = []
    for filepath in sorted(glob.glob(os.path.join(docs_dir, "*.txt"))):
        try:
            loader = TextLoader(filepath, encoding="utf-8")
            docs = loader.load()
            documents.extend(_add_metadata(docs, filepath))
            print(f"    [OK] {os.path.basename(filepath)}")
        except Exception as e:
            print(f"    [ERR] {os.path.basename(filepath)}: {e}")
    return documents


def load_pdf_files(docs_dir: str) -> List[Document]:
    """Load all .pdf files from the docs directory."""
    documents = []
    for filepath in sorted(glob.glob(os.path.join(docs_dir, "*.pdf"))):
        try:
            loader = PyPDFLoader(filepath)
            docs = loader.load()
            documents.extend(_add_metadata(docs, filepath))
            print(f"    [OK] {os.path.basename(filepath)}")
        except Exception as e:
            print(f"    [ERR] {os.path.basename(filepath)}: {e}")
    return documents


def load_csv_files(docs_dir: str) -> List[Document]:
    """Load all .csv files from the docs directory."""
    documents = []
    for filepath in sorted(glob.glob(os.path.join(docs_dir, "*.csv"))):
        try:
            loader = CSVLoader(filepath, encoding="utf-8")
            docs = loader.load()
            documents.extend(_add_metadata(docs, filepath))
            print(f"    [OK] {os.path.basename(filepath)}")
        except Exception as e:
            print(f"    [ERR] {os.path.basename(filepath)}: {e}")
    return documents


def load_json_files(docs_dir: str) -> List[Document]:
    """Load all .json files from the docs directory."""
    documents = []
    for filepath in sorted(glob.glob(os.path.join(docs_dir, "*.json"))):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json_lib.load(f)

            # Handle different JSON structures
            if isinstance(data, list):
                # Array of objects - each object becomes a document
                for item in data:
                    text = json_lib.dumps(item, indent=2) if isinstance(item, dict) else str(item)
                    doc = Document(page_content=text)
                    documents.append(doc)
            elif isinstance(data, dict):
                # Single object - entire content becomes one document
                doc = Document(page_content=json_lib.dumps(data, indent=2))
                documents.append(doc)
            else:
                doc = Document(page_content=str(data))
                documents.append(doc)

            documents = _add_metadata(documents, filepath)
            print(f"    [OK] {os.path.basename(filepath)}")
        except Exception as e:
            print(f"    [ERR] {os.path.basename(filepath)}: {e}")
    return documents


def load_documents(docs_dir: str = DOCS_DIR) -> List[Document]:
    """Load all supported document types from the docs directory."""
    documents = []

    print("  TXT files:")
    documents.extend(load_txt_files(docs_dir))

    print("  PDF files:")
    pdf_docs = load_pdf_files(docs_dir)
    if not pdf_docs:
        print("    (none found)")
    documents.extend(pdf_docs)

    print("  CSV files:")
    csv_docs = load_csv_files(docs_dir)
    if not csv_docs:
        print("    (none found)")
    documents.extend(csv_docs)

    print("  JSON files:")
    json_docs = load_json_files(docs_dir)
    if not json_docs:
        print("    (none found)")
    documents.extend(json_docs)

    return documents


def load_from_upload(filepath: str) -> List[Document]:
    """
    Load a single uploaded file (used by the /documents/upload API endpoint).

    Args:
        filepath: Absolute path to the uploaded file

    Returns:
        List of Document objects
    """
    ext = os.path.splitext(filepath)[1].lower()
    documents = []

    try:
        if ext == ".txt":
            loader = TextLoader(filepath, encoding="utf-8")
            documents = loader.load()
        elif ext == ".pdf":
            loader = PyPDFLoader(filepath)
            documents = loader.load()
        elif ext == ".csv":
            loader = CSVLoader(filepath, encoding="utf-8")
            documents = loader.load()
        elif ext == ".json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json_lib.load(f)
            if isinstance(data, list):
                for item in data:
                    text = json_lib.dumps(item, indent=2) if isinstance(item, dict) else str(item)
                    documents.append(Document(page_content=text))
            else:
                documents.append(Document(page_content=json_lib.dumps(data, indent=2)))
        else:
            # Attempt as plain text
            with open(filepath, "r", encoding="utf-8") as f:
                documents.append(Document(page_content=f.read()))

        documents = _add_metadata(documents, filepath)
    except Exception as e:
        print(f"  Error loading {filepath}: {e}")

    return documents


def run_ingestion(docs_dir: str = DOCS_DIR):
    """
    Full document ingestion pipeline.

    1. Load all documents from docs_dir
    2. Chunk them with metadata
    3. Index document chunks into vector store
    4. Index banker notes and complaint transcripts
    """
    print("=" * 60)
    print("Banking AI - Document Ingestion Pipeline")
    print("=" * 60)

    # Step 1: Load documents
    print("\n[1/4] Loading documents...")
    documents = load_documents(docs_dir)
    if not documents:
        print("No documents found. Exiting.")
        return

    print(f"\n  Total documents loaded: {len(documents)}")

    # Step 2: Chunk documents
    print("\n[2/4] Chunking documents...")
    chunks = chunk_documents(documents)

    # Step 3: Index document chunks
    print("\n[3/4] Indexing document chunks...")
    doc_count = index_documents(chunks)

    # Step 4: Index banker notes and complaints
    print("\n[4/4] Indexing banker notes and complaints...")
    interaction_count = index_interactions()

    print("\n" + "=" * 60)
    print("Document ingestion complete!")
    print(f"  Documents loaded:       {len(documents)}")
    print(f"  Document chunks:        {doc_count}")
    print(f"  Interaction records:    {interaction_count}")
    print("=" * 60)

    return {
        "documents_loaded": len(documents),
        "chunks_created": doc_count,
        "interactions_indexed": interaction_count,
    }


if __name__ == "__main__":
    run_ingestion()
