"""
Trust Scoring Route — Customer trust score + AI trust score endpoints.

Layer 1: Customer Trust Score — uses TrustScoreCalculator (weighted 5-component formula).
Layer 2: AI Trust Score — uses AITrustScorer (5-metric AI response quality score).

Both layers store score history in SQLite for audit and trend analysis.
"""
import traceback

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

from src.api.auth import CurrentUser, get_current_user, log_audit

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
async def get_trust_score(
    customer_id: str,
    http_request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get the trust score for a customer.

    Returns a composite score (0-100) based on 5 weighted components:
    - account_age (20%), credit_score (30%), fraud_history (25%),
      sentiment_avg (15%), interaction_count (10%)

    Tiers: High Risk (0-40) · Moderate (41-70) · Trusted (71-100).
    """
    from sqlalchemy import text as sql_text
    from src.models.database import engine as _engine

    ip = http_request.client.host if http_request and http_request.client else ""
    log_audit(current_user.username, current_user.role, "read", "trust_score",
              resource_id=customer_id, customer_id=customer_id, ip=ip)

    # --- 1. Try cached score from trust_scores table (fast path) ---
    try:
        with _engine.connect() as conn:
            cached = conn.execute(sql_text("""
                SELECT score, tier,
                       account_age_component, credit_score_component,
                       fraud_history_component, sentiment_component,
                       interaction_component
                FROM trust_scores
                WHERE customer_id = :cid
                ORDER BY timestamp DESC LIMIT 1
            """), {"cid": customer_id}).fetchone()

        if cached:
            c = dict(cached._mapping)
            return TrustScoreResponse(
                status="ok",
                customer_id=customer_id,
                score=c["score"],
                tier=c["tier"],
                components={
                    "account_age":      c.get("account_age_component"),
                    "credit_score":     c.get("credit_score_component"),
                    "fraud_history":    c.get("fraud_history_component"),
                    "sentiment_avg":    c.get("sentiment_component"),
                    "interaction_count": c.get("interaction_component"),
                },
                weights={
                    "account_age": 0.20, "credit_score": 0.30,
                    "fraud_history": 0.25, "sentiment_avg": 0.15,
                    "interaction_count": 0.10,
                },
                fraud_incidents=None,
                total_interactions=None,
            )
    except Exception:
        pass  # fall through to live calculation

    # --- 2. Live calculation — inline, using the main engine (DB-agnostic) ---
    # TrustScoreCalculator creates its own engine and uses SQLite-specific DDL
    # (AUTOINCREMENT) which breaks on PostgreSQL.  We reproduce the same 5-component
    # formula directly here, using the already-initialised _engine.
    try:
        import datetime
        from src.models.database import customer_pk

        pk = customer_pk()
        WEIGHTS = {
            "account_age": 0.20, "credit_score": 0.30,
            "fraud_history": 0.25, "sentiment_avg": 0.15,
            "interaction_count": 0.10,
        }

        with _engine.connect() as conn:
            cust = conn.execute(sql_text(
                f"SELECT * FROM customers WHERE {pk} = :cid"
            ), {"cid": customer_id}).fetchone()

            if not cust:
                return TrustScoreResponse(
                    status="not_found",
                    customer_id=customer_id,
                    error="Customer not found",
                )

            c = dict(cust._mapping)

            fraud_count = conn.execute(sql_text(
                "SELECT COUNT(*) FROM enriched_transactions WHERE customer_id = :cid AND is_fraud = 1"
            ), {"cid": customer_id}).scalar() or 0

            try:
                int_row = conn.execute(sql_text(
                    "SELECT COUNT(*) as cnt, AVG(sentiment_score) as avg_sent FROM interactions WHERE customer_id = :cid"
                ), {"cid": customer_id}).fetchone()
                interaction_count = int(int_row[0]) if int_row and int_row[0] else 0
                avg_sentiment = float(int_row[1]) if int_row and int_row[1] is not None else 0.0
            except Exception:
                interaction_count = 0
                avg_sentiment = 0.0

        # Compute account age (handle both old schema account_opened and new created_at)
        created_raw = c.get("created_at") or c.get("account_opened") or ""
        try:
            created_dt = datetime.datetime.fromisoformat(str(created_raw)[:10])
            age_days = (datetime.datetime.utcnow() - created_dt).days
        except Exception:
            age_days = 0

        credit = int(c.get("credit_score") or 650)

        components = {
            "account_age":      round(min(age_days / 3650.0, 1.0) * 100, 1),
            "credit_score":     round(max(0.0, min(100.0, (credit - 300) / 550.0 * 100)), 1),
            "fraud_history":    round(max(0.0, 100.0 - fraud_count * 25), 1),
            "sentiment_avg":    round((avg_sentiment + 1.0) / 2.0 * 100, 1),
            "interaction_count": round(min(interaction_count / 20.0, 1.0) * 100, 1),
        }

        score = round(max(0.0, min(100.0, sum(components[k] * WEIGHTS[k] for k in WEIGHTS))), 1)
        tier = "High Risk" if score <= 40 else "Moderate" if score <= 70 else "Trusted"

        return TrustScoreResponse(
            status="ok",
            customer_id=customer_id,
            score=score,
            tier=tier,
            components=components,
            weights=WEIGHTS,
            fraud_incidents=fraud_count,
            total_interactions=interaction_count,
        )

    except Exception as e:
        traceback.print_exc()
        return TrustScoreResponse(
            status="error",
            customer_id=customer_id,
            error=f"Error computing trust score: {str(e)}",
        )


@router.get("/history/{customer_id}", response_model=TrustHistoryResponse)
async def get_trust_history(
    customer_id: str,
    limit: int = 10,
    current_user: CurrentUser = Depends(get_current_user),
):
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
async def get_ai_trust_history(
    session_id: str = None,
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
):
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
