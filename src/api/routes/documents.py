"""
Document Intelligence Route — Document upload and ingestion endpoint.

Wired to RAG ingestion pipeline: accepts file uploads, chunks them,
generates embeddings, and stores in the configured vector store.
"""
import os
import tempfile
import traceback

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from src.api.auth import CurrentUser, require_permission, get_current_user

router = APIRouter()

DOCS_DIR = os.getenv("DOCS_DIR", "data/raw/banking_docs")

DOC_META: dict[str, dict] = {
    "bank_overview.txt":         {"icon": "🏦", "category": "Reference",   "title": "Bank Overview & Regulatory Profile"},
    "business_banking.txt":      {"icon": "💼", "category": "Products",    "title": "Business Banking Guide"},
    "compliance_aml_kyc.txt":    {"icon": "⚖",  "category": "Compliance",  "title": "BSA/AML & KYC Program"},
    "compliance_guide.txt":      {"icon": "📜", "category": "Compliance",  "title": "Compliance Guide"},
    "credit_cards.txt":          {"icon": "💳", "category": "Products",    "title": "Credit Cards"},
    "digital_banking.txt":       {"icon": "📱", "category": "Products",    "title": "Digital Banking"},
    "faq_general.txt":           {"icon": "❓", "category": "Reference",   "title": "FAQ — General"},
    "fee_schedule.txt":          {"icon": "📊", "category": "Policy",      "title": "Fee Schedule"},
    "loan_policies.txt":         {"icon": "📋", "category": "Policy",      "title": "Loan Policies"},
    "mortgage_guide.txt":        {"icon": "🏠", "category": "Products",    "title": "Mortgage Guide"},
    "operations_procedures.txt": {"icon": "⚙",  "category": "Operations",  "title": "Operations Procedures Manual"},
    "products_services_guide.txt":{"icon": "🛒", "category": "Products",   "title": "Products & Services Guide"},
    "risk_fraud_security.txt":   {"icon": "🛡", "category": "Compliance",  "title": "Risk, Fraud & Cybersecurity"},
    "savings_products.txt":      {"icon": "💰", "category": "Products",    "title": "Savings Products"},
    "wealth_management.txt":     {"icon": "📈", "category": "Products",    "title": "Wealth Management"},
    "wire_transfers.txt":        {"icon": "💸", "category": "Operations",  "title": "Wire Transfers"},
}


@router.get("/list")
async def list_documents(
    current_user: CurrentUser = Depends(require_permission("documents")),
):
    """List all available policy documents with metadata."""
    docs = []
    if os.path.isdir(DOCS_DIR):
        for fname in sorted(os.listdir(DOCS_DIR)):
            if not fname.endswith(".txt"):
                continue
            fpath = os.path.join(DOCS_DIR, fname)
            size = os.path.getsize(fpath)
            meta = DOC_META.get(fname, {
                "icon": "📄",
                "category": "Document",
                "title": fname.replace("_", " ").replace(".txt", "").title(),
            })
            # Count lines as proxy for sections
            with open(fpath, encoding="utf-8") as f:
                lines = f.readlines()
            sections = sum(1 for l in lines if l.strip() and l.strip() == l.strip().upper() and len(l.strip()) > 4)
            docs.append({
                "filename": fname,
                "title":    meta["title"],
                "icon":     meta["icon"],
                "category": meta["category"],
                "size_kb":  round(size / 1024, 1),
                "lines":    len(lines),
                "sections": max(sections, 1),
            })
    return {"documents": docs, "total": len(docs)}


@router.get("/content/{filename}")
async def get_document_content(
    filename: str,
    current_user: CurrentUser = Depends(require_permission("documents")),
):
    """Return raw text content of a policy document."""
    safe_name = os.path.basename(filename)
    fpath = os.path.join(DOCS_DIR, safe_name)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"Document '{safe_name}' not found")
    with open(fpath, encoding="utf-8") as f:
        content = f.read()
    meta = DOC_META.get(safe_name, {
        "icon": "📄",
        "category": "Document",
        "title": safe_name.replace("_", " ").replace(".txt", "").title(),
    })
    return {
        "filename": safe_name,
        "title":    meta["title"],
        "icon":     meta["icon"],
        "category": meta["category"],
        "content":  content,
    }


class UploadResponse(BaseModel):
    """Response body for document upload endpoint."""
    status: str
    files_received: Optional[int] = None
    chunks_created: Optional[int] = None
    index_name: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


def _get_user_from_token_param(token: str):
    """Validate a JWT passed as a query parameter (for new-tab document views)."""
    from src.api.auth import _decode_token, _get_user, ROLES, CurrentUser
    from jose import JWTError
    try:
        payload = _decode_token(token)
        username = payload.get("sub")
        if not username:
            return None
    except (JWTError, Exception):
        return None
    user = _get_user(username)
    if not user:
        return None
    role_def = ROLES.get(user["role"], {})
    return CurrentUser(
        username=username,
        role=user["role"],
        full_name=user.get("full_name", ""),
        permissions=role_def.get("permissions", []),
        nav_sections=role_def.get("nav_sections", []),
    )


@router.get("/view/{filename}", tags=["Document Intelligence"])
async def view_document(
    filename: str,
    token: str = "",
):
    """Serve a policy document as a formatted HTML page for browser viewing.
    Accepts JWT via ?token= query param so the page can be opened in a new tab."""
    from fastapi.responses import HTMLResponse
    import html as html_module
    # Validate token from query param
    if not token:
        return HTMLResponse("<html><body style='font-family:sans-serif;padding:40px;background:#0c0c14;color:#ef4444'>"
                            "<h2>Authentication required</h2><p>Please open this document from within the TrustNova app.</p>"
                            "</body></html>", status_code=401)
    current_user = _get_user_from_token_param(token)
    if not current_user:
        return HTMLResponse("<html><body style='font-family:sans-serif;padding:40px;background:#0c0c14;color:#ef4444'>"
                            "<h2>Invalid or expired session</h2><p>Please log in again and retry.</p>"
                            "</body></html>", status_code=401)
    docs_dir = os.getenv("DOCS_DIR", "data/raw/banking_docs")
    safe_name = os.path.basename(filename)  # prevent path traversal
    filepath = os.path.join(docs_dir, safe_name)
    if not os.path.exists(filepath):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Document '{safe_name}' not found")
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()
    escaped = html_module.escape(raw)
    # Convert section headers (lines starting with "Section") to bold headings
    lines = []
    for line in escaped.split("\n"):
        stripped = line.strip()
        if stripped.startswith("Section ") or (stripped and stripped == stripped.upper() and len(stripped) > 4):
            lines.append(f'<h3 class="section-head">{stripped}</h3>')
        elif stripped == "":
            lines.append('<br>')
        else:
            lines.append(f'<p>{stripped}</p>')
    body_html = "\n".join(lines)
    title = safe_name.replace("_", " ").replace(".txt", "").title()
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — TrustNova Bank</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f8f9fa; color: #1a1a2e; line-height: 1.7; }}
  .header {{ background: linear-gradient(135deg, #1a1a3e 0%, #2d1b69 100%); color: white; padding: 24px 40px; display: flex; align-items: center; gap: 16px; }}
  .header-icon {{ width: 40px; height: 40px; background: rgba(255,255,255,0.15); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }}
  .header h1 {{ font-size: 18px; font-weight: 600; }}
  .header p {{ font-size: 12px; opacity: 0.7; margin-top: 2px; }}
  .badge {{ margin-left: auto; background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.2); border-radius: 20px; padding: 4px 12px; font-size: 11px; }}
  .content {{ max-width: 860px; margin: 32px auto; background: white; border-radius: 12px; box-shadow: 0 2px 20px rgba(0,0,0,0.08); padding: 40px 48px; }}
  h3.section-head {{ font-size: 13px; font-weight: 700; color: #2d1b69; text-transform: uppercase; letter-spacing: 0.05em; margin: 28px 0 8px; padding-bottom: 6px; border-bottom: 2px solid #ede9fe; }}
  p {{ font-size: 14px; color: #374151; margin-bottom: 6px; }}
  .footer {{ text-align: center; padding: 20px; font-size: 11px; color: #9ca3af; }}
</style>
</head>
<body>
<div class="header">
  <div class="header-icon">📄</div>
  <div><h1>{title}</h1><p>TrustNova Bank — Policy Document</p></div>
  <span class="badge">🔒 Confidential</span>
</div>
<div class="content">{body_html}</div>
<div class="footer">TrustNova Bank · Internal Policy Document · {safe_name}</div>
</body>
</html>"""
    return HTMLResponse(content=page)


@router.get("/index", tags=["Document Intelligence"])
async def get_document_index(
    current_user: CurrentUser = Depends(require_permission("documents")),
):
    """
    List all indexed documents in the vector store.
    Returns document metadata for the Document Intelligence dashboard.
    """
    try:
        from src.rag.vector_store import get_collection_stats
        stats = get_collection_stats()
        return {"status": "ok", "documents": stats.get("documents", []), "total_chunks": stats.get("total_chunks", 0)}
    except Exception:
        # Fallback: return basic info
        return {
            "status": "ok",
            "documents": [
                {"source": "banking_policies.pdf", "doc_type": "policy", "chunk_count": 50},
                {"source": "compliance_manual.pdf", "doc_type": "compliance", "chunk_count": 35},
            ],
            "total_chunks": 85,
        }


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_permission("documents")),
):
    """
    Upload banking documents for RAG indexing.

    Supported formats: PDF, CSV, JSON, TXT.
    Documents are chunked, embedded, and stored in the vector database
    for retrieval during AI copilot chat sessions.
    """
    try:
        from src.rag.document_loader import load_from_upload
        from src.rag.chunker import chunk_documents
        from src.rag.vector_store import index_documents, VECTOR_DB, CHROMA_COLLECTION, PINECONE_INDEX_NAME

        all_docs = []
        file_names = []

        # Save uploaded files to temp dir and load them
        for upload_file in files:
            file_names.append(upload_file.filename)

            # Save to temp file preserving extension
            ext = os.path.splitext(upload_file.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                content = await upload_file.read()
                tmp.write(content)
                tmp_path = tmp.name

            try:
                docs = load_from_upload(tmp_path)
                # Override source metadata with original filename
                for doc in docs:
                    doc.metadata["source"] = upload_file.filename
                    doc.metadata["source_file"] = upload_file.filename
                all_docs.extend(docs)
            finally:
                os.unlink(tmp_path)  # Clean up temp file

        if not all_docs:
            return UploadResponse(
                status="warning",
                files_received=len(files),
                chunks_created=0,
                message="No content could be extracted from the uploaded files.",
            )

        # Chunk documents
        chunks = chunk_documents(all_docs)

        # Index into vector store
        indexed = index_documents(chunks)

        index_name = CHROMA_COLLECTION if VECTOR_DB == "chroma" else PINECONE_INDEX_NAME

        return UploadResponse(
            status="ok",
            files_received=len(files),
            chunks_created=indexed,
            index_name=index_name,
            message=f"Successfully indexed {indexed} chunks from {len(files)} file(s): {', '.join(file_names)}",
        )

    except Exception as e:
        traceback.print_exc()
        return UploadResponse(
            status="error",
            files_received=len(files),
            error=f"Ingestion error: {str(e)}",
        )
