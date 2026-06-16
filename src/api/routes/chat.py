"""
AI Copilot chat endpoint — routes to the appropriate agent, then computes AI trust score.
"""
import os
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from src.api.auth import CurrentUser, require_permission, log_audit

router = APIRouter()

LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")


class ChatRequest(BaseModel):
    question: str
    customer_id: Optional[str] = None
    agent_id: Optional[str] = None
    context: Optional[dict] = None


class AITrustScore(BaseModel):
    final_score: float
    tier: str
    components: dict


class ChatResponse(BaseModel):
    answer: str
    sources: list
    confidence: float
    agent_name: str
    latency_ms: int
    metadata: dict = {}
    trust_score: Optional[AITrustScore] = None


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission("chat")),
):
    from src.agents.registry import get_agent, get_default_agent_for_role
    from src.rag.intent_classifier import classify_intent, needs_db_data
    from src.rag.data_retriever import retrieve_structured_data

    agent = get_agent(req.agent_id) if req.agent_id else get_default_agent_for_role(current_user.role)

    customer_ctx = ""
    if req.customer_id:
        customer_ctx = _build_customer_context(req.customer_id)

    extra_ctx = ""
    if req.context:
        for k, v in req.context.items():
            extra_ctx += f"\n{k.replace('_', ' ').title()}: {v}"

    # Hybrid RAG: classify intent and fetch live DB data when appropriate
    intent = classify_intent(req.question)
    structured_ctx = ""
    structured_sources: list = []
    if needs_db_data(intent):
        try:
            structured_ctx, structured_sources = retrieve_structured_data(
                intent, req.question, req.customer_id
            )
        except Exception as e:
            print(f"[Chat] Structured retrieval failed for intent '{intent}': {e}")

    result = agent.run(
        question=req.question,
        customer_context=customer_ctx + extra_ctx,
        extra_data={"customer_id": req.customer_id, "role": current_user.role},
        structured_context=structured_ctx,
    )

    # Merge structured DB sources with document RAG sources
    if structured_sources:
        result.sources = structured_sources + result.sources

    # ── AI Trust Score ─────────────────────────────────────────────────
    trust_score = None
    try:
        from src.models.ai_trust import get_ai_trust_scorer
        scorer = get_ai_trust_scorer()
        # source_chunks: use actual retrieved text (stored by BaseAgent); fall back to filenames
        source_chunks = result.metadata.get("_source_texts") or [s.get("document", "") for s in result.sources]
        # sim_scores are stored in metadata by BaseAgent
        _sim_scores = result.metadata.get("_sim_scores", [])
        ts = scorer.score(
            query=req.question,
            answer=result.answer,
            source_chunks=source_chunks,
            similarity_scores=_sim_scores,
            session_id=current_user.username,
            model_used=LLM_MODEL,
            is_db_grounded=bool(structured_sources),
        )
        trust_score = AITrustScore(
            final_score=ts["final_score"],
            tier=ts["tier"],
            components=ts["components"],
        )
    except Exception as e:
        print(f"[Chat] AI trust score failed: {e}")

    log_audit(
        current_user.username, current_user.role, "chat", "ai_copilot",
        resource_id=req.agent_id or agent.name,
        customer_id=req.customer_id or "",
        ip=request.client.host if request.client else "",
    )

    raw = result.to_dict()
    # Strip internal keys before returning to the client
    sim_scores = raw.get("metadata", {}).pop("_sim_scores", [])
    has_customer_ctx = bool(req.customer_id) and bool(customer_ctx)
    raw["confidence"] = _compute_confidence(raw.get("confidence", 0.5), raw.get("sources", []), sim_scores, has_customer_ctx)
    return ChatResponse(**raw, trust_score=trust_score)


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission("chat")),
):
    """SSE streaming endpoint — yields tokens as they arrive, then a final 'done' event with metadata."""
    from src.agents.registry import get_agent, get_default_agent_for_role
    from src.rag.intent_classifier import classify_intent, needs_db_data
    from src.rag.data_retriever import retrieve_structured_data

    agent = get_agent(req.agent_id) if req.agent_id else get_default_agent_for_role(current_user.role)

    customer_ctx = ""
    if req.customer_id:
        customer_ctx = _build_customer_context(req.customer_id)

    extra_ctx = ""
    if req.context:
        for k, v in req.context.items():
            extra_ctx += f"\n{k.replace('_', ' ').title()}: {v}"

    extra_data = {"customer_id": req.customer_id, "role": current_user.role}

    # Hybrid RAG: classify intent and fetch live DB data when appropriate
    intent = classify_intent(req.question)
    structured_ctx = ""
    structured_sources: list = []
    if needs_db_data(intent):
        try:
            structured_ctx, structured_sources = retrieve_structured_data(
                intent, req.question, req.customer_id
            )
        except Exception as e:
            print(f"[Stream] Structured retrieval failed for intent '{intent}': {e}")

    def generate():
        done_payload = None
        for event in agent.stream_response(
            question=req.question,
            customer_context=customer_ctx + extra_ctx,
            extra_data=extra_data,
            structured_context=structured_ctx,
        ):
            if event["type"] == "token":
                yield f"data: {json.dumps(event)}\n\n"
            elif event["type"] == "done":
                done_payload = event

        if done_payload:
            if structured_sources:
                done_payload["sources"] = structured_sources + done_payload.get("sources", [])
            sim_scores = done_payload["metadata"].pop("_sim_scores", [])
            has_customer_ctx = bool(req.customer_id) and bool(customer_ctx)
            done_payload["confidence"] = _compute_confidence(
                done_payload["confidence"], done_payload["sources"], sim_scores, has_customer_ctx
            )
            # Trust score
            try:
                from src.models.ai_trust import get_ai_trust_scorer
                scorer = get_ai_trust_scorer()
                source_chunks = done_payload["metadata"].pop("_source_texts", []) or \
                                [s.get("document", "") for s in done_payload["sources"]]
                ts = scorer.score(
                    query=req.question,
                    answer=done_payload["answer"],
                    source_chunks=source_chunks,
                    similarity_scores=sim_scores,
                    session_id=current_user.username,
                    model_used=LLM_MODEL,
                    is_db_grounded=bool(structured_sources),
                )
                done_payload["trust_score"] = {
                    "final_score": ts["final_score"],
                    "tier": ts["tier"],
                    "components": ts["components"],
                }
            except Exception as e:
                print(f"[Stream] trust score failed: {e}")

            log_audit(
                current_user.username, current_user.role, "chat_stream", "ai_copilot",
                resource_id=req.agent_id or agent.name,
                customer_id=req.customer_id or "",
                ip=request.client.host if request.client else "",
            )
            yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _compute_confidence(base: float, sources: list, sim_scores: list = None, has_customer_ctx: bool = False) -> float:
    """Re-score confidence using source count, similarity, freshness, and customer context."""
    if not sources:
        # Customer-grounded responses are reliable even without policy RAG hits
        if has_customer_ctx:
            return round(min(base, 0.95), 2)
        return round(min(base, 0.40), 2)
    # base is already calibrated to 95%+ in BaseAgent for retrieved responses.
    # Apply a small additional boost for multiple high-similarity sources.
    if sim_scores:
        avg_sim = sum(sim_scores) / len(sim_scores)
        sim_boost = max(0, (avg_sim - 0.5) * 0.08)
    else:
        sim_boost = 0
    boost = sim_boost + (0.01 if has_customer_ctx else 0)
    return round(min(0.99, base + boost), 2)


def _build_customer_context(customer_id: str) -> str:
    """
    Build a rich customer context block for the LLM.
    Uses _row_to_customer from customers.py so all derived fields
    (kyc_status, segment, aml_risk, phone, location) are consistent
    with the Customer 360 view.
    """
    try:
        from src.models.database import engine, customer_pk
        from sqlalchemy import text
        from src.api.routes.customers import _row_to_customer

        pk = customer_pk()
        with engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT * FROM customers WHERE {pk} = :cid"),
                {"cid": customer_id},
            ).fetchone()

        if not row:
            return f"[No customer found for ID: {customer_id}]"

        c = _row_to_customer(dict(row._mapping))
        balance    = (c.get("balance_cents") or 0) / 100
        income     = (c.get("annual_income") or 0) / 100
        age_days   = c.get("account_age_days", 0)
        age_years  = f"{age_days / 365:.1f} years" if age_days >= 365 else f"{age_days} days"

        return (
            f"=== CUSTOMER CONTEXT ===\n"
            f"Name            : {c['first_name']} {c['last_name']}\n"
            f"Customer ID     : {c['id']}\n"
            f"Email           : {c['email']}\n"
            f"Phone           : {c.get('phone', 'N/A')}\n"
            f"Location        : {c.get('address_city', '')}, {c.get('address_state', '')}\n"
            f"Segment         : {c.get('segment', 'N/A')}\n"
            f"Account Type    : {c.get('customer_type', 'N/A')}\n"
            f"Account Balance : ${balance:,.2f}\n"
            f"Account Age     : {age_years}\n"
            f"Annual Income   : ${income:,.0f}\n"
            f"Credit Score    : {c.get('credit_score', 'N/A')}\n"
            f"KYC Status      : {c.get('kyc_status', 'N/A')}\n"
            f"AML Risk Rating : {c.get('aml_risk_rating', 'N/A')}\n"
            f"Employment      : {c.get('employment_status', 'N/A')}\n"
            f"PEP             : {'YES — Enhanced Due Diligence Required' if c.get('is_pep') else 'No'}\n"
            f"Sanctioned      : {'YES — BLOCKED' if c.get('is_sanctioned') else 'No'}\n"
            f"========================\n"
        )
    except Exception as e:
        return f"[Customer context unavailable — {e}]"
