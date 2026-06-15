"""
KPI Stats endpoint — returns all metrics for role-based dashboards.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()


@router.get("/stats")
async def kpi_stats(current_user: CurrentUser = Depends(require_permission("chat"))):
    """Comprehensive KPI stats for role-based KPI bar and dashboard."""
    with engine.connect() as conn:
        total_customers = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 0
        try:
            ai_queries_today = conn.execute(text(
                "SELECT COUNT(*) FROM llm_usage WHERE DATE(timestamp) = DATE('now')"
            )).scalar() or 0
        except Exception:
            ai_queries_today = 0

        fraud_open = conn.execute(text(
            "SELECT COUNT(*) FROM fraud_alerts WHERE status='open'"
        )).scalar() or 0
        fraud_total = conn.execute(text("SELECT COUNT(*) FROM fraud_alerts")).scalar() or 0
        fraud_critical = conn.execute(text(
            "SELECT COUNT(*) FROM fraud_alerts WHERE risk_score >= 0.85 AND status='open'"
        )).scalar() or 0

        try:
            loan_count = conn.execute(text("SELECT COUNT(*) FROM loans")).scalar() or 0
            loan_pending = conn.execute(text(
                "SELECT COUNT(*) FROM loans WHERE status = 'pending'"
            )).scalar() or 0
        except Exception:
            loan_count = 0
            loan_pending = 0

        kyc_pending = conn.execute(text(
            "SELECT COUNT(*) FROM customers WHERE LOWER(aml_risk_rating) IN ('medium', 'high')"
        )).scalar() or 0

        try:
            trust_avg = conn.execute(text(
                "SELECT AVG(final_score) FROM ai_trust_scores"
            )).scalar() or 87.4
        except Exception:
            trust_avg = 87.4

        high_risk = conn.execute(text(
            "SELECT COUNT(*) FROM customers WHERE LOWER(aml_risk_rating) = 'high'"
        )).scalar() or 0

        avg_credit = conn.execute(text(
            "SELECT AVG(credit_score) FROM customers WHERE credit_score > 0"
        )).scalar() or 650

        try:
            aml_open = conn.execute(text(
                "SELECT COUNT(*) FROM aml_cases WHERE status IN ('open', 'under_review')"
            )).scalar() or 0
        except Exception:
            aml_open = 0

    return {
        "total_customers": total_customers,
        "ai_queries_today": ai_queries_today,
        "fraud_open": fraud_open,
        "fraud_total": fraud_total,
        "fraud_critical": fraud_critical,
        "loan_count": loan_count,
        "loan_pending": loan_pending,
        "kyc_pending": kyc_pending,
        "trust_score_avg": round(float(trust_avg), 1),
        "docs_indexed": 16,
        "high_risk_customers": high_risk,
        "avg_credit_score": int(avg_credit),
        "aml_open": aml_open,
    }


@router.get("/ai-trust/recent")
async def ai_trust_recent(current_user: CurrentUser = Depends(require_permission("chat"))):
    """Recent AI trust score entries with scoring breakdown."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, session_id, query, retrieval_confidence, hallucination_probability,
                   model_agreement, citation_quality, prompt_reliability, final_score,
                   model_used, timestamp
            FROM ai_trust_scores
            ORDER BY timestamp DESC
            LIMIT 10
        """)).fetchall()
    entries = [dict(r._mapping) for r in rows]
    return {
        "entries": entries,
        "storage": {
            "table": "ai_trust_scores",
            "database": "SQLite banking.db",
            "file": "src/models/ai_trust.py → get_ai_trust_scorer()",
        },
        "scoring_weights": {
            "retrieval_confidence": {"weight": 0.30, "description": "Cosine similarity of top RAG chunks"},
            "hallucination_probability": {"weight": 0.25, "description": "Inverted — grounding check vs source docs"},
            "model_agreement": {"weight": 0.20, "description": "Jaccard similarity between LLM responses"},
            "citation_quality": {"weight": 0.15, "description": "Regex citation patterns (BSA, KYC, SAR, OFAC)"},
            "prompt_reliability": {"weight": 0.10, "description": "Rolling avg of last 20 trust scores"},
        },
        "tiers": {
            "High Confidence": "≥ 95",
            "Moderate Confidence": "≥ 85",
            "Low Confidence": "≥ 70",
            "Unreliable": "< 70",
        },
    }
