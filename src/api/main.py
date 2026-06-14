import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from src.api import auth as auth_module
from src.api.routes import (
    chat, fraud, trust, documents,
    customers, accounts, transactions, loans,
    aml, kyc, risk, treasury,
    kpi, notifications, announcements, bug_reports,
    admin_users, appointments, credit_cards, access_requests,
)

try:
    from src.api.routes import feedback
    _has_feedback = True
except ImportError:
    _has_feedback = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("  TrustNova AI — Banking Copilot Starting")
    print("=" * 60)
    print(f"  Time:     {datetime.now().isoformat()}")
    print(f"  Database: {os.getenv('DATABASE_URL', 'sqlite:///./banking.db')}")
    auth_module.ensure_users_table()
    print(f"  API Docs: http://localhost:8001/docs")
    print("=" * 60)
    yield
    print("\n  TrustNova AI — Shutting Down")


app = FastAPI(
    title="TrustNova AI — Banking Copilot",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

_cors_raw = os.getenv("CORS_ORIGINS", "*")
_cors_list = ["*"] if _cors_raw.strip() == "*" else [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=_cors_raw.strip() != "*",
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


# Auth
app.include_router(auth_module.router,    prefix="/auth",            tags=["Auth"])

# AI / Trust
app.include_router(chat.router,           prefix="/chat",            tags=["AI Copilot"])
app.include_router(trust.router,          prefix="/trust",           tags=["Trust"])
app.include_router(documents.router,      prefix="/documents",       tags=["Documents"])
if _has_feedback:
    app.include_router(feedback.router,   prefix="/feedback",        tags=["Feedback"])

# Core Banking
app.include_router(customers.router,      prefix="/customers",       tags=["Customers"])
app.include_router(accounts.router,       prefix="/accounts",        tags=["Accounts"])
app.include_router(transactions.router,   prefix="/transactions",    tags=["Transactions"])
app.include_router(loans.router,          prefix="/loans",           tags=["Loans"])

# Compliance & Risk
app.include_router(fraud.router,          prefix="/fraud",           tags=["Fraud"])
app.include_router(aml.router,            prefix="/aml",             tags=["AML"])
app.include_router(kyc.router,            prefix="/kyc",             tags=["KYC"])
app.include_router(risk.router,           prefix="/risk",            tags=["Risk"])

# Treasury
app.include_router(treasury.router,       prefix="/treasury",        tags=["Treasury"])

# Operations
app.include_router(appointments.router,   prefix="/appointments",    tags=["Appointments"])
app.include_router(credit_cards.router,   prefix="/credit-cards",    tags=["Credit Cards"])

# Admin
app.include_router(kpi.router,            prefix="/kpi",             tags=["KPI"])
app.include_router(notifications.router,  prefix="/notifications",   tags=["Notifications"])
app.include_router(announcements.router,  prefix="/announcements",   tags=["Announcements"])
app.include_router(bug_reports.router,    prefix="/bug-reports",     tags=["Bug Reports"])
app.include_router(admin_users.router,    prefix="/admin/users",     tags=["Admin"])
app.include_router(access_requests.router,prefix="/access-requests", tags=["Access Requests"])


@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "service": "TrustNova AI",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse({"service": "TrustNova AI Banking Copilot", "docs": "/docs"})
