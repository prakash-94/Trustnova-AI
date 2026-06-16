"""Customer management endpoints — real SQLite banking.db customers table."""
import uuid, datetime, hashlib, random
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from src.api.auth import CurrentUser, require_permission, log_audit
from src.models.database import engine

router = APIRouter()

_AREA_CODES = ["212","310","312","404","415","469","512","602","617","702",
               "713","718","770","786","813","832","858","917","972","305"]
_CITIES = [
    ("New York","NY"),("Los Angeles","CA"),("Chicago","IL"),("Houston","TX"),
    ("Phoenix","AZ"),("Philadelphia","PA"),("San Antonio","TX"),("San Diego","CA"),
    ("Dallas","TX"),("San Jose","CA"),("Austin","TX"),("Jacksonville","FL"),
    ("Fort Worth","TX"),("Columbus","OH"),("Charlotte","NC"),("Indianapolis","IN"),
    ("San Francisco","CA"),("Seattle","WA"),("Denver","CO"),("Nashville","TN"),
    ("Miami","FL"),("Atlanta","GA"),("Portland","OR"),("Baltimore","MD"),
    ("Las Vegas","NV"),("Louisville","KY"),("Memphis","TN"),("Milwaukee","WI"),
    ("Albuquerque","NM"),("Tucson","AZ"),("Fresno","CA"),("Sacramento","CA"),
]


def _seeded(cid: str, suffix: str) -> random.Random:
    seed = int(hashlib.md5((cid + suffix).encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def _phone(cid: str) -> str:
    rng = _seeded(cid, "_phone")
    return f"({rng.choice(_AREA_CODES)}) {rng.randint(200,999)}-{rng.randint(1000,9999)}"


def _city_state(cid: str) -> tuple[str, str]:
    return _seeded(cid, "_loc").choice(_CITIES)


def _row_to_customer(row: dict) -> dict:
    cid = row.get("customer_id") or row.get("id", "")
    city = row.get("address_city") or _city_state(cid)[0]
    state = row.get("address_state") or _city_state(cid)[1]
    return {
        "id":                cid,
        "first_name":        row.get("first_name", ""),
        "last_name":         row.get("last_name", ""),
        "email":             row.get("email", ""),
        "phone":             row.get("phone") or _phone(cid),
        "segment":           row.get("segment", "retail"),
        "customer_type":     row.get("customer_type", "individual"),
        "kyc_status":        row.get("kyc_status", "pending"),
        "aml_risk_rating":   row.get("aml_risk_rating", "low"),
        "credit_score":      row.get("credit_score"),
        "annual_income":     row.get("annual_income"),
        "employment_status": row.get("employment_status"),
        "is_pep":            bool(row.get("is_pep", False)),
        "is_sanctioned":     bool(row.get("is_sanctioned", False)),
        "address_city":      city,
        "address_state":     state,
        "is_active":         bool(row.get("is_active", True)),
        "created_at":        row.get("created_at"),
    }


class NewCustomerRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    credit_score: Optional[int] = 650
    annual_income: Optional[float] = 50000.0
    segment: Optional[str] = "retail"
    customer_type: Optional[str] = "individual"
    aml_risk_rating: Optional[str] = "low"
    address_city: Optional[str] = None
    address_state: Optional[str] = None
    account_type: Optional[str] = "checking"
    opening_balance: Optional[float] = 0.0


@router.post("")
async def create_customer(
    body: NewCustomerRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission("customers:write")),
):
    cid = uuid.uuid4().hex[:8]
    now = datetime.datetime.utcnow().isoformat()
    today = now[:10]
    risk = (body.aml_risk_rating or "low").lower()
    if risk not in ("low", "medium", "high", "very high"):
        risk = "low"

    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT customer_id FROM customers WHERE email = :email"), {"email": body.email}
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="A customer with this email already exists.")

        conn.execute(text("""
            INSERT INTO customers
                (customer_id, first_name, last_name, email, phone, segment, customer_type,
                 kyc_status, aml_risk_rating, credit_score, annual_income,
                 is_pep, is_sanctioned, is_active, created_at)
            VALUES
                (:id, :fn, :ln, :email, :phone, :segment, :ctype,
                 'pending', :risk, :credit, :income,
                 0, 0, 1, :now)
        """), {
            "id": cid,
            "fn": body.first_name.strip(),
            "ln": body.last_name.strip(),
            "email": body.email.strip(),
            "phone": body.phone,
            "segment": body.segment or "retail",
            "ctype": body.customer_type or "individual",
            "risk": risk,
            "credit": body.credit_score or 650,
            "income": body.annual_income or 0,
            "city": body.address_city,
            "state": body.address_state,
            "now": now,
        })

        # Generate IDs matching existing DB format
        import random as _rng
        acct_num = "AC" + "".join([str(_rng.randint(0, 9)) for _ in range(10)])
        aid = str(_rng.randint(10**18, 10**19 - 1))
        bal_cents = int((body.opening_balance or 0) * 100)
        conn.execute(text("""
            INSERT INTO accounts
                (id, customer_id, account_number, account_type, status, balance_cents, currency, opened_date)
            VALUES
                (:aid, :cid, :acct, :atype, 'active', :bal, 'USD', :today)
        """), {
            "aid": aid, "cid": cid,
            "acct": acct_num,
            "atype": body.account_type or "checking",
            "bal": bal_cents,
            "today": today,
        })

    log_audit(current_user.username, current_user.role, "create", "customer",
              resource_id=cid, customer_id=cid,
              ip=request.client.host if request.client else "")

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM customers WHERE customer_id = :id"), {"id": cid}).fetchone()
    return {"customer": _row_to_customer(dict(row._mapping)), "message": "Customer created successfully."}


@router.get("/search")
async def search_customers(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, le=100),
    current_user: CurrentUser = Depends(require_permission("customers:read")),
):
    q_stripped = q.strip().lower()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT * FROM customers
            WHERE LOWER(first_name) LIKE :q
               OR LOWER(last_name) LIKE :q
               OR LOWER(first_name || ' ' || last_name) LIKE :q
               OR LOWER(last_name || ' ' || first_name) LIKE :q
               OR LOWER(COALESCE(name, '')) LIKE :q
            ORDER BY first_name, last_name
            LIMIT :limit
        """), {"q": f"%{q_stripped}%", "limit": limit}).fetchall()
    return {"results": [_row_to_customer(dict(r._mapping)) for r in rows], "total": len(rows)}


@router.get("/list")
async def list_customers(
    limit: int = Query(200, le=1100),
    offset: int = Query(0, ge=0),
    risk_level: Optional[str] = None,
    current_user: CurrentUser = Depends(require_permission("customers:read")),
):
    filters, params = [], {"limit": limit, "offset": offset}
    if risk_level:
        filters.append("LOWER(aml_risk_rating) = :risk_level")
        params["risk_level"] = risk_level.lower()
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM customers {where}"), params).scalar()
        rows = conn.execute(text(
            f"SELECT * FROM customers {where} ORDER BY first_name, last_name LIMIT :limit OFFSET :offset"
        ), params).fetchall()
    return {"customers": [_row_to_customer(dict(r._mapping)) for r in rows], "total": total}


@router.get("/stats/overview")
async def get_customer_stats(
    current_user: CurrentUser = Depends(require_permission("customers:read")),
):
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 0
        try:
            ai_queries = conn.execute(text(
                "SELECT COUNT(*) FROM llm_usage WHERE DATE(timestamp) = DATE('now')"
            )).scalar() or 0
        except Exception:
            ai_queries = 0
    return {"total_customers": total, "ai_queries_today": ai_queries}


@router.get("/{customer_id}/accounts")
async def get_customer_accounts(
    customer_id: str,
    current_user: CurrentUser = Depends(require_permission("accounts:read")),
):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT * FROM accounts WHERE customer_id = :cid ORDER BY opened_date DESC"
        ), {"cid": customer_id}).fetchall()
    if not rows:
        return {"accounts": []}
    accounts = []
    for r in rows:
        d = dict(r._mapping)
        accounts.append({
            "id": d.get("id", ""),
            "account_number": d.get("account_number", ""),
            "account_type": d.get("account_type", "checking"),
            "status": d.get("status", "active"),
            "balance_cents": int(d.get("balance_cents") or 0),
            "currency": d.get("currency", "USD"),
            "opened_date": d.get("opened_date"),
            "interest_rate": d.get("interest_rate"),
        })
    return {"accounts": accounts}


@router.get("/{customer_id}/transactions")
async def get_customer_transactions(
    customer_id: str,
    limit: int = Query(100, le=500),
    current_user: CurrentUser = Depends(require_permission("transactions:read")),
):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT transaction_id, customer_id, amount, merchant, category,
                   location, timestamp, is_fraud, merchant_risk
            FROM enriched_transactions
            WHERE customer_id = :cid
            ORDER BY timestamp DESC LIMIT :limit
        """), {"cid": customer_id, "limit": limit}).fetchall()
    txns = []
    for r in rows:
        d = dict(r._mapping)
        amt = float(d.get("amount") or 0)
        txns.append({
            "id": d["transaction_id"],
            "transaction_type": "credit" if amt > 0 else "debit",
            "amount_cents": int(abs(amt) * 100),
            "description": d.get("merchant") or "Unknown",
            "merchant_name": d.get("merchant") or "",
            "merchant_category": d.get("category") or "other",
            "location": d.get("location") or "",
            "channel": "pos",
            "status": "completed",
            "is_flagged": bool(d.get("is_fraud")),
            "created_at": d.get("timestamp") or "",
        })
    return {"transactions": txns}


@router.get("/{customer_id}/summary")
async def get_customer_summary(
    customer_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_permission("customers:read")),
):
    with engine.connect() as conn:
        cust_row = conn.execute(text(
            "SELECT * FROM customers WHERE customer_id = :cid"
        ), {"cid": customer_id}).fetchone()
        if not cust_row:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer = _row_to_customer(dict(cust_row._mapping))

        acct_rows = conn.execute(text(
            "SELECT * FROM accounts WHERE customer_id = :cid ORDER BY opened_date DESC LIMIT 5"
        ), {"cid": customer_id}).fetchall()

        txn_rows = conn.execute(text("""
            SELECT transaction_id, amount, merchant, category, location, timestamp, is_fraud
            FROM enriched_transactions
            WHERE customer_id = :cid ORDER BY timestamp DESC LIMIT 5
        """), {"cid": customer_id}).fetchall()

        fraud_count = conn.execute(text(
            "SELECT COUNT(*) FROM fraud_alerts WHERE customer_id = :cid"
        ), {"cid": customer_id}).scalar() or 0

        try:
            alert_count = conn.execute(text(
                "SELECT COUNT(*) FROM alerts WHERE customer_id = :cid AND status='open'"
            ), {"cid": customer_id}).scalar() or 0
        except Exception:
            alert_count = 0

    accounts = []
    total_balance = 0
    for r in acct_rows:
        d = dict(r._mapping)
        bal = int(d.get("balance_cents") or 0)
        total_balance += bal
        accounts.append({
            "id": d.get("id", ""),
            "account_number": d.get("account_number", ""),
            "account_type": d.get("account_type", "checking"),
            "status": d.get("status", "active"),
            "balance_cents": bal,
            "currency": "USD",
            "opened_date": d.get("opened_date"),
        })

    recent_txns = []
    for r in txn_rows:
        d = dict(r._mapping)
        amt = float(d.get("amount") or 0)
        recent_txns.append({
            "id": d["transaction_id"],
            "transaction_type": "credit" if amt > 0 else "debit",
            "amount_cents": int(abs(amt) * 100),
            "description": d.get("merchant") or "Unknown",
            "merchant_category": d.get("category") or "other",
            "location": d.get("location") or "",
            "status": "completed",
            "is_flagged": bool(d.get("is_fraud")),
            "created_at": d.get("timestamp") or "",
        })

    log_audit(current_user.username, current_user.role, "view_360", "customer",
              resource_id=customer_id, customer_id=customer_id,
              ip=request.client.host if request.client else "")

    return {
        "customer": customer,
        "accounts": accounts,
        "recent_transactions": recent_txns,
        "summary": {
            "total_balance_cents": total_balance,
            "account_count": len(accounts),
            "flagged_transaction_count": fraud_count,
            "kyc_status": customer["kyc_status"],
            "aml_risk": customer["aml_risk_rating"],
            "credit_score": customer["credit_score"],
            "alert_count": alert_count,
            "fraud_count": fraud_count,
        },
    }


@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_permission("customers:read")),
):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT * FROM customers WHERE customer_id = :cid"
        ), {"cid": customer_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    log_audit(current_user.username, current_user.role, "read", "customer",
              resource_id=customer_id, customer_id=customer_id,
              ip=request.client.host if request.client else "")
    return _row_to_customer(dict(row._mapping))
