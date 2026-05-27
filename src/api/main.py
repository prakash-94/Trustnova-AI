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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator

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


# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


# --- Dashboard Route ---
@app.get("/dashboard", tags=["Dashboard"], include_in_schema=False)
async def serve_dashboard():
    """Serve the enterprise dashboard SPA."""
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"error": "Dashboard not found. Ensure frontend/index.html exists."}


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
