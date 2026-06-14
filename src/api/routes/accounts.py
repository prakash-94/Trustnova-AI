import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY, customer_id TEXT, account_type TEXT,
            account_number TEXT, balance_cents INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'active', interest_rate REAL, opened_date TEXT,
            last_transaction_date TEXT, created_at TEXT)"""))
        c.commit()
_ensure()

@router.get("")
def list_accounts(type: str=None, status: str=None, limit: int=Query(100,le=500), offset: int=0, cu: CurrentUser=Depends(require_permission("accounts:read"))):
    filters,params = ["1=1"],{}
    if type:   filters.append("account_type=:type");   params["type"]=type
    if status: filters.append("status=:status"); params["status"]=status
    params.update({"lim":limit,"off":offset})
    with _engine.connect() as c:
        rows  = c.execute(text(f"SELECT * FROM accounts WHERE {' AND '.join(filters)} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),params).fetchall()
        total = c.execute(text(f"SELECT COUNT(*) FROM accounts WHERE {' AND '.join(filters)}"),{k:v for k,v in params.items() if k not in ('lim','off')}).fetchone()[0]
    return {"accounts":[dict(r._mapping) for r in rows],"total":total}

@router.get("/stats")
def account_stats(cu: CurrentUser=Depends(require_permission("accounts:read"))):
    with _engine.connect() as c:
        total  = c.execute(text("SELECT COUNT(*) FROM accounts")).fetchone()[0]
        active = c.execute(text("SELECT COUNT(*) FROM accounts WHERE status='active'")).fetchone()[0]
        bal    = c.execute(text("SELECT COALESCE(SUM(balance_cents),0) FROM accounts")).fetchone()[0]
        rows   = c.execute(text("SELECT account_type, COUNT(*) as cnt FROM accounts GROUP BY account_type")).fetchall()
    return {"total":total,"active":active,"total_balance_cents":bal,"by_type":{r[0]:r[1] for r in rows}}
