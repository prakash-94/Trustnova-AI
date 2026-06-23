"""
RAG Eval Pipeline — automated quality measurement for the retrieval system.

Priority 4: You can't improve what you can't measure.

Mechanical analogy: a car factory QC department that runs 50 test cars through
a standard checklist every night and reports a quality score. If the score
drops after a change, you know something broke.

Three metrics measured per golden query:
  1. Retrieval Recall    — did we fetch relevant documents? (0–1)
  2. Answer Faithfulness — does the answer match the retrieved sources? (0–1)
  3. Answer Relevance    — does the answer actually address the question? (0–1)

Golden queries are curated banking questions with known expected keywords.
Results stored in rag_eval_results table for trending over time.

Usage:
    from src.rag.eval_pipeline import run_eval
    report = run_eval()          # runs all golden queries
    print(report.summary())

Or via API:
    POST /rag/eval/run           → triggers eval, returns report
    GET  /rag/eval/history       → last N eval runs
    GET  /rag/eval/latest        → most recent scores
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional

from src.models.database import engine, auto_pk
from sqlalchemy import text


# ── Golden query bank ─────────────────────────────────────────────────────────
# Each entry: question + expected_keywords (must appear in retrieved context
# or answer to count as a retrieval hit)

GOLDEN_QUERIES: list[dict] = [
    # Risk queries
    {
        "id": "risk_01",
        "intent": "risk",
        "question": "Show me all high risk customers",
        "expected_keywords": ["high", "risk", "aml_risk_rating", "customer"],
    },
    {
        "id": "risk_02",
        "intent": "risk",
        "question": "Which customers have critical AML risk ratings?",
        "expected_keywords": ["aml", "risk", "critical", "high"],
    },
    # Fraud queries
    {
        "id": "fraud_01",
        "intent": "fraud",
        "question": "List all open fraud alerts",
        "expected_keywords": ["fraud", "alert", "open", "risk_score"],
    },
    {
        "id": "fraud_02",
        "intent": "fraud",
        "question": "Show suspicious transaction activity",
        "expected_keywords": ["fraud", "suspicious", "transaction", "flagged"],
    },
    # Loan queries — these test semantic routing (no literal "loan" in some)
    {
        "id": "loan_01",
        "intent": "loan",
        "question": "What are the active loans in our portfolio?",
        "expected_keywords": ["loan", "active", "outstanding", "balance"],
    },
    {
        "id": "loan_02",
        "intent": "loan",
        "question": "Which customers have delinquent obligations?",  # no word "loan"
        "expected_keywords": ["loan", "delinquent", "status", "balance"],
    },
    # Transaction queries
    {
        "id": "txn_01",
        "intent": "transaction",
        "question": "Show recent transaction history",
        "expected_keywords": ["transaction", "merchant", "amount", "timestamp"],
    },
    # Account queries
    {
        "id": "acc_01",
        "intent": "account",
        "question": "What are the account balances across the portfolio?",
        "expected_keywords": ["account", "balance", "type", "status"],
    },
    # Stats / portfolio
    {
        "id": "stats_01",
        "intent": "stats",
        "question": "Give me an institution-wide risk summary",
        "expected_keywords": ["total", "customer", "risk", "fraud", "loan"],
    },
    # Policy / compliance (tests HyDE vector retrieval)
    {
        "id": "policy_01",
        "intent": "general",
        "question": "What is the AML policy for wire transfers above $10,000?",
        "expected_keywords": ["aml", "wire", "transfer", "compliance", "policy"],
    },
    {
        "id": "policy_02",
        "intent": "general",
        "question": "What are the KYC requirements for new account opening?",
        "expected_keywords": ["kyc", "account", "identity", "verification", "customer"],
    },
]


# ── Result containers ─────────────────────────────────────────────────────────

@dataclass
class QueryEvalResult:
    query_id:          str
    intent:            str
    question:          str
    retrieval_recall:  float   # 0–1: fraction of expected_keywords found in context
    faithfulness:      float   # 0–1: answer grounded in retrieved context
    relevance:         float   # 0–1: answer addresses the question
    latency_ms:        int
    error:             Optional[str] = None

    @property
    def avg_score(self) -> float:
        return round((self.retrieval_recall + self.faithfulness + self.relevance) / 3, 3)


@dataclass
class EvalReport:
    run_id:        str
    timestamp:     str
    total_queries: int
    results:       List[QueryEvalResult] = field(default_factory=list)
    error_count:   int = 0

    @property
    def avg_retrieval_recall(self) -> float:
        good = [r for r in self.results if not r.error]
        return round(sum(r.retrieval_recall for r in good) / max(len(good), 1), 3)

    @property
    def avg_faithfulness(self) -> float:
        good = [r for r in self.results if not r.error]
        return round(sum(r.faithfulness for r in good) / max(len(good), 1), 3)

    @property
    def avg_relevance(self) -> float:
        good = [r for r in self.results if not r.error]
        return round(sum(r.relevance for r in good) / max(len(good), 1), 3)

    @property
    def overall_score(self) -> float:
        return round((self.avg_retrieval_recall + self.avg_faithfulness + self.avg_relevance) / 3, 3)

    def summary(self) -> str:
        lines = [
            f"\n{'='*55}",
            f"  RAG EVAL REPORT — {self.timestamp[:19]}",
            f"{'='*55}",
            f"  Queries run     : {self.total_queries}",
            f"  Errors          : {self.error_count}",
            f"{'─'*55}",
            f"  Retrieval Recall: {self.avg_retrieval_recall:.1%}",
            f"  Faithfulness    : {self.avg_faithfulness:.1%}",
            f"  Answer Relevance: {self.avg_relevance:.1%}",
            f"{'─'*55}",
            f"  OVERALL SCORE   : {self.overall_score:.1%}",
            f"{'='*55}",
        ]
        # Flag weak queries
        weak = [r for r in self.results if r.avg_score < 0.50 and not r.error]
        if weak:
            lines.append(f"\n  Weak queries (score < 50%):")
            for r in weak:
                lines.append(f"    [{r.query_id}] {r.question[:55]}  score={r.avg_score:.0%}")
        return "\n".join(lines)


# ── Core eval logic ───────────────────────────────────────────────────────────

def run_eval(
    queries: list[dict] | None = None,
    permissions: set | None = None,
) -> EvalReport:
    """
    Run the RAG eval pipeline against the golden query bank.

    Args:
        queries:     custom query list (defaults to GOLDEN_QUERIES)
        permissions: permission set for retrieval (defaults to admin wildcard)

    Returns:
        EvalReport with per-query scores and aggregates
    """
    import asyncio
    import time

    queries     = queries or GOLDEN_QUERIES
    permissions = permissions or {"*"}
    run_id      = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report      = EvalReport(
        run_id=run_id,
        timestamp=datetime.utcnow().isoformat(),
        total_queries=len(queries),
    )

    for q in queries:
        t0 = time.time()
        try:
            result = _eval_single_query(q, permissions, asyncio.new_event_loop())
            report.results.append(result)
            if result.error:
                report.error_count += 1
        except Exception as exc:
            report.results.append(QueryEvalResult(
                query_id=q["id"], intent=q["intent"],
                question=q["question"],
                retrieval_recall=0.0, faithfulness=0.0, relevance=0.0,
                latency_ms=int((time.time() - t0) * 1000),
                error=str(exc),
            ))
            report.error_count += 1

    _persist_report(report)
    return report


def _eval_single_query(
    q: dict,
    permissions: set,
    loop,
) -> QueryEvalResult:
    import time

    t0       = time.time()
    question = q["question"]
    keywords = [kw.lower() for kw in q["expected_keywords"]]

    # ── Step 1: Run retrieval (no LLM generation — just retrieval) ────────────
    from src.rag.query_router import build_retrieval_manifest

    manifest = build_retrieval_manifest(
        query=question,
        customer_id=None,
        permissions=permissions,
    )

    from src.rag.parallel_retriever import parallel_retrieve
    retrieval = loop.run_until_complete(parallel_retrieve(manifest))

    # Combine all retrieved text
    all_context = " ".join(
        r.content.lower() for r in retrieval.results if r.content
    )

    # ── Metric 1: Retrieval Recall ────────────────────────────────────────────
    hits = sum(1 for kw in keywords if kw in all_context)
    retrieval_recall = hits / max(len(keywords), 1)

    # ── Step 2: Generate answer for faithfulness + relevance check ────────────
    answer = ""
    try:
        from src.rag.context_fusion import fuse_context
        from src.api.llm_router import route

        fused   = fuse_context(retrieval.results, manifest.rbac_blocked_sources)
        prompt  = (
            f"{fused}\n\n"
            f"QUESTION: {question}\n\n"
            f"Answer concisely using only the context above:"
        )
        result  = route("general", prompt)
        answer  = result.get("response", "")
    except Exception:
        pass

    # ── Metric 2: Faithfulness ────────────────────────────────────────────────
    faithfulness = _faithfulness_score(answer, all_context) if answer else 0.0

    # ── Metric 3: Answer Relevance ────────────────────────────────────────────
    relevance = _relevance_score(question, answer) if answer else 0.0

    latency = int((time.time() - t0) * 1000)
    return QueryEvalResult(
        query_id=q["id"],
        intent=q["intent"],
        question=question,
        retrieval_recall=round(retrieval_recall, 3),
        faithfulness=round(faithfulness, 3),
        relevance=round(relevance, 3),
        latency_ms=latency,
    )


def _faithfulness_score(answer: str, context: str) -> float:
    """
    Measure how grounded the answer is in the retrieved context.
    Uses keyword overlap as a lightweight proxy for semantic faithfulness.
    """
    if not answer or not context:
        return 0.0

    # Tokenize (simple word split, lowercase, strip punctuation)
    import re
    _tok = lambda t: set(re.findall(r"\b[a-z]{3,}\b", t.lower()))

    answer_words  = _tok(answer)
    context_words = _tok(context)
    common        = answer_words & context_words

    # Precision: what fraction of non-trivial answer words appear in context?
    stopwords = {"the","a","an","is","are","was","were","be","been","have","has",
                 "for","and","or","but","not","this","that","with","from","they",
                 "which","what","when","where","how","their","there","then"}
    content_words = answer_words - stopwords
    if not content_words:
        return 0.5  # can't evaluate
    overlap = (common - stopwords) & content_words
    return min(1.0, len(overlap) / len(content_words))


def _relevance_score(question: str, answer: str) -> float:
    """
    Lightweight proxy for answer relevance: do question keywords appear in answer?
    """
    if not answer:
        return 0.0

    import re
    _tok = lambda t: set(re.findall(r"\b[a-z]{4,}\b", t.lower()))
    stopwords = {"show","list","what","give","tell","does","have","with","that","this","from","their"}

    q_words  = _tok(question) - stopwords
    a_words  = _tok(answer)
    if not q_words:
        return 0.5
    hits = q_words & a_words
    return min(1.0, len(hits) / len(q_words))


# ── Persistence ───────────────────────────────────────────────────────────────

def _ensure_eval_table():
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS rag_eval_results (
                id          {auto_pk},
                run_id      TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                total_queries INTEGER,
                overall_score REAL,
                retrieval_recall REAL,
                faithfulness REAL,
                relevance    REAL,
                error_count  INTEGER,
                details_json TEXT,
                created_at   TEXT NOT NULL
            )
        """))
        conn.commit()


def _persist_report(report: EvalReport) -> None:
    try:
        _ensure_eval_table()
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO rag_eval_results
                (run_id, timestamp, total_queries, overall_score,
                 retrieval_recall, faithfulness, relevance,
                 error_count, details_json, created_at)
                VALUES (:run_id, :ts, :total, :overall,
                        :recall, :faith, :relev,
                        :errors, :details, :now)
            """), {
                "run_id":  report.run_id,
                "ts":      report.timestamp,
                "total":   report.total_queries,
                "overall": report.overall_score,
                "recall":  report.avg_retrieval_recall,
                "faith":   report.avg_faithfulness,
                "relev":   report.avg_relevance,
                "errors":  report.error_count,
                "details": json.dumps([asdict(r) for r in report.results]),
                "now":     datetime.utcnow().isoformat(),
            })
            conn.commit()
    except Exception as exc:
        print(f"[EvalPipeline] Failed to persist report: {exc}")


def get_eval_history(limit: int = 10) -> list[dict]:
    """Retrieve the last N eval run summaries from DB."""
    try:
        _ensure_eval_table()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT run_id, timestamp, total_queries, overall_score,
                       retrieval_recall, faithfulness, relevance, error_count
                FROM rag_eval_results
                ORDER BY created_at DESC LIMIT :lim
            """), {"lim": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def get_latest_eval() -> dict | None:
    """Return the most recent eval run with full details."""
    try:
        _ensure_eval_table()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT * FROM rag_eval_results
                ORDER BY created_at DESC LIMIT 1
            """)).fetchone()
        if not row:
            return None
        d = dict(row._mapping)
        d["details"] = json.loads(d.get("details_json") or "[]")
        return d
    except Exception:
        return None
