"""
Customer Intelligence Route — Customer 360 profile endpoint.

Wired to customer_context module for real profile data from SQLite
including transactions, sentiment, trust score, support history,
risk profile (Phase 7), and product recommendations (Phase 7).
"""
import traceback

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional, List

from src.api.auth import CurrentUser, require_permission, log_audit

router = APIRouter()


class CustomerSummaryResponse(BaseModel):
    """Response body for customer summary endpoint."""
    status: str
    customer_id: Optional[str] = None
    profile: Optional[dict] = None
    last_5_transactions: Optional[list] = None
    trust_score: Optional[dict] = None
    sentiment_trend: Optional[dict] = None
    support_tickets: Optional[dict] = None
    fraud_history: Optional[dict] = None
    rag_interaction_notes: Optional[list] = None
    risk_profile: Optional[dict] = None
    recommendations: Optional[list] = None
    error: Optional[str] = None


@router.get("/search", tags=["Customer Intelligence"])
async def search_customers(
    q: str = "",
    limit: int = 5,
    http_request: Request = None,
    current_user: CurrentUser = Depends(require_permission("customer")),
):
    """
    Search customers by name or ID.
    Returns matching customer records for the dashboard search bar.
    """
    try:
        import pandas as pd
        from sqlalchemy import text
        from src.models.database import engine

        query = text("""
            SELECT customer_id, name, age, income, credit_score, balance, account_type
            FROM customers
            WHERE customer_id LIKE :q OR name LIKE :qn
            LIMIT :lim
        """)
        df = pd.read_sql(query, engine, params={"q": f"%{q}%", "qn": f"%{q}%", "lim": limit})

        return {
            "status": "ok",
            "results": df.to_dict(orient="records"),
            "total": len(df),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "results": []}


@router.get("/summary/{customer_id}", response_model=CustomerSummaryResponse)
async def get_customer_summary(
    customer_id: str,
    http_request: Request = None,
    current_user: CurrentUser = Depends(require_permission("customer")),
):
    """
    Get a full 360-degree customer profile.

    Returns merged structured data (balance, credit score, account age)
    and unstructured data (banker notes, sentiment trends, interaction history).

    Includes Phase 7 intelligence:
    - Risk profile (risk_level, sentiment, fraud_risk, retention_probability)
    - Product recommendations (top 3 with reason strings)
    """
    try:
        from src.rag.customer_context import get_full_customer_context

        # Audit log PII access
        ip = http_request.client.host if http_request and http_request.client else ""
        log_audit(current_user.username, "read", "customer_profile", customer_id, ip)

        context = get_full_customer_context(customer_id)

        if "error" in context:
            return CustomerSummaryResponse(
                status="not_found",
                customer_id=customer_id,
                error=context["error"],
            )

        return CustomerSummaryResponse(
            status="ok",
            customer_id=customer_id,
            profile=context["profile"],
            last_5_transactions=context["last_5_transactions"],
            trust_score=context["trust_score"],
            sentiment_trend=context["sentiment_trend"],
            support_tickets=context.get("support_tickets"),
            fraud_history=context.get("fraud_history"),
            rag_interaction_notes=context.get("rag_interaction_notes"),
            risk_profile=context.get("risk_profile"),
            recommendations=context.get("recommendations"),
        )

    except Exception as e:
        traceback.print_exc()
        return CustomerSummaryResponse(
            status="error",
            customer_id=customer_id,
            error=f"Error retrieving customer data: {str(e)}",
        )
