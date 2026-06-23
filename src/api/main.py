"""
Banking AI Copilot — Main FastAPI Application.

Entry point for the backend API. Configures CORS, security headers,
rate limiting, authentication, and mounts all route modules.

Run with:
    uvicorn src.api.main:app --reload --port 8000
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

# Import route modules
from src.api.routes import chat, fraud, customer, trust, documents, feedback
from src.api.routes import rag_eval as rag_eval_module
from src.api.routes import customers, loans, aml, kyc, risk, treasury
from src.api.routes import access_requests
from src.api.routes import kpi as kpi_module
# Bank-wide Operations routes (separate from customer-specific routes)
from src.api.routes import accounts as accounts_module
from src.api.routes import transactions as transactions_module
from src.api import auth as auth_module
# Communication & Admin routes
from src.api.routes import notifications as notifications_module
from src.api.routes import announcements as announcements_module
from src.api.routes import bug_reports as bug_reports_module
from src.api.routes import admin_users as admin_users_module
# Executive & Banker features
from src.api.routes import appointments as appointments_module
from src.api.routes import credit_cards as credit_cards_module
from src.api.routes import compliance as compliance_module


# ── Lifespan (startup / shutdown) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed demo users and initialize DB tables on startup."""
    print("=" * 60)
    print("  Banking AI Copilot — Starting Up")
    print("=" * 60)
    print(f"  Time:     {datetime.now().isoformat()}")
    print(f"  Database: {os.getenv('DATABASE_URL', 'sqlite:///./banking.db')}")
    print(f"  LLM:      {os.getenv('LLM_PROVIDER','groq').upper()} / {os.getenv('LLM_MODEL','llama-3.3-70b-versatile')}")
    print(f"  Groq:     {'configured' if os.getenv('GROQ_API_KEY') else 'NOT SET'}")
    print(f"  OpenAI:   {'configured' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
    print(f"  Pinecone: {'configured' if os.getenv('PINECONE_API_KEY') else 'NOT SET'}")
    print(f"  Auth:     JWT ({'DEMO key — change JWT_SECRET_KEY in prod!' if os.getenv('JWT_SECRET_KEY','CHANGE-ME') == 'CHANGE-ME-IN-PRODUCTION-use-256-bit-random-key' else 'custom key set'})")
    print(f"  CORS:     {_cors_origins}")

    # Apply DB schema migrations (add missing columns to old volumes)
    from src.models.database import run_migrations, ensure_indexes
    run_migrations()
    ensure_indexes()

    # Seed auth tables and demo users
    auth_module.ensure_users_table()

    # Pre-compute semantic router intent vectors (runs once, cached for server lifetime)
    try:
        from src.rag.semantic_router import precompute_intent_vectors
        precompute_intent_vectors()
    except Exception as _e:
        print(f"  [SemanticRouter] Precompute skipped: {_e}")

    print(f"  Dashboard: http://localhost:8000/login")
    print("=" * 60)
    yield
    print("\n  Banking AI Copilot — Shutting Down")


# ── Rate Limiter ───────────────────────────────────────────────
_rate_limit = os.getenv("RATE_LIMIT", "60/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[_rate_limit])

# ── FastAPI App ────────────────────────────────────────────────
app = FastAPI(
    title="Banking AI Copilot",
    description=(
        "Enterprise Banking AI Copilot Platform — intelligent document retrieval, "
        "fraud detection, customer intelligence, AI trust scoring, and a self-improving feedback engine.\n\n"
        "**Authentication:** All endpoints except `/auth/login` and `/health` require a Bearer JWT.\n"
        "Obtain a token via `POST /auth/login`."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Attach Limiter ─────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS Middleware ────────────────────────────────────────────
# Production: set CORS_ORIGINS=https://app.yourbank.com,https://admin.yourbank.com
_cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
_cors_origins = (
    ["*"]
    if _cors_origins_raw.strip() == "*"
    else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
)
app.add_middleware(GZipMiddleware, minimum_size=512)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,  # app uses Bearer JWT, not cookies — credentials mode not needed
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ── Security Headers Middleware ────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if os.getenv("ENVIRONMENT", "development") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # CSP only on HTML responses — API JSON responses don't need it and
    # adding connect-src 'self' here would confuse browsers/DevTools.
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src *;"
        )
    return response


# ── Prometheus Metrics ─────────────────────────────────────────
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    excluded_handlers=["/metrics", "/health"],
    inprogress_name="http_requests_in_progress",
    inprogress_labels=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False, tags=["Monitoring"])


# ── Route Modules ──────────────────────────────────────────────
# Auth (no auth required on /auth/login)
app.include_router(auth_module.router, prefix="/auth", tags=["Authentication"])

# Business routes (all protected — auth dependencies declared in each route)
app.include_router(chat.router,      prefix="/chat",      tags=["Chat — AI Copilot"])
app.include_router(rag_eval_module.router, prefix="/rag/eval", tags=["RAG — Eval Pipeline"])
app.include_router(fraud.router,     prefix="/fraud",     tags=["Fraud Detection"])
app.include_router(customer.router,  prefix="/customer",  tags=["Customer Intelligence"])
app.include_router(trust.router,     prefix="/trust",     tags=["Trust Scoring"])
app.include_router(documents.router, prefix="/documents", tags=["Document Intelligence"])
app.include_router(feedback.router,  prefix="/feedback",  tags=["Feedback Loop"])
# New enterprise routes
app.include_router(customers.router, prefix="/customers", tags=["Customer 360"])
app.include_router(loans.router,     prefix="/loans",     tags=["Loans"])
app.include_router(aml.router,       prefix="/aml",       tags=["AML"])
app.include_router(kyc.router,       prefix="/kyc",       tags=["KYC"])
app.include_router(risk.router,      prefix="/risk",      tags=["Risk"])
app.include_router(treasury.router,              prefix="/treasury",        tags=["Treasury"])
app.include_router(access_requests.router,       prefix="/access-requests", tags=["Access Requests"])
# Bank Operations: bank-wide account + transaction views (not customer-scoped)
app.include_router(accounts_module.router,        prefix="/accounts",        tags=["Bank Accounts"])
app.include_router(transactions_module.router,    prefix="/transactions",    tags=["Bank Transactions"])
app.include_router(kpi_module.router,             prefix="/kpi",             tags=["KPI Stats"])
# Communication & Admin
app.include_router(notifications_module.router,   prefix="/notifications",   tags=["Notifications"])
app.include_router(announcements_module.router,   prefix="/announcements",   tags=["Announcements"])
app.include_router(bug_reports_module.router,     prefix="/bug-reports",     tags=["Bug Reports"])
app.include_router(admin_users_module.router,     prefix="/admin",           tags=["Admin"])
app.include_router(appointments_module.router,    prefix="/appointments",    tags=["Appointments"])
app.include_router(credit_cards_module.router,    prefix="/credit-cards",    tags=["Credit Cards"])
app.include_router(compliance_module.router,      prefix="/compliance",      tags=["Compliance"])


# ── Health Check (no auth) ─────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "service": "Banking AI Copilot",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
            "pinecone_key_set": bool(os.getenv("PINECONE_API_KEY")),
            "database_url": os.getenv("DATABASE_URL", "sqlite:///./banking.db").split("///")[0] + "///***",
            "auth_enabled": True,
        },
    }
