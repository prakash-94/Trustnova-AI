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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

# Import route modules
from src.api.routes import chat, fraud, customer, trust, documents, feedback
from src.api import auth as auth_module


# ── Lifespan (startup / shutdown) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed demo users and initialize DB tables on startup."""
    print("=" * 60)
    print("  Banking AI Copilot — Starting Up")
    print("=" * 60)
    print(f"  Time:     {datetime.now().isoformat()}")
    print(f"  Database: {os.getenv('DATABASE_URL', 'sqlite:///./banking.db')}")
    print(f"  OpenAI:   {'configured' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
    print(f"  Pinecone: {'configured' if os.getenv('PINECONE_API_KEY') else 'NOT SET'}")
    print(f"  Auth:     JWT ({'DEMO key — change JWT_SECRET_KEY in prod!' if os.getenv('JWT_SECRET_KEY','CHANGE-ME') == 'CHANGE-ME-IN-PRODUCTION-use-256-bit-random-key' else 'custom key set'})")

    # Seed auth tables and demo users
    auth_module.ensure_users_table()

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins_raw.strip() != "*",
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
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
    # Only add HSTS in production (when TLS is terminated at the load balancer)
    if os.getenv("ENVIRONMENT", "development") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Content-Security-Policy: allow self + CDN for Chart.js
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self';"
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
app.include_router(fraud.router,     prefix="/fraud",     tags=["Fraud Detection"])
app.include_router(customer.router,  prefix="/customer",  tags=["Customer Intelligence"])
app.include_router(trust.router,     prefix="/trust",     tags=["Trust Scoring"])
app.include_router(documents.router, prefix="/documents", tags=["Document Intelligence"])
app.include_router(feedback.router,  prefix="/feedback",  tags=["Feedback Loop"])


# ── Static Files ───────────────────────────────────────────────
_file_relative = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)
_cwd_relative = os.path.join(os.getcwd(), "frontend")
frontend_dir = _file_relative if os.path.isdir(_file_relative) else _cwd_relative

if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


# ── Page Routes ────────────────────────────────────────────────
@app.get("/login", tags=["UI"], include_in_schema=False)
async def serve_login():
    """Serve the login page."""
    path = os.path.join(frontend_dir, "login.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html",
                            headers={"Cache-Control": "no-store"})
    return JSONResponse({"error": "login.html not found"}, status_code=404)


@app.get("/dashboard", tags=["UI"], include_in_schema=False)
async def serve_dashboard():
    """Serve the main dashboard SPA (auth enforced client-side and via API)."""
    path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html",
                            headers={"Cache-Control": "no-store"})
    return JSONResponse({"error": "index.html not found"}, status_code=404)


@app.get("/", tags=["UI"], include_in_schema=False)
async def root():
    """Redirect root to login."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")


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
