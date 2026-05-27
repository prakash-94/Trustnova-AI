"""
Trust Scoring Route — Customer trust score + AI trust score endpoints.

Layer 1: Customer Trust Score — uses TrustScoreCalculator (weighted 5-component formula).
Layer 2: AI Trust Score — uses AITrustScorer (5-metric AI response quality score).

Both layers store score history in SQLite for audit and trend analysis.
"""
import traceback

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

router = APIRouter()


# ──────────────────────────────────────────────────────────────
# Response Models
# ──────────────────────────────────────────────────────────────

class TrustScoreResponse(BaseModel):
    """Response body for customer trust score endpoint."""
    status: str
    customer_id: Optional[str] = None
    score: Optional[float] = None
    tier: Optional[str] = None
    components: Optional[dict] = None
    weights: Optional[dict] = None
    fraud_incidents: Optional[int] = None
    total_interactions: Optional[int] = None
    error: Optional[str] = None


class TrustHistoryResponse(BaseModel):
    """Response body for trust score history endpoint."""
    status: str
    customer_id: Optional[str] = None
    history: Optional[List[dict]] = None
    error: Optional[str] = None


class AITrustHistoryResponse(BaseModel):
    """Response body for AI trust score history endpoint."""
    status: str
    session_id: Optional[str] = None
    history: Optional[List[dict]] = None
    error: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Layer 1: Customer Trust Score
# ──────────────────────────────────────────────────────────────

@router.get("/score/{customer_id}", response_model=TrustScoreResponse)
async def get_trust_score(customer_id: str):
    """
    Get the trust score for a customer.

    Returns a composite score (0-100) based on 5 weighted components:
    - account_age (20%) — older accounts score higher
    - credit_score (30%) — 300-850 mapped to 0-100
    - fraud_history (25%) — penalizes fraud incidents
    - sentiment_avg (15%) — average interaction sentiment
    - interaction_count (10%) — engagement level

    Tiers: High Risk (0-40) · Moderate (41-70) · Trusted (71-100).
    """
    try:
        from src.models.trust_scorer import TrustScoreCalculator

        calculator = TrustScoreCalculator()
        result = calculator.calculate(customer_id)

        if "error" in result:
            return TrustScoreResponse(
                status="not_found",
                customer_id=customer_id,
                error=result.get("error", "Customer not found"),
            )

        return TrustScoreResponse(
            status="ok",
            customer_id=customer_id,
            score=result["score"],
            tier=result["tier"],
            components=result.get("components"),
            weights=result.get("weights"),
            fraud_incidents=result.get("fraud_incidents"),
            total_interactions=result.get("total_interactions"),
        )

    except Exception as e:
        traceback.print_exc()
        return TrustScoreResponse(
            status="error",
            customer_id=customer_id,
            error=f"Error computing trust score: {str(e)}",
        )


@router.get("/history/{customer_id}", response_model=TrustHistoryResponse)
async def get_trust_history(customer_id: str, limit: int = 10):
    """
    Get historical trust scores for a customer.

    Returns the last N trust score calculations with timestamps,
    useful for trend analysis and audit.
    """
    try:
        from src.models.trust_scorer import TrustScoreCalculator

        calculator = TrustScoreCalculator()
        history = calculator.get_score_history(customer_id, limit=limit)

        return TrustHistoryResponse(
            status="ok",
            customer_id=customer_id,
            history=history,
        )

    except Exception as e:
        traceback.print_exc()
        return TrustHistoryResponse(
            status="error",
            customer_id=customer_id,
            error=f"Error retrieving trust history: {str(e)}",
        )


# ──────────────────────────────────────────────────────────────
# Layer 2: AI Trust Score History
# ──────────────────────────────────────────────────────────────

@router.get("/ai-history", response_model=AITrustHistoryResponse)
async def get_ai_trust_history(session_id: str = None, limit: int = 20):
    """
    Get historical AI response trust scores.

    Optionally filter by session_id. Returns the last N AI trust score
    calculations with all 5 component metrics and timestamps.
    """
    try:
        from src.models.ai_trust import get_ai_trust_scorer

        scorer = get_ai_trust_scorer()
        history = scorer.get_score_history(session_id=session_id, limit=limit)

        return AITrustHistoryResponse(
            status="ok",
            session_id=session_id,
            history=history,
        )

    except Exception as e:
        traceback.print_exc()
        return AITrustHistoryResponse(
            status="error",
            session_id=session_id,
            error=f"Error retrieving AI trust history: {str(e)}",
        )
