import os
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

@router.get("/")
def get_kpis(cu: CurrentUser=Depends(require_permission("reports:read"))):
    with _engine.connect() as c:
        customer_total  = c.execute(text("SELECT COUNT(*) FROM customers WHERE is_active=1")).fetchone()[0] if _table_exists(c,"customers") else 0
        account_total   = c.execute(text("SELECT COUNT(*) FROM accounts WHERE status='active'")).fetchone()[0] if _table_exists(c,"accounts") else 0
        tx_today        = c.execute(text("SELECT COUNT(*),COALESCE(SUM(amount_cents),0) FROM transactions WHERE date(created_at)=date('now')")).fetchone() if _table_exists(c,"transactions") else (0,0)
        loan_total      = c.execute(text("SELECT COUNT(*),COALESCE(SUM(amount_cents),0) FROM loans WHERE status='active'")).fetchone() if _table_exists(c,"loans") else (0,0)
        aml_open        = c.execute(text("SELECT COUNT(*) FROM aml_cases WHERE status='open'")).fetchone()[0] if _table_exists(c,"aml_cases") else 0
        kyc_pending     = c.execute(text("SELECT COUNT(*) FROM kyc_records WHERE status='pending'")).fetchone()[0] if _table_exists(c,"kyc_records") else 0
        fraud_alerts    = c.execute(text("SELECT COUNT(*) FROM transactions WHERE is_flagged=1 AND date(created_at)=date('now')")).fetchone()[0] if _table_exists(c,"transactions") else 0
    return {
        "customers": {"total": customer_total},
        "accounts":  {"active": account_total},
        "transactions": {"today_count": tx_today[0], "today_volume_cents": tx_today[1]},
        "loans": {"active_count": loan_total[0], "portfolio_cents": loan_total[1]},
        "aml": {"open_cases": aml_open},
        "kyc": {"pending": kyc_pending},
        "fraud": {"today_alerts": fraud_alerts}
    }

def _table_exists(conn, name):
    r = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),{"n":name}).fetchone()
    return r is not None
