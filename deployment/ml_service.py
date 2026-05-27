"""
Banking AI Copilot — ML Inference Micro-Service.

Standalone FastAPI service that loads pre-trained fraud detection models
and exposes prediction endpoints. Runs as a separate container for
independent scaling and isolation.
"""
import os
import pickle
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

# ── Configuration ────────────────────────────────────────────
MODEL_DIR = "models"
MODELS = {
    "xgboost": "fraud_detector_v1.pkl",
    "xgboost_v2": "fraud_xgboost_v2.pkl",
    "random_forest": "fraud_random_forest.pkl",
    "isolation_forest": "fraud_isolation_forest.pkl",
    "autoencoder": "fraud_autoencoder.pkl",
    "lstm": "fraud_lstm.pkl",
    "retention": "retention_model.pkl",
}

FEATURE_COLS = [
    "amount", "hour", "geo_mismatch", "device_new",
    "amount_zscore", "velocity_30m", "credit_score",
    "account_age_days", "is_weekend", "merchant_risk",
]

# ── FastAPI App ──────────────────────────────────────────────
app = FastAPI(
    title="Banking AI Copilot — ML Service",
    description="Fraud detection model inference micro-service",
    version="1.0.0",
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Model Cache ──────────────────────────────────────────────
_model_cache: dict = {}


def load_model(name: str):
    """Load and cache a model from disk."""
    if name not in _model_cache:
        filename = MODELS.get(name)
        if not filename:
            raise HTTPException(404, f"Unknown model: {name}")
        path = os.path.join(MODEL_DIR, filename)
        if not os.path.exists(path):
            raise HTTPException(404, f"Model file not found: {path}")
        with open(path, "rb") as f:
            _model_cache[name] = pickle.load(f)
    return _model_cache[name]


# ── Schemas ──────────────────────────────────────────────────
class TransactionInput(BaseModel):
    """Single transaction for fraud scoring."""
    amount: float = Field(..., description="Transaction amount in USD")
    hour: int = Field(0, ge=0, le=23, description="Hour of day (0-23)")
    geo_mismatch: int = Field(0, ge=0, le=1, description="Geographic mismatch flag")
    device_new: int = Field(0, ge=0, le=1, description="New device flag")
    amount_zscore: float = Field(0.0, description="Z-score of amount vs. customer avg")
    velocity_30m: int = Field(0, ge=0, description="Transactions in last 30 minutes")
    credit_score: int = Field(700, ge=300, le=850, description="Customer credit score")
    account_age_days: int = Field(365, ge=0, description="Account age in days")
    is_weekend: int = Field(0, ge=0, le=1, description="Weekend flag")
    merchant_risk: float = Field(0.0, ge=0.0, le=1.0, description="Merchant risk score")
    model: Optional[str] = Field("xgboost", description="Model to use for prediction")


class PredictionResponse(BaseModel):
    """Fraud prediction result."""
    fraud_probability: float
    risk_tier: str
    is_fraud_predicted: bool
    top_risk_factors: list
    model_used: str
    latency_ms: float


class BatchInput(BaseModel):
    """Batch of transactions for scoring."""
    transactions: list[TransactionInput]


# ── Endpoints ────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check for the ML service."""
    available_models = []
    for name, filename in MODELS.items():
        path = os.path.join(MODEL_DIR, filename)
        available_models.append({
            "name": name,
            "file": filename,
            "loaded": name in _model_cache,
            "exists": os.path.exists(path),
        })
    return {
        "status": "ok",
        "service": "ml-inference",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "models": available_models,
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict_fraud(txn: TransactionInput):
    """Score a single transaction for fraud."""
    start = datetime.now()

    model_name = txn.model or "xgboost"
    model = load_model(model_name)

    # Build feature vector
    features = pd.DataFrame([{
        col: getattr(txn, col) for col in FEATURE_COLS
    }])[FEATURE_COLS].fillna(0)

    # Predict
    try:
        fraud_prob = float(model.predict_proba(features)[0, 1])
    except AttributeError:
        # Isolation Forest returns -1/1 labels, no predict_proba
        score = model.decision_function(features)[0]
        fraud_prob = max(0.0, min(1.0, 1.0 - (score + 0.5)))

    is_fraud = fraud_prob >= 0.5
    risk_tier = "HIGH" if fraud_prob > 0.7 else "MEDIUM" if fraud_prob > 0.3 else "LOW"

    # Top risk factors via feature importance
    top_factors = []
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        contributions = []
        for i, col in enumerate(FEATURE_COLS):
            val = features.iloc[0][col]
            contributions.append({
                "feature": col,
                "value": float(val),
                "importance": float(importances[i]),
                "contribution": float(importances[i] * abs(val)),
            })
        contributions.sort(key=lambda x: x["contribution"], reverse=True)
        top_factors = contributions[:3]

    latency = (datetime.now() - start).total_seconds() * 1000

    return PredictionResponse(
        fraud_probability=round(fraud_prob, 4),
        risk_tier=risk_tier,
        is_fraud_predicted=is_fraud,
        top_risk_factors=top_factors,
        model_used=model_name,
        latency_ms=round(latency, 2),
    )


@app.post("/predict/batch")
async def predict_batch(batch: BatchInput):
    """Score a batch of transactions."""
    results = []
    for txn in batch.transactions:
        result = await predict_fraud(txn)
        results.append(result)
    return {"predictions": results, "count": len(results)}


@app.get("/models")
async def list_models():
    """List all available models and their status."""
    models = []
    for name, filename in MODELS.items():
        path = os.path.join(MODEL_DIR, filename)
        models.append({
            "name": name,
            "file": filename,
            "loaded": name in _model_cache,
            "exists": os.path.exists(path),
            "size_mb": round(os.path.getsize(path) / 1048576, 2) if os.path.exists(path) else None,
        })
    return {"models": models}
