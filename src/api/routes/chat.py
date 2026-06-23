"""
AI Copilot chat endpoint — Multi-Source Hybrid RAG v2.

Pipeline (per request):
  1. Query Router     → RetrievalManifest (which sources / tables / entities)
  2. Parallel Retrieve → asyncio.gather() across SQL + fraud + vector simultaneously
  3. Context Fusion   → structured labeled prompt context (SQL first, docs last)
  4. LLM Generation   → agent.run() with fused context
  5. Verification     → numeric + semantic check; regenerate once on failure
  6. Trust Score v2   → Risk (0-100) / Trust (85-99) / Confidence (0-100)
"""
import os
import json
import re
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from src.api.auth import CurrentUser, require_permission, log_audit, ROLES

router = APIRouter()

LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question:    str
    customer_id: Optional[str] = None
    agent_id:    Optional[str] = None
    context:     Optional[dict] = None


class AITrustScore(BaseModel):
    final_score: float
    tier:        str
    components:  dict


class TrustScoreV2Response(BaseModel):
    risk_score:       float
    risk_tier:        str
    trust_score:      float
    trust_tier:       str
    confidence_score: float
    explainability:   dict


class ChatResponse(BaseModel):
    answer:       str
    sources:      list
    confidence:   float
    agent_name:   str
    latency_ms:   int
    metadata:     dict = {}
    trust_score:  Optional[AITrustScore] = None          # legacy — kept for UI compat
    trust_score_v2: Optional[TrustScoreV2Response] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_source_citations(text: str) -> int:
    """Count [SQL] / [Fraud Engine] / [Policy Doc] / [Feature Ref] tags in text."""
    return len(re.findall(r"\[(SQL|Fraud Engine|Policy Doc|Feature Ref)\]", text, re.IGNORECASE))


def _avg_freshness(results) -> float:
    if not results:
        return 1.0
    return sum(r.freshness_score for r in results) / len(results)


def _avg_sim(sim_scores: list) -> float:
    return sum(sim_scores) / len(sim_scores) if sim_scores else 0.6


# ── Main chat endpoint ────────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    req:          ChatRequest,
    request:      Request,
    current_user: CurrentUser = Depends(require_permission("chat")),
):
    from src.agents.registry import get_agent, get_default_agent_for_role
    from src.rag import rbac_filter
    from src.rag.query_router import build_retrieval_manifest
    from src.rag.parallel_retriever import parallel_retrieve
    from src.rag.context_fusion import fuse_context
    from src.rag.verification import verify_response, build_correction_prompt

    agent = (
        get_agent(req.agent_id)
        if req.agent_id
        else get_default_agent_for_role(current_user.role)
    )

    # ── Customer context (legacy block — kept for agent compatibility) ─────────
    customer_ctx = ""
    if req.customer_id:
        customer_ctx = _build_customer_context(req.customer_id)
        customer_ctx = rbac_filter.redact_customer_fields(customer_ctx, current_user.permissions)

    extra_ctx = ""
    if req.context:
        for k, v in req.context.items():
            extra_ctx += f"\n{k.replace('_', ' ').title()}: {v}"

    # ── Step 1: Query Router ───────────────────────────────────────────────────
    manifest = build_retrieval_manifest(
        query=req.question,
        customer_id=req.customer_id,
        permissions=set(current_user.permissions),
    )

    # ── Step 2: Parallel Retrieval ─────────────────────────────────────────────
    retrieval = await parallel_retrieve(manifest)

    # ── Step 3: Context Fusion ─────────────────────────────────────────────────
    fused_ctx = fuse_context(
        results=retrieval.results,
        blocked_sources=manifest.rbac_blocked_sources,
        customer_id=req.customer_id,
    )

    # ── Step 4: LLM Generation ─────────────────────────────────────────────────
    result = agent.run(
        question=req.question,
        customer_context=customer_ctx + extra_ctx,
        extra_data={
            "customer_id":       req.customer_id,
            "role":              current_user.role,
            "permissions":       current_user.permissions,
            "retrieval_intents": retrieval.intents,
        },
        structured_context=fused_ctx,
    )

    # Merge all sources (parallel retrieval sources + document RAG sources)
    all_sources = retrieval.all_sources + [
        s for s in result.sources
        if s not in retrieval.all_sources
    ]
    result.sources = all_sources

    # ── Step 5: Verification ───────────────────────────────────────────────────
    sim_scores     = result.metadata.get("_sim_scores", [])
    source_chunks  = result.metadata.get("_source_texts") or retrieval.source_chunks

    verification = verify_response(
        response=result.answer,
        sql_text_snapshot=retrieval.sql_text_snapshot,
        source_chunks=source_chunks,
    )

    if not verification.passed:
        # One regeneration attempt with a correction prompt
        try:
            correction_q = build_correction_prompt(
                original_query=req.question,
                failed_response=result.answer,
                violations=verification.violations,
                fused_context=fused_ctx,
            )
            corrected = agent.run(
                question=correction_q,
                customer_context=customer_ctx,
                extra_data={
                    "customer_id": req.customer_id,
                    "role": current_user.role,
                    "permissions": current_user.permissions,
                },
                structured_context=fused_ctx,
            )
            result.answer   = corrected.answer
            result.metadata["verification_corrected"] = True
        except Exception as exc:
            result.metadata["verification_error"] = str(exc)

    result.metadata["verification_passed"]    = verification.passed
    result.metadata["verification_confidence"] = verification.confidence
    if verification.violations:
        result.metadata["verification_violations"] = verification.violations

    # ── Step 6a: Legacy AI Trust Score (backward compat) ──────────────────────
    trust_score = None
    try:
        from src.models.ai_trust import get_ai_trust_scorer
        scorer = get_ai_trust_scorer()
        ts = scorer.score(
            query=req.question,
            answer=result.answer,
            source_chunks=source_chunks,
            similarity_scores=sim_scores,
            session_id=current_user.username,
            model_used=LLM_MODEL,
            is_db_grounded=bool(retrieval.all_sources),
        )
        trust_score = AITrustScore(
            final_score=ts["final_score"],
            tier=ts["tier"],
            components=ts["components"],
        )
    except Exception as e:
        print(f"[Chat] AI trust score failed: {e}")

    # ── Step 6b: 3-Layer Trust Score v2 ───────────────────────────────────────
    trust_score_v2 = None
    if req.customer_id:
        try:
            from src.models.trust_scorer_v2 import compute_all_scores

            avg_sim_score = _avg_sim(sim_scores)
            scores = compute_all_scores(
                customer_id=req.customer_id,
                retrieval_meta={
                    "sources_succeeded":   retrieval.sources_succeeded,
                    "sources_attempted":   retrieval.sources_attempted,
                    "avg_retrieval_score": avg_sim_score,
                    "citation_count":      _count_source_citations(result.answer),
                    "avg_freshness":       _avg_freshness(retrieval.results),
                },
                verification_conf=verification.confidence,
            )
            if scores:
                trust_score_v2 = TrustScoreV2Response(
                    risk_score=scores.risk_score,
                    risk_tier=scores.risk_tier,
                    trust_score=scores.trust_score,
                    trust_tier=scores.trust_tier,
                    confidence_score=scores.confidence_score,
                    explainability=scores.explainability,
                )
        except Exception as e:
            print(f"[Chat] Trust score v2 failed: {e}")

    # ── Audit + response ───────────────────────────────────────────────────────
    log_audit(
        current_user.username, current_user.role, "chat", "ai_copilot",
        resource_id=req.agent_id or agent.name,
        customer_id=req.customer_id or "",
        ip=request.client.host if request.client else "",
    )

    raw = result.to_dict()
    raw["metadata"].pop("_source_texts", None)
    sim_scores_out = raw["metadata"].pop("_sim_scores", [])
    has_customer_ctx = bool(req.customer_id) and bool(customer_ctx)
    raw["confidence"] = _compute_confidence(
        raw.get("confidence", 0.5),
        raw.get("sources", []),
        sim_scores_out,
        has_customer_ctx,
    )

    return ChatResponse(**raw, trust_score=trust_score, trust_score_v2=trust_score_v2)


# ── Streaming endpoint ────────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    req:          ChatRequest,
    request:      Request,
    current_user: CurrentUser = Depends(require_permission("chat")),
):
    """SSE streaming — yields tokens as they arrive, then a final 'done' event with metadata."""
    from src.agents.registry import get_agent, get_default_agent_for_role
    from src.rag import rbac_filter
    from src.rag.query_router import build_retrieval_manifest
    from src.rag.parallel_retriever import parallel_retrieve
    from src.rag.context_fusion import fuse_context

    agent = (
        get_agent(req.agent_id)
        if req.agent_id
        else get_default_agent_for_role(current_user.role)
    )

    customer_ctx = ""
    if req.customer_id:
        customer_ctx = _build_customer_context(req.customer_id)
        customer_ctx = rbac_filter.redact_customer_fields(customer_ctx, current_user.permissions)

    extra_ctx = ""
    if req.context:
        for k, v in req.context.items():
            extra_ctx += f"\n{k.replace('_', ' ').title()}: {v}"

    # Parallel retrieval + fusion (async, before streaming starts)
    manifest = build_retrieval_manifest(
        query=req.question,
        customer_id=req.customer_id,
        permissions=set(current_user.permissions),
    )
    retrieval = await parallel_retrieve(manifest)
    fused_ctx = fuse_context(
        results=retrieval.results,
        blocked_sources=manifest.rbac_blocked_sources,
        customer_id=req.customer_id,
    )

    extra_data = {
        "customer_id":       req.customer_id,
        "role":              current_user.role,
        "permissions":       current_user.permissions,
        "retrieval_intents": retrieval.intents,
    }

    def generate():
        done_payload = None
        for event in agent.stream_response(
            question=req.question,
            customer_context=customer_ctx + extra_ctx,
            extra_data=extra_data,
            structured_context=fused_ctx,
        ):
            if event["type"] == "token":
                yield f"data: {json.dumps(event)}\n\n"
            elif event["type"] == "done":
                done_payload = event

        if done_payload:
            # Merge sources
            done_payload["sources"] = retrieval.all_sources + done_payload.get("sources", [])

            sim_scores    = done_payload["metadata"].pop("_sim_scores", [])
            source_chunks = done_payload["metadata"].pop("_source_texts", []) or retrieval.source_chunks
            has_ctx       = bool(req.customer_id) and bool(customer_ctx)

            done_payload["confidence"] = _compute_confidence(
                done_payload["confidence"], done_payload["sources"], sim_scores, has_ctx
            )

            # Legacy trust score
            try:
                from src.models.ai_trust import get_ai_trust_scorer
                scorer = get_ai_trust_scorer()
                ts = scorer.score(
                    query=req.question,
                    answer=done_payload["answer"],
                    source_chunks=source_chunks,
                    similarity_scores=sim_scores,
                    session_id=current_user.username,
                    model_used=LLM_MODEL,
                    is_db_grounded=bool(retrieval.all_sources),
                )
                done_payload["trust_score"] = {
                    "final_score": ts["final_score"],
                    "tier":        ts["tier"],
                    "components":  ts["components"],
                }
            except Exception as e:
                print(f"[Stream] trust score failed: {e}")

            # Trust score v2
            if req.customer_id:
                try:
                    from src.models.trust_scorer_v2 import compute_all_scores
                    scores = compute_all_scores(
                        customer_id=req.customer_id,
                        retrieval_meta={
                            "sources_succeeded":   retrieval.sources_succeeded,
                            "sources_attempted":   retrieval.sources_attempted,
                            "avg_retrieval_score": _avg_sim(sim_scores),
                            "citation_count":      _count_source_citations(done_payload["answer"]),
                            "avg_freshness":       _avg_freshness(retrieval.results),
                        },
                        verification_conf=1.0,
                    )
                    if scores:
                        done_payload["trust_score_v2"] = {
                            "risk_score":       scores.risk_score,
                            "risk_tier":        scores.risk_tier,
                            "trust_score":      scores.trust_score,
                            "trust_tier":       scores.trust_tier,
                            "confidence_score": scores.confidence_score,
                        }
                except Exception as e:
                    print(f"[Stream] trust score v2 failed: {e}")

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


# ── Shared helpers ────────────────────────────────────────────────────────────

def _compute_confidence(
    base: float,
    sources: list,
    sim_scores: list = None,
    has_customer_ctx: bool = False,
) -> float:
    if not sources:
        if has_customer_ctx:
            return round(min(base, 0.95), 2)
        return round(min(base, 0.40), 2)
    if sim_scores:
        avg_sim    = sum(sim_scores) / len(sim_scores)
        sim_boost  = max(0, (avg_sim - 0.5) * 0.08)
    else:
        sim_boost = 0
    boost = sim_boost + (0.01 if has_customer_ctx else 0)
    return round(min(0.99, base + boost), 2)


def _build_customer_context(customer_id: str) -> str:
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

        c       = _row_to_customer(dict(row._mapping))
        balance = (c.get("balance_cents") or 0) / 100
        income  = (c.get("annual_income") or 0) / 100
        age_days = c.get("account_age_days", 0)
        age_years = f"{age_days / 365:.1f} years" if age_days >= 365 else f"{age_days} days"

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
