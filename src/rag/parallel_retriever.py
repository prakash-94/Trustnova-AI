"""
Parallel Retrieval Engine — fires all data sources simultaneously via asyncio.

Replaces the sequential per-intent loop in chat.py with asyncio.gather() so
SQL, risk, fraud, and vector DB are all queried at the same time.

Existing data_retriever.py functions are synchronous (SQLAlchemy sync engine),
so each is wrapped with asyncio.to_thread() to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, List, Optional

from src.rag.query_router import RetrievalManifest


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class SourceResult:
    source_type: str          # "sql" | "risk_engine" | "fraud_engine" | "vector" | "codebase"
    content: str              # formatted text for context fusion
    raw_text: str             # same content — kept for verification layer
    metadata: List[dict]      # source citation objects
    freshness_score: float    # 0.0 (stale) → 1.0 (live)
    retrieval_latency_ms: int
    error: Optional[str] = None


@dataclass
class ParallelRetrievalResult:
    results:            List[SourceResult]
    intents:            List[str]
    all_sources:        List[dict]       # flat merged list for ChatResponse.sources
    sql_text_snapshot:  str              # raw SQL context for verification
    source_chunks:      List[str]        # vector chunks for verification
    total_latency_ms:   int
    sources_attempted:  int
    sources_succeeded:  int


# ── Main entry point ──────────────────────────────────────────────────────────

async def parallel_retrieve(manifest: RetrievalManifest) -> ParallelRetrievalResult:
    """
    Launch all retrieval tasks in parallel, collect results, return unified object.
    Each task is wrapped in asyncio.to_thread() so sync DB calls don't block
    the FastAPI event loop.
    """
    loop_start = asyncio.get_event_loop().time()

    tasks: list[asyncio.Task] = []

    if manifest.sql_tables or any(
        i in {"risk", "fraud", "customer", "transaction", "account", "loan", "trust_score", "stats"}
        for i in manifest.intents
    ):
        tasks.append(asyncio.create_task(_retrieve_sql(manifest), name="sql"))

    if manifest.use_fraud_engine:
        tasks.append(asyncio.create_task(_retrieve_fraud(manifest), name="fraud"))

    if manifest.use_vector_db:
        tasks.append(asyncio.create_task(_retrieve_vector(manifest), name="vector"))

    if manifest.use_codebase_store:
        tasks.append(asyncio.create_task(_retrieve_codebase(manifest), name="codebase"))

    raw = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[SourceResult] = []
    for item in raw:
        if isinstance(item, Exception):
            results.append(SourceResult(
                source_type="error", content="", raw_text="",
                metadata=[], freshness_score=0.0,
                retrieval_latency_ms=0, error=str(item),
            ))
        else:
            results.append(item)

    good_results = [r for r in results if not r.error]
    all_sources  = [src for r in good_results for src in r.metadata]

    # SQL text snapshot for the verification layer
    sql_snapshot = next(
        (r.raw_text for r in good_results if r.source_type == "sql"), ""
    )

    # Vector chunks for semantic grounding check
    vector_result = next((r for r in good_results if r.source_type == "vector"), None)
    source_chunks = (
        [block.strip() for block in vector_result.content.split("\n\n") if block.strip()]
        if vector_result else []
    )

    elapsed = int((asyncio.get_event_loop().time() - loop_start) * 1000)

    return ParallelRetrievalResult(
        results=good_results,
        intents=manifest.intents,
        all_sources=all_sources,
        sql_text_snapshot=sql_snapshot,
        source_chunks=source_chunks,
        total_latency_ms=elapsed,
        sources_attempted=len(tasks),
        sources_succeeded=len(good_results),
    )


# ── SQL retrieval ─────────────────────────────────────────────────────────────

async def _retrieve_sql(manifest: RetrievalManifest) -> SourceResult:
    """
    Dispatch to existing data_retriever.py functions for each intent.
    Runs synchronous DB calls in a thread so the event loop stays free.
    """
    t0 = asyncio.get_event_loop().time()

    def _sync_fetch():
        from src.rag.intent_classifier import needs_db_data
        from src.rag.data_retriever import retrieve_structured_data

        query      = manifest.entity_refs.get("original_query", "")
        cid        = manifest.entity_refs.get("customer_id")
        # Use the manifest intents (semantic router result) — NOT a second regex pass.
        # Re-running plan_intents() here was discarding the semantic router's work.
        intents    = manifest.intents

        parts: list[str] = []
        metadata: list[dict] = []
        seen: set[tuple] = set()

        for intent in intents:
            if not needs_db_data(intent):
                continue
            try:
                ctx, srcs = retrieve_structured_data(intent, query, cid)
                if ctx:
                    parts.append(f"[INTENT: {intent.upper()}]\n{ctx}")
                for s in srcs:
                    key = (s.get("document"), s.get("table"))
                    if key not in seen:
                        seen.add(key)
                        metadata.append(s)
            except Exception as exc:
                parts.append(f"[Retrieval error for {intent}: {exc}]")

        return "\n\n".join(parts), metadata

    combined_ctx, meta = await asyncio.to_thread(_sync_fetch)
    latency = int((asyncio.get_event_loop().time() - t0) * 1000)

    return SourceResult(
        source_type="sql",
        content=combined_ctx,
        raw_text=combined_ctx,
        metadata=meta,
        freshness_score=1.0,      # live DB read
        retrieval_latency_ms=latency,
    )


# ── Fraud engine retrieval ────────────────────────────────────────────────────

async def _retrieve_fraud(manifest: RetrievalManifest) -> SourceResult:
    t0 = asyncio.get_event_loop().time()
    cid = manifest.entity_refs.get("customer_id")
    query = manifest.entity_refs.get("original_query", "")

    def _sync_fetch():
        from src.rag.data_retriever import get_fraud_data
        return get_fraud_data(query, customer_id=cid)

    ctx, meta = await asyncio.to_thread(_sync_fetch)
    latency = int((asyncio.get_event_loop().time() - t0) * 1000)

    return SourceResult(
        source_type="fraud_engine",
        content=f"[FRAUD ENGINE]\n{ctx}" if ctx else "",
        raw_text=ctx,
        metadata=meta,
        freshness_score=1.0,
        retrieval_latency_ms=latency,
    )


# ── Vector DB retrieval ───────────────────────────────────────────────────────

async def _retrieve_vector(manifest: RetrievalManifest) -> SourceResult:
    t0 = asyncio.get_event_loop().time()
    query = manifest.entity_refs.get("original_query", "")

    def _sync_fetch():
        # HyDE: generate hypothetical document → embed it → search.
        # Falls back to standard hybrid_search() automatically on any failure.
        from src.rag.hyde import hybrid_hyde_search
        docs = hybrid_hyde_search(query, k=6)

        lines: list[str] = ["[POLICY / DOCUMENT EVIDENCE]"]
        meta: list[dict] = []
        for doc, score in docs:
            if score > 0.20:
                source = doc.metadata.get("source", "policy_doc")
                lines.append(f"[score:{score:.2f}][{source}]\n{doc.page_content}")
                meta.append({
                    "document": source,
                    "score": round(score, 4),
                    "source_type": "vector",
                    "section": doc.metadata.get("section"),
                })
        return "\n\n".join(lines), meta

    ctx, meta = await asyncio.to_thread(_sync_fetch)
    latency = int((asyncio.get_event_loop().time() - t0) * 1000)

    return SourceResult(
        source_type="vector",
        content=ctx,
        raw_text=ctx,
        metadata=meta,
        freshness_score=0.75,
        retrieval_latency_ms=latency,
    )


# ── Codebase / feature store retrieval ───────────────────────────────────────

# Authoritative TrustNova feature reference used when vector store has no
# codebase-tagged documents yet.  Update this as the platform evolves.
_CODEBASE_FALLBACK = """[TRUSTNOVA FEATURE REFERENCE — Built-in Knowledge Base]

TRUST SCORE (3-layer system):
  • Risk Score  (0–100)  : 100 − weighted trust components; higher = riskier
  • Trust Score (85–99)  : 99 − (risk/100 × 14); always in 85-99 range
  • Confidence  (0–100)  : retrieval quality × verification quality
  • Tiers: Premium ≥97, Preferred ≥92, Standard otherwise

FRAUD DETECTION:
  • Model: XGBoost with SHAP explanations
  • Decision threshold: 0.65 (scores above = flagged)
  • Real-time transaction scoring on enriched_transactions table
  • Severity tiers: Critical ≥0.85, High ≥0.70, Medium ≥0.55, Low <0.55

RAG PIPELINE (6-layer hybrid):
  Query → Entity Memory → Query Rewriter → Semantic Router →
  Parallel Retrieval (SQL + Risk + Fraud + Vector/HyDE) →
  Context Fusion → LLM Generation → Verification → 3-Layer Trust Score

INTENT ROUTING (13 intents):
  risk, fraud, customer, transaction, account, loan, trust_score,
  kyc, aml, policy, stats, trustnova_features, general

AML / KYC:
  • AML alerts tracked in fraud_alerts table (status: open/resolved)
  • KYC fields: identity_verified, kyc_status, cdd_level in customers table
  • SAR/CTR thresholds: configurable; structuring detection enabled
  • CDD levels: standard, enhanced, simplified

ACCESS CONTROL (RBAC):
  • 13 roles with intent-level permission gates
  • Field-level restrictions: fraud:read, risk:read, loans:read, aml:read
  • All queries RBAC-filtered before any data is retrieved

SUPPORTED QUERY TYPES:
  Customer intelligence, loan portfolio, fraud investigation,
  AML compliance, KYC verification, risk assessment,
  transaction analysis, portfolio statistics, platform features
"""


async def _retrieve_codebase(manifest: RetrievalManifest) -> SourceResult:
    """
    Retrieve TrustNova feature/methodology knowledge.

    Strategy:
      1. Try vector store with source_type=codebase filter (real uploaded docs)
      2. Fall back to built-in _CODEBASE_FALLBACK if vector store returns nothing
    """
    t0 = asyncio.get_event_loop().time()
    query = manifest.entity_refs.get("original_query", "")

    def _sync_fetch() -> tuple[str, list[dict]]:
        try:
            from src.rag.hyde import hybrid_hyde_search
            docs = hybrid_hyde_search(
                query, k=4,
                metadata_filter={"source_type": "codebase"},
            )
            chunks = [
                f"[score:{score:.2f}][{doc.metadata.get('source', 'feature_ref')}]\n"
                f"{doc.page_content}"
                for doc, score in docs
                if score > 0.20
            ]
            if chunks:
                content = "[TRUSTNOVA FEATURE REFERENCE]\n\n" + "\n\n".join(chunks)
                meta = [
                    {
                        "document": doc.metadata.get("source", "feature_ref"),
                        "score": round(score, 4),
                        "source_type": "codebase",
                    }
                    for doc, score in docs if score > 0.20
                ]
                return content, meta
        except Exception:
            pass

        # Vector store empty or unavailable — use built-in reference
        return _CODEBASE_FALLBACK, [
            {"document": "TrustNova Built-in Reference", "source_type": "codebase"}
        ]

    content, meta = await asyncio.to_thread(_sync_fetch)
    latency = int((asyncio.get_event_loop().time() - t0) * 1000)
    return SourceResult(
        source_type="codebase",
        content=content,
        raw_text=content,
        metadata=meta,
        freshness_score=1.0,
        retrieval_latency_ms=latency,
    )
