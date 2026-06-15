# =============================================================
#  TrustNova AI — ML Inference Service
#  Lightweight FastAPI service for fraud model predictions
#  Docker Hub: chotu94/trusnova-ml
# =============================================================

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ── System deps for XGBoost / scikit-learn ────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── ML dependencies ───────────────────────────────────────────
COPY deployment/requirements.ml.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.ml.txt

# ── Inference service code ─────────────────────────────────────
COPY deployment/ml_service.py ./ml_service.py

# ── ML model artefacts ────────────────────────────────────────
# Models are generated locally (not stored in git).
# Place pkl files in models/ before building this image.
# Run: python -m src.models.train  to generate them.
RUN mkdir -p /app/models
COPY models/ /app/models/

# ── Non-root user ─────────────────────────────────────────────
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "ml_service:app", "--host", "0.0.0.0", "--port", "8001"]
