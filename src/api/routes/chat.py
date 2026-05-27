"""
Chat Route — AI Copilot conversation endpoint.

Wired to RAG QA chain for banking document retrieval with source citations.
Supports optional customer context enrichment.
Integrates with:
  - Phase 4: session memory (DB-backed) and LLM router
  - Phase 6: AI Trust Scoring — real-time trust score on every response
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import traceback

router = APIRouter()


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""
    question: str = Field(..., description="The banker's question to the AI copilot")
    customer_id: Optional[str] = Field(None, description="Optional customer ID for context-aware answers")
    session_id: Optional[str] = Field(None, description="Session ID for conversation memory")

    model_config = {"json_schema_extra": {
        "examples": [{
            "question": "What is the AML policy for transactions over $10,000?",
            "customer_id": "abc12345",
            "session_id": "session_001"
        }]
    }}


class SourceInfo(BaseModel):
    """Source citation info."""
    source: str
    doc_type: str = ""
    section: str = ""
    text_preview: str = ""


class ChatResponse(BaseModel):
    """
    Response body for the chat endpoint.

    Includes full evidence display per Phase 6 spec:
    - answer: The AI-generated response
    - sources: Cited document sources
    - retrieved_chunks: Raw text chunks used for context
    - ai_trust_score: Composite trust score (0-100)
    - trust_components: Breakdown of all 5 trust metrics
    - session_id: Conversation session ID
    - model_used: LLM model that generated the answer
    """
    status: str
    answer: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    retrieved_chunks: Optional[List[str]] = None
    ai_trust_score: Optional[float] = None
    trust_components: Optional[Dict[str, float]] = None
    trust_tier: Optional[str] = None
    session_id: Optional[str] = None
    model_used: Optional[str] = None
    error: Optional[str] = None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    AI Copilot Chat — ask banking questions with RAG-powered responses.

    Returns cited answers from banking documents, customer records,
    and interaction history. Supports conversation memory via session_id.

    Every response includes:
    - Source citations with document references
    - AI Trust Score (0-100) with 5-component breakdown
    - Retrieved source chunks for evidence transparency
    """
    try:
        from src.rag.qa_chain import ask_single_question
        from src.rag.customer_context import format_customer_context, get_full_customer_context
        from src.api.memory import get_memory
        from src.models.ai_trust import get_ai_trust_scorer

        memory = get_memory()

        # Create or retrieve session
        session_id = request.session_id
        if session_id:
            # Store the user's question in session memory
            memory.append_to_session(session_id, "user", request.question)
        else:
            # Auto-create a session for tracking
            session_id = memory.create_session(
                customer_id=request.customer_id or "",
            )
            memory.append_to_session(session_id, "user", request.question)

        # Build customer context if customer_id provided
        customer_context = ""
        if request.customer_id:
            ctx = get_full_customer_context(request.customer_id)
            if "error" not in ctx:
                customer_context = format_customer_context(ctx)

        # Query RAG system — returns answer, sources, retrieved_chunks, similarity_scores
        result = ask_single_question(
            question=request.question,
            customer_context=customer_context,
        )

        sources = [
            SourceInfo(
                source=s.get("source", "unknown"),
                doc_type=s.get("doc_type", ""),
                section=s.get("section", ""),
                text_preview=s.get("text_preview", ""),
            )
            for s in result.get("sources", [])
        ]

        answer = result["answer"]
        retrieved_chunks = result.get("retrieved_chunks", [])
        similarity_scores = result.get("similarity_scores", [])

        # ─── Phase 6: AI Trust Scoring ────────────────────────────
        # Compute real-time trust score for this response
        ai_trust_scorer = get_ai_trust_scorer()
        trust_result = ai_trust_scorer.score(
            query=request.question,
            answer=answer,
            source_chunks=retrieved_chunks,
            similarity_scores=similarity_scores,
            session_id=session_id,
            model_used="gpt-4",
        )

        ai_trust_score = trust_result.get("final_score", 0.0)
        trust_components = trust_result.get("components", {})
        trust_tier = trust_result.get("tier", "Unknown")

        # Store assistant response in session memory
        memory.append_to_session(
            session_id, "assistant", answer,
            model_used="gpt-4",
        )

        return ChatResponse(
            status="ok",
            answer=answer,
            sources=sources,
            retrieved_chunks=retrieved_chunks,
            ai_trust_score=ai_trust_score,
            trust_components=trust_components,
            trust_tier=trust_tier,
            session_id=session_id,
            model_used="gpt-4",
        )

    except Exception as e:
        traceback.print_exc()
        return ChatResponse(
            status="error",
            answer=None,
            sources=None,
            error=f"RAG system error: {str(e)}. Ensure documents are indexed (run: python -m src.rag.document_loader).",
        )
