"""
Fraud Detection Route — Real-time transaction fraud scoring.

Supports:
  - XGBoost prediction with SHAP feature attribution
  - Ensemble scoring: XGBoost + Isolation Forest average
  - Human-readable fraud explanation (rule-based or GPT-4)
  - Risk tier classification: Low (0-0.3) · Medium (0.3-0.7) · High (0.7-1.0)
"""
import os
import time
import pickle
import traceback

import numpy as np
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List

from src.api.auth import CurrentUser, require_permission

router = APIRouter()

MODEL_DIR = "models"


class TransactionInput(BaseModel):
    """Input transaction for fraud checking."""
    transaction_id: Optional[str] = Field(None, description="Transaction ID")
    customer_id: Optional[str] = Field(None, description="Customer ID for alert storage")
    amount: float = Field(..., description="Transaction amount in USD")
    hour: int = Field(..., ge=0, le=23, description="Hour of transaction (0-23)")
    geo_mismatch: int = Field(0, ge=0, le=1, description="1 if location differs from customer's usual")
    device_new: int = Field(0, ge=0, le=1, description="1 if transaction from a new device")
    is_weekend: int = Field(0, ge=0, le=1, description="1 if transaction on weekend")
    amount_zscore: Optional[float] = Field(0.0, description="Z-score of amount vs customer average")
    velocity_30m: Optional[int] = Field(0, description="Number of transactions in last 30 minutes")
    credit_score: Optional[int] = Field(700, ge=300, le=850, description="Customer credit score")
    account_age_days: Optional[int] = Field(365, description="Account age in days")
    merchant_risk: Optional[float] = Field(0.0, ge=0.0, le=1.0, description="Merchant risk score (0-1)")
    use_ensemble: Optional[bool] = Field(False, description="Use ensemble scoring (XGBoost + Isolation Forest)")
    use_llm_explanation: Optional[bool] = Field(False, description="Generate GPT-4 explanation (slower)")

    model_config = {"json_schema_extra": {
        "examples": [{
            "amount": 5000.00,
            "hour": 2,
            "geo_mismatch": 1,
            "device_new": 1,
            "is_weekend": 0,
            "amount_zscore": 3.5,
            "velocity_30m": 4,
            "credit_score": 450,
            "account_age_days": 30,
            "merchant_risk": 0.8,
            "use_ensemble": True,
        }]
    }}


class RiskFactor(BaseModel):
    """A single risk factor contributing to fraud score."""
    feature: str
    value: float
    importance: float
    contribution: float
    direction: Optional[str] = None


class FraudCheckResponse(BaseModel):
    """Response from fraud check endpoint."""
    status: str
    fraud_probability: Optional[float] = None
    risk_tier: Optional[str] = None
    top_risk_factors: Optional[List[RiskFactor]] = None
    explanation: Optional[str] = None
    models_used: Optional[List[str]] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


def _get_isolation_forest_score(txn_dict: dict) -> Optional[float]:
    """Get fraud probability from Isolation Forest model if available."""
    iso_path = os.path.join(MODEL_DIR, "fraud_isolation_forest.pkl")
    if not os.path.exists(iso_path):
        return None

    try:
        import pandas as pd
        from src.models.fraud_detector import FEATURE_COLS

        with open(iso_path, "rb") as f:
            iso_model = pickle.load(f)

        features = pd.DataFrame([txn_dict])[FEATURE_COLS].fillna(0)
        raw_score = iso_model.decision_function(features)[0]

        # Convert to probability-like (0-1, higher = more fraud)
        # Isolation Forest scores: lower = more anomalous
        prob = max(0.0, min(1.0, 0.5 - raw_score))
        return prob

    except Exception as e:
        print(f"  [Fraud] Isolation Forest scoring failed: {e}")
        return None


@router.get("/alerts", tags=["Fraud Detection"])
async def get_fraud_alerts(
    limit: int = 20,
    current_user: CurrentUser = Depends(require_permission("fraud")),
):
    """
    Get recent fraud alerts from the database.
    Returns flagged transactions with risk scores for the Fraud Monitor dashboard.
    """
    try:
        import pandas as pd
        from sqlalchemy import create_engine, text
        from dotenv import load_dotenv
        engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./banking.db"))

        df = pd.read_sql(
            text("SELECT * FROM fraud_alerts ORDER BY timestamp DESC LIMIT :lim"),
            engine,
            params={"lim": limit},
        )

        return {
            "status": "ok",
            "alerts": df.to_dict(orient="records"),
            "total": len(df),
        }
    except Exception as e:
        return {"status": "ok", "alerts": [], "total": 0}


@router.post("/check", response_model=FraudCheckResponse)
async def fraud_check(
    transaction: TransactionInput,
    request: Request = None,
    current_user: CurrentUser = Depends(require_permission("fraud")),
):
    """
    Check a transaction for fraud risk.

    Returns fraud probability, risk tier (Low/Medium/High),
    top risk factors with SHAP attribution, optional human-readable explanation.

    Supports ensemble scoring: average of XGBoost + Isolation Forest.
    """
    start_time = time.time()

    try:
        from src.models.fraud_detector import fraud_predict

        # Build transaction dict from request
        txn_dict = {
            "amount": transaction.amount,
            "hour": transaction.hour,
            "geo_mismatch": transaction.geo_mismatch,
            "device_new": transaction.device_new,
            "is_weekend": transaction.is_weekend,
            "amount_zscore": transaction.amount_zscore or 0.0,
            "velocity_30m": transaction.velocity_30m or 0,
            "credit_score": transaction.credit_score or 700,
            "account_age_days": transaction.account_age_days or 365,
            "merchant_risk": transaction.merchant_risk or 0.0,
        }

        # XGBoost prediction
        result = fraud_predict(txn_dict)
        xgb_prob = result["fraud_probability"]
        models_used = ["XGBoost"]

        # Ensemble scoring if requested
        final_prob = xgb_prob
        if transaction.use_ensemble:
            iso_prob = _get_isolation_forest_score(txn_dict)
            if iso_prob is not None:
                final_prob = round((xgb_prob + iso_prob) / 2, 4)
                models_used.append("Isolation Forest")

        # Risk tier
        if final_prob >= 0.7:
            risk_tier = "High"
        elif final_prob >= 0.3:
            risk_tier = "Medium"
        else:
            risk_tier = "Low"

        # SHAP-based risk factors
        risk_factors = []
        explanation = None
        try:
            from src.models.explainer import get_shap_explanation, _generate_fallback_explanation, generate_llm_explanation

            shap_result = get_shap_explanation(txn_dict)

            risk_factors = [
                RiskFactor(
                    feature=f["feature"],
                    value=f["value"],
                    importance=f["abs_shap"],
                    contribution=f["shap_value"],
                    direction=f["direction"],
                )
                for f in shap_result["top_3_shap_features"]
            ]

            # Generate explanation
            if transaction.use_llm_explanation:
                explanation = generate_llm_explanation(
                    txn_dict, final_prob, risk_tier,
                    shap_result["top_3_shap_features"],
                )
            else:
                explanation = _generate_fallback_explanation(
                    txn_dict, final_prob, risk_tier,
                    shap_result["top_3_shap_features"],
                )

        except Exception as shap_err:
            print(f"  [Fraud] SHAP explanation failed: {shap_err}")
            # Fallback to feature importance-based factors
            risk_factors = [
                RiskFactor(
                    feature=f["feature"],
                    value=f["value"],
                    importance=f["importance"],
                    contribution=f["contribution"],
                )
                for f in result.get("top_3_risk_factors", [])
            ]

        # Store alert for High/Medium risk
        if risk_tier in ("High", "Medium") and transaction.customer_id:
            try:
                from src.models.explainer import store_fraud_alert
                store_fraud_alert(
                    transaction_id=transaction.transaction_id or "unknown",
                    customer_id=transaction.customer_id,
                    fraud_probability=final_prob,
                    risk_tier=risk_tier,
                    explanation=explanation or "",
                    model_used="+".join(models_used),
                )
            except Exception:
                pass  # Don't fail the request if alert storage fails

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return FraudCheckResponse(
            status="ok",
            fraud_probability=final_prob,
            risk_tier=risk_tier,
            top_risk_factors=risk_factors,
            explanation=explanation,
            models_used=models_used,
            latency_ms=latency_ms,
        )

    except Exception as e:
        traceback.print_exc()
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return FraudCheckResponse(
            status="error",
            latency_ms=latency_ms,
            error=f"Fraud detection error: {str(e)}. Ensure model is trained (run: python -m src.models.fraud_detector).",
        )
