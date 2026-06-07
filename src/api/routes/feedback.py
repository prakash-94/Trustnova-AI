"""
Feedback Route — Enhanced banker feedback collection + analysis endpoints.

Phase 8 endpoints:
  POST /feedback          — Submit feedback (stores in ai_feedback + session + self-improvement)
  GET  /feedback/stats    — Get overall feedback stats
  GET  /feedback/report   — Generate weekly quality report
  GET  /feedback/retrieval-health — Retrieval chunk quality report
  GET  /feedback/prompt-health    — Prompt template health report
"""
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from src.api.auth import CurrentUser, require_permission, get_current_user

router = APIRouter()


class FeedbackRequest(BaseModel):
    """Request body for the feedback endpoint."""
    session_id: str = Field(..., description="Session ID the feedback belongs to")
    response_id: str = Field(..., description="ID of the AI response being rated")
    feedback_type: str = Field(
        ...,
        description="Type of feedback: 'approve', 'reject', or 'edit'",
        pattern="^(approve|reject|edit)$",
    )
    correction_text: Optional[str] = Field("", description="Banker's corrected text (for 'edit' type)")
    prompt: Optional[str] = Field("", description="The original prompt that generated the response")
    response_text: Optional[str] = Field("", description="The AI response that was rated")
    model_used: Optional[str] = Field("", description="The LLM model that generated the response")
    trust_score: Optional[float] = Field(0.0, description="AI trust score of the response")
    retrieved_chunks: Optional[List[str]] = Field(None, description="Source chunks used in RAG context")
    doc_type: Optional[str] = Field("", description="Document type(s) referenced")
    prompt_template: Optional[str] = Field("general", description="Which prompt template was used")

    model_config = {"json_schema_extra": {
        "examples": [{
            "session_id": "session_001",
            "response_id": "resp_abc123",
            "feedback_type": "reject",
            "correction_text": "The correct AML threshold is $10,000, not $5,000.",
            "prompt": "What is the AML reporting threshold?",
            "response_text": "The AML reporting threshold is $5,000.",
            "model_used": "gpt-4",
            "trust_score": 72.5,
            "retrieved_chunks": ["AML Policy Section 4.2: ..."],
            "doc_type": "compliance",
            "prompt_template": "compliance_qa",
        }]
    }}


class FeedbackResponse(BaseModel):
    """Response body for the feedback endpoint."""
    status: str
    feedback_type: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: Optional[str] = None
    stats: Optional[dict] = None
    report: Optional[dict] = None
    error: Optional[str] = None


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: CurrentUser = Depends(require_permission("feedback")),
):
    """
    Submit feedback on an AI response.

    Supports three feedback types:
    - **approve**: The response was accurate and helpful
    - **reject**: The response was inaccurate or unhelpful
    - **edit**: The response needed corrections (include corrected text)

    Feedback is stored in:
    1. ai_feedback table (full context for analysis)
    2. Session memory (conversation history)
    3. Self-improvement feedback table (for model retraining)
    4. Chunk feedback (retrieval optimizer)
    """
    try:
        from src.feedback.ai_feedback_store import AIFeedbackStore
        from src.feedback.retrieval_optimizer import RetrievalOptimizer
        from src.api.memory import get_memory
        from src.models.self_improvement import SelfImprovementLoop

        # 1. Store in AI feedback table (Phase 8)
        store = AIFeedbackStore()
        store.store(
            session_id=request.session_id,
            response_id=request.response_id,
            feedback_type=request.feedback_type,
            prompt=request.prompt or "",
            response_text=request.response_text or "",
            model_used=request.model_used or "",
            trust_score=request.trust_score or 0.0,
            correction_text=request.correction_text or "",
            retrieved_chunks=request.retrieved_chunks or [],
            doc_type=request.doc_type or "",
            prompt_template=request.prompt_template or "general",
        )

        # 2. Store in session memory
        memory = get_memory()
        memory.store_feedback(
            session_id=request.session_id,
            response_id=request.response_id,
            feedback_type=request.feedback_type,
            prompt=request.prompt or "",
            model_used=request.model_used or "",
            trust_score=request.trust_score or 0.0,
            correction_text=request.correction_text or "",
        )

        # 3. Record in self-improvement feedback table
        loop = SelfImprovementLoop()
        loop.record_feedback(
            txn_id=request.response_id,
            predicted_fraud=request.trust_score or 0.0,
            banker_says_fraud=(request.feedback_type == "reject"),
            notes=f"[{request.feedback_type}] {request.correction_text or 'No correction text'}",
        )

        # 4. Update retrieval optimizer chunk weights
        if request.retrieved_chunks:
            optimizer = RetrievalOptimizer()
            optimizer.log_feedback_for_chunks(
                chunks=request.retrieved_chunks,
                feedback_type=request.feedback_type,
            )

        # Get updated stats
        stats = loop.get_feedback_stats()

        return FeedbackResponse(
            status="ok",
            feedback_type=request.feedback_type,
            session_id=request.session_id,
            timestamp=datetime.now().isoformat(),
            stats=stats,
        )

    except Exception as e:
        traceback.print_exc()
        return FeedbackResponse(
            status="error",
            error=f"Feedback submission error: {str(e)}",
        )


@router.get("/stats", response_model=FeedbackResponse)
async def get_feedback_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get feedback statistics summary.

    Returns total feedback count, agreement rate, and
    breakdown of feedback types.
    """
    try:
        from src.models.self_improvement import SelfImprovementLoop

        loop = SelfImprovementLoop()
        stats = loop.get_feedback_stats()

        return FeedbackResponse(
            status="ok",
            stats=stats,
        )

    except Exception as e:
        traceback.print_exc()
        return FeedbackResponse(
            status="error",
            error=f"Error retrieving feedback stats: {str(e)}",
        )


@router.get("/report", response_model=FeedbackResponse)
async def get_feedback_report(
    days: int = 7,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Generate a weekly feedback quality report.

    Analyzes rejection rates per model, prompt template, and doc type.
    Triggers alerts if any category exceeds 20% rejection rate.
    """
    try:
        from src.feedback.analyzer import FeedbackAnalyzer

        analyzer = FeedbackAnalyzer()
        report = analyzer.weekly_report(days=days)

        return FeedbackResponse(
            status="ok",
            report=report,
        )

    except Exception as e:
        traceback.print_exc()
        return FeedbackResponse(
            status="error",
            error=f"Error generating report: {str(e)}",
        )


@router.get("/retrieval-health", response_model=FeedbackResponse)
async def get_retrieval_health(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get retrieval chunk quality health report.

    Shows chunk feedback weight distribution, downranked and boosted
    chunks, and overall retrieval quality metrics.
    """
    try:
        from src.feedback.retrieval_optimizer import RetrievalOptimizer

        optimizer = RetrievalOptimizer()
        report = optimizer.get_health_report()
        downranked = optimizer.get_downranked_chunks()

        return FeedbackResponse(
            status="ok",
            report={
                **report,
                "downranked_chunks": downranked[:10],
            },
        )

    except Exception as e:
        traceback.print_exc()
        return FeedbackResponse(
            status="error",
            error=f"Error getting retrieval health: {str(e)}",
        )


@router.get("/prompt-health", response_model=FeedbackResponse)
async def get_prompt_health(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get prompt template health report.

    Shows per-template rejection rates, suggestions generated,
    and templates needing optimization (10+ rejections).
    """
    try:
        from src.feedback.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        health = optimizer.get_prompt_health()
        suggestions = optimizer.get_suggestion_history()

        return FeedbackResponse(
            status="ok",
            report={
                **health,
                "recent_suggestions": suggestions[:10],
            },
        )

    except Exception as e:
        traceback.print_exc()
        return FeedbackResponse(
            status="error",
            error=f"Error getting prompt health: {str(e)}",
        )
