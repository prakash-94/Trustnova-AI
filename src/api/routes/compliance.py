"""
Compliance Dashboard API — live data from banking.db.

Endpoints:
  GET /compliance/stats       — complaint counts + category breakdown
  GET /compliance/complaints  — paginated complaints with derived status
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.api.auth import CurrentUser, require_permission
from src.models.database import engine

router = APIRouter()

# Timestamp cutoffs for derived complaint status
_OPEN_CUTOFF       = "2026-06-01"   # >= this → Open
_IN_REVIEW_CUTOFF  = "2026-03-01"   # >= this (and < OPEN) → In Review
                                     # < IN_REVIEW → Resolved


def _derive_status(ts: str) -> str:
    if ts >= _OPEN_CUTOFF:
        return "Open"
    if ts >= _IN_REVIEW_CUTOFF:
        return "In Review"
    return "Resolved"


@router.get("/stats")
async def compliance_stats(
    current_user: CurrentUser = Depends(require_permission("chat")),
):
    """Live complaint counts + category breakdown from the complaints table."""
    try:
        with engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM complaints")).scalar() or 0

            open_count = conn.execute(text(
                "SELECT COUNT(*) FROM complaints WHERE timestamp >= :cutoff"
            ), {"cutoff": _OPEN_CUTOFF}).scalar() or 0

            in_review = conn.execute(text(
                "SELECT COUNT(*) FROM complaints "
                "WHERE timestamp >= :lo AND timestamp < :hi"
            ), {"lo": _IN_REVIEW_CUTOFF, "hi": _OPEN_CUTOFF}).scalar() or 0

            resolved = total - open_count - in_review

            category_rows = conn.execute(text(
                "SELECT category, COUNT(*) AS cnt "
                "FROM complaints GROUP BY category ORDER BY cnt DESC"
            )).fetchall()

            avg_sentiment = conn.execute(
                text("SELECT AVG(sentiment_score) FROM complaints")
            ).scalar() or -0.5
    except SQLAlchemyError:
        return {
            "complaint_counts": {"total": 0, "open": 0, "in_review": 0, "resolved": 0},
            "categories": [],
            "avg_sentiment": 0.0,
        }

    return {
        "complaint_counts": {
            "total":     total,
            "open":      open_count,
            "in_review": in_review,
            "resolved":  resolved,
        },
        "categories": [
            {"name": r[0].replace("_", " ").title(), "count": r[1]}
            for r in category_rows
        ],
        "avg_sentiment": round(float(avg_sentiment), 2),
    }


@router.get("/complaints")
async def complaints_list(
    status: str  = Query("all", description="all | open | in_review | resolved"),
    limit:  int  = Query(20, ge=1, le=100),
    offset: int  = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("chat")),
):
    """Paginated complaints list with derived status field."""
    where_map = {
        "open":      f"timestamp >= '{_OPEN_CUTOFF}'",
        "in_review": f"timestamp >= '{_IN_REVIEW_CUTOFF}' AND timestamp < '{_OPEN_CUTOFF}'",
        "resolved":  f"timestamp < '{_IN_REVIEW_CUTOFF}'",
    }
    where = where_map.get(status.lower(), "1=1")

    try:
        with engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM complaints WHERE {where}")
            ).scalar() or 0

            rows = conn.execute(text(f"""
                SELECT complaint_id, customer_id, category,
                       transcript_text, resolution_text,
                       sentiment_score, timestamp
                FROM complaints
                WHERE {where}
                ORDER BY timestamp DESC
                LIMIT :limit OFFSET :offset
            """), {"limit": limit, "offset": offset}).fetchall()
    except SQLAlchemyError:
        return {"complaints": [], "total": 0}

    complaints = []
    for r in rows:
        m = dict(r._mapping)
        ts = str(m.get("timestamp") or "")
        complaints.append({
            "id":          m["complaint_id"],
            "customer_id": m["customer_id"],
            "category":    (m["category"] or "").replace("_", " ").title(),
            "description": m["transcript_text"] or "",
            "resolution":  m["resolution_text"] or "",
            "sentiment":   float(m["sentiment_score"] or -0.5),
            "timestamp":   ts,
            "status":      _derive_status(ts),
            "raised_by":   "Customer",
        })

    return {"complaints": complaints, "total": total}