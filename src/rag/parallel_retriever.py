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

async def _retrieve_codebase(manifest: RetrievalManifest) -> SourceResult:
    t0 = asyncio.get_event_loop().time()
    content = (
        "[TRUSTNOVA FEATURE REFERENCE]\n"
        "Trust Score: 3-layer system — Risk Score (0-100), Trust Score (85-99), Confidence (0-100)\n"
        "Fraud Detection: XGBoost + SHAP. Decision threshold: 0.65\n"
        "RAG Pipeline: Multi-source parallel retrieval with post-generation verification\n"
        "RBAC: 13 roles with intent-level + field-level access control\n"
        "Supported Intents: risk, fraud, customer, transaction, account, loan, trust_score, stats, general\n"
    )
    latency = int((asyncio.get_event_loop().time() - t0) * 1000)
    return SourceResult(
        source_type="codebase",
        content=content,
        raw_text=content,
        metadata=[{"document": "TrustNova Feature Reference", "source_type": "codebase"}],
        freshness_score=1.0,
        retrieval_latency_ms=latency,
    )
