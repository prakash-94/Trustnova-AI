"""
RAG Eval API — endpoints to trigger and inspect quality reports.

POST /rag/eval/run      → run all golden queries, return full report
GET  /rag/eval/latest   → most recent eval scores
GET  /rag/eval/history  → last N eval runs (trend data)

Access: admin + data_analyst roles only.
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional

from src.api.auth import CurrentUser, require_permission

router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class QueryScore(BaseModel):
    query_id:         str
    intent:           str
    question:         str
    retrieval_recall: float
    faithfulness:     float
    relevance:        float
    avg_score:        float
    latency_ms:       int
    error:            Optional[str] = None


class EvalReportResponse(BaseModel):
    run_id:               str
    timestamp:            str
    total_queries:        int
    overall_score:        float
    avg_retrieval_recall: float
    avg_faithfulness:     float
    avg_relevance:        float
    error_count:          int
    results:              List[QueryScore]
    summary:              str


class EvalHistoryEntry(BaseModel):
    run_id:           str
    timestamp:        str
    total_queries:    int
    overall_score:    float
    retrieval_recall: float
    faithfulness:     float
    relevance:        float
    error_count:      int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run", response_model=EvalReportResponse)
async def run_eval(
    current_user: CurrentUser = Depends(require_permission("admin")),
):
    """
    Trigger a full RAG eval run against all golden queries.
    Runs synchronously and returns the full report.
    May take 30–120 seconds depending on the number of queries.
    """
    import asyncio
    from src.rag.eval_pipeline import run_eval as _run_eval, GOLDEN_QUERIES

    # run_eval is synchronous (uses its own event loop per query)
    report = await asyncio.to_thread(
        _run_eval,
        GOLDEN_QUERIES,
        set(current_user.permissions),
    )

    return EvalReportResponse(
        run_id=report.run_id,
        timestamp=report.timestamp,
        total_queries=report.total_queries,
        overall_score=report.overall_score,
        avg_retrieval_recall=report.avg_retrieval_recall,
        avg_faithfulness=report.avg_faithfulness,
        avg_relevance=report.avg_relevance,
        error_count=report.error_count,
        results=[
            QueryScore(
                query_id=r.query_id,
                intent=r.intent,
                question=r.question,
                retrieval_recall=r.retrieval_recall,
                faithfulness=r.faithfulness,
                relevance=r.relevance,
                avg_score=r.avg_score,
                latency_ms=r.latency_ms,
                error=r.error,
            )
            for r in report.results
        ],
        summary=report.summary(),
    )


@router.get("/latest")
async def get_latest_eval(
    current_user: CurrentUser = Depends(require_permission("admin")),
):
    """Return the most recent eval run with all query-level details."""
    from src.rag.eval_pipeline import get_latest_eval as _get_latest
    result = _get_latest()
    if not result:
        return {"message": "No eval runs found. Run POST /rag/eval/run first."}
    return result


@router.get("/history", response_model=List[EvalHistoryEntry])
async def get_eval_history(
    limit: int = 10,
    current_user: CurrentUser = Depends(require_permission("admin")),
):
    """Return the last N eval run summaries for trend analysis."""
    from src.rag.eval_pipeline import get_eval_history as _get_history
    rows = _get_history(limit=limit)
    return [
        EvalHistoryEntry(
            run_id=r["run_id"],
            timestamp=r["timestamp"],
            total_queries=r["total_queries"],
            overall_score=r["overall_score"],
            retrieval_recall=r["retrieval_recall"],
            faithfulness=r["faithfulness"],
            relevance=r["relevance"],
            error_count=r["error_count"],
        )
        for r in rows
    ]
