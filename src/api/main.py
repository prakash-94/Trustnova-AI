"""
Banking AI Copilot — Main FastAPI Application.

Entry point for the backend API. Configures CORS, mounts all route modules,
serves the enterprise dashboard, and provides the /health endpoint.

Run with:
    uvicorn src.api.main:app --reload --port 8000
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
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


# --- Lifespan (startup / shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    print("=" * 60)
    print("  Banking AI Copilot — Starting Up")
    print("=" * 60)
    print(f"  Time:     {datetime.now().isoformat()}")
    print(f"  Database: {os.getenv('DATABASE_URL', 'sqlite:///./banking.db')}")
    print(f"  OpenAI:   {'configured' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
    print(f"  Pinecone: {'configured' if os.getenv('PINECONE_API_KEY') else 'NOT SET'}")
    print(f"  Dashboard: http://localhost:8000/dashboard")
    print("=" * 60)
    yield
    print("\n  Banking AI Copilot — Shutting Down")


# --- Rate Limiter ---
# RATE_LIMIT env var: default "60/minute". Override per environment.
_rate_limit = os.getenv("RATE_LIMIT", "60/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[_rate_limit])

# --- FastAPI App ---
app = FastAPI(
    title="Banking AI Copilot",
    description=(
        "Enterprise Banking AI Copilot Platform — providing intelligent document retrieval, "
        "fraud detection, customer intelligence, AI trust scoring, and a self-improving feedback engine."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# --- Attach Limiter State ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- CORS Middleware ---
# CORS_ORIGINS env var is a comma-separated list of allowed origins.
# Example: CORS_ORIGINS=https://app.yourdomain.com,https://admin.yourdomain.com
# Defaults to "*" for local development only.
_cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
_cors_origins = (
    ["*"]
    if _cors_origins_raw.strip() == "*"
    else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins_raw.strip() != "*",  # credentials require explicit origin list
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


# --- Prometheus Metrics ---
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    excluded_handlers=["/metrics", "/health"],
    env_var_name="ENABLE_METRICS",
    inprogress_name="http_requests_in_progress",
    inprogress_labels=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False, tags=["Monitoring"])


# --- Mount Route Modules ---
app.include_router(chat.router, prefix="/chat", tags=["Chat — AI Copilot"])
app.include_router(fraud.router, prefix="/fraud", tags=["Fraud Detection"])
app.include_router(customer.router, prefix="/customer", tags=["Customer Intelligence"])
app.include_router(trust.router, prefix="/trust", tags=["Trust Scoring"])
app.include_router(documents.router, prefix="/documents", tags=["Document Intelligence"])
app.include_router(feedback.router, prefix="/feedback", tags=["Feedback Loop"])


# --- Static Files (Phase 9 Dashboard) ---
# src/api/main.py → go up 2 levels → project root → frontend/
_file_relative = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)
_cwd_relative = os.path.join(os.getcwd(), "frontend")
frontend_dir = _file_relative if os.path.isdir(_file_relative) else _cwd_relative

if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    print(f"  Dashboard: serving from {frontend_dir}")
else:
    print(f"  WARNING: frontend dir not found! Tried:\n    {_file_relative}\n    {_cwd_relative}")


# --- Dashboard Route ---
@app.get("/dashboard", tags=["Dashboard"], include_in_schema=False)
async def serve_dashboard():
    """Serve the enterprise dashboard SPA."""
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return {"error": f"Dashboard not found at {index_path}. Run from project root."}


# --- Health Check ---
@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint. Returns system status and configuration state.
    """
    return {
        "status": "ok",
        "service": "Banking AI Copilot",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
            "pinecone_key_set": bool(os.getenv("PINECONE_API_KEY")),
            "database_url": os.getenv("DATABASE_URL", "sqlite:///./banking.db"),
        },
    }


@app.get("/", tags=["System"])
async def root():
    """Root endpoint — redirects to API docs."""
    return {
        "message": "Banking AI Copilot API",
        "docs": "/docs",
        "health": "/health",
        "dashboard": "/dashboard",
    }
