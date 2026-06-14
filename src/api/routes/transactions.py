import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY, account_id TEXT, customer_id TEXT, transaction_type TEXT,
            amount_cents INTEGER, currency TEXT DEFAULT 'USD', description TEXT,
            merchant TEXT, category TEXT, status TEXT DEFAULT 'completed',
            is_flagged INTEGER DEFAULT 0, flag_reason TEXT, location TEXT, created_at TEXT)"""))
        c.commit()
_ensure()

def _period_filter(period: str):
    now = datetime.now()
    if period == "daily":     return (now - timedelta(days=1)).isoformat()
    if period == "weekly":    return (now - timedelta(weeks=1)).isoformat()
    if period == "monthly":   return (now - timedelta(days=30)).isoformat()
    if period == "quarterly": return (now - timedelta(days=90)).isoformat()
    if period == "annual":    return (now - timedelta(days=365)).isoformat()
    return None

@router.get("")
def list_transactions(period: str=None, limit: int=Query(100,le=500), offset: int=0, cu: CurrentUser=Depends(require_permission("transactions:read"))):
    since = _period_filter(period) if period and period!="all" else None
    params = {"lim":limit,"off":offset}
    where  = "created_at>=:since" if since else "1=1"
    if since: params["since"]=since
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM transactions WHERE {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),params).fetchall()
        total = c.execute(text(f"SELECT COUNT(*) FROM transactions WHERE {where}"),{"since":since} if since else {}).fetchone()[0]
    return {"transactions":[dict(r._mapping) for r in rows],"total":total}

@router.get("/stats")
def transaction_stats(cu: CurrentUser=Depends(require_permission("transactions:read"))):
    today = datetime.now().date().isoformat()
    with _engine.connect() as c:
        total   = c.execute(text("SELECT COUNT(*) FROM transactions")).fetchone()[0]
        td      = c.execute(text("SELECT COUNT(*) FROM transactions WHERE created_at>=:d"),{"d":today}).fetchone()[0]
        flagged = c.execute(text("SELECT COUNT(*) FROM transactions WHERE is_flagged=1")).fetchone()[0]
        vol     = c.execute(text("SELECT COALESCE(SUM(ABS(amount_cents)),0) FROM transactions")).fetchone()[0]
    return {"total":total,"today":td,"flagged":flagged,"total_volume_cents":vol}
