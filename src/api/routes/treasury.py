import os, json
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS treasury_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, instrument TEXT, cusip TEXT,
            position_type TEXT, face_value REAL DEFAULT 0, market_value REAL DEFAULT 0,
            yield_rate REAL DEFAULT 0, duration REAL DEFAULT 0, maturity_date TEXT,
            coupon_rate REAL DEFAULT 0, currency TEXT DEFAULT 'USD', status TEXT DEFAULT 'active',
            updated_at TEXT)"""))
        c.execute(text("""CREATE TABLE IF NOT EXISTS liquidity_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, metric_name TEXT UNIQUE,
            value REAL DEFAULT 0, threshold REAL DEFAULT 0, status TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

@router.get("/positions")
def get_positions(position_type: str=None, cu: CurrentUser=Depends(require_permission("treasury:read"))):
    filters,params = ["1=1"],{}
    if position_type: filters.append("position_type=:pt"); params["pt"]=position_type
    with _engine.connect() as c:
        rows = c.execute(text(f"SELECT * FROM treasury_positions WHERE {' AND '.join(filters)} ORDER BY market_value DESC"),params).fetchall()
    return {"positions":[dict(r._mapping) for r in rows],"total":len(rows)}

@router.get("/liquidity")
def get_liquidity(cu: CurrentUser=Depends(require_permission("treasury:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("SELECT * FROM liquidity_metrics ORDER BY metric_name")).fetchall()
    return {"metrics":[dict(r._mapping) for r in rows]}

@router.get("/summary")
def treasury_summary(cu: CurrentUser=Depends(require_permission("treasury:read"))):
    with _engine.connect() as c:
        total_pos  = c.execute(text("SELECT COALESCE(SUM(market_value),0) FROM treasury_positions WHERE status='active'")).fetchone()[0]
        pos_count  = c.execute(text("SELECT COUNT(*) FROM treasury_positions WHERE status='active'")).fetchone()[0]
        by_type    = c.execute(text("SELECT position_type,SUM(market_value) FROM treasury_positions WHERE status='active' GROUP BY position_type")).fetchall()
        avg_yield  = c.execute(text("SELECT COALESCE(AVG(yield_rate),0) FROM treasury_positions WHERE status='active'")).fetchone()[0]
    return {
        "total_portfolio_value": round(total_pos,2),
        "active_positions": pos_count,
        "avg_yield": round(avg_yield,4),
        "by_type": {r[0]:round(r[1],2) for r in by_type}
    }
