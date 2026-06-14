import os
from fastapi import APIRouter, Depends, Query
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(os.getenv("DATABASE_URL","sqlite:///./banking.db"), connect_args={"check_same_thread":False})

def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS risk_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT UNIQUE,
            risk_score REAL DEFAULT 0.0, risk_band TEXT DEFAULT 'low',
            credit_risk REAL DEFAULT 0.0, fraud_risk REAL DEFAULT 0.0,
            aml_risk REAL DEFAULT 0.0, operational_risk REAL DEFAULT 0.0,
            assessed_by TEXT, notes TEXT, created_at TEXT, updated_at TEXT)"""))
        c.commit()
_ensure()

@router.get("/customer/{customer_id}")
def customer_risk(customer_id: str, cu: CurrentUser=Depends(require_permission("risk:read"))):
    with _engine.connect() as c:
        row = c.execute(text("SELECT * FROM risk_assessments WHERE customer_id=:cid"),{"cid":customer_id}).fetchone()
    if not row:
        return {"customer_id":customer_id,"risk_score":0.0,"risk_band":"low","credit_risk":0.0,"fraud_risk":0.0,"aml_risk":0.0}
    return dict(row._mapping)

@router.get("/portfolio")
def portfolio_risk(cu: CurrentUser=Depends(require_permission("risk:read"))):
    with _engine.connect() as c:
        total = c.execute(text("SELECT COUNT(*) FROM risk_assessments")).fetchone()[0]
        avg   = c.execute(text("SELECT COALESCE(AVG(risk_score),0) FROM risk_assessments")).fetchone()[0]
        rows  = c.execute(text("SELECT risk_band, COUNT(*) as cnt FROM risk_assessments GROUP BY risk_band")).fetchall()
    return {"total":total,"avg_score":round(avg,2),"by_band":{r[0]:r[1] for r in rows}}

@router.get("/segment/{band}")
def segment_risk(band: str, cu: CurrentUser=Depends(require_permission("risk:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("SELECT * FROM risk_assessments WHERE risk_band=:b ORDER BY risk_score DESC"),{"b":band}).fetchall()
    return {"customers":[dict(r._mapping) for r in rows],"total":len(rows)}
