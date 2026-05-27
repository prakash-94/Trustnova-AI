# =============================================================
#  Banking AI Copilot — ML Inference Service
#  Lightweight FastAPI service for fraud model predictions
# =============================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for XGBoost
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Minimal ML dependencies ─────────────────────────────────
COPY deployment/requirements.ml.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.ml.txt

# ── Copy models & inference code ─────────────────────────────
COPY models/ ./models/
COPY deployment/ml_service.py ./ml_service.py

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "ml_service:app", "--host", "0.0.0.0", "--port", "8001"]
