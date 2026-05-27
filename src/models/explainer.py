"""
Fraud Explanation Engine.

Provides two layers of fraud explanation:
  1. SHAP-based feature attribution — per-prediction SHAP values from XGBoost
  2. GPT-4 narrative explanation  — human-readable risk assessment via LLM router

Also stores explanation text alongside fraud scores in the fraud_alerts table.
"""
import os
import pickle
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")
MODEL_DIR = "models"


# --- SHAP Cache ---
_shap_explainer = None


def get_shap_explainer():
    """Get or create a cached SHAP TreeExplainer for XGBoost."""
    global _shap_explainer
    if _shap_explainer is None:
        import shap
        from src.models.fraud_detector import get_cached_model
        model = get_cached_model()
        _shap_explainer = shap.TreeExplainer(model)
    return _shap_explainer


def get_shap_explanation(transaction: dict) -> Dict:
    """
    Get SHAP-based feature attribution for a single transaction.

    Returns top 3 features ranked by absolute SHAP value, plus the
    raw SHAP values for all features.

    Args:
        transaction: dict with feature values matching FEATURE_COLS

    Returns:
        Dict with 'top_3_shap_features' and 'shap_values'
    """
    from src.models.fraud_detector import FEATURE_COLS

    explainer = get_shap_explainer()

    features = pd.DataFrame([transaction])[FEATURE_COLS].fillna(0)
    shap_values = explainer.shap_values(features)

    # For binary classification, shap_values may be a list [class_0, class_1]
    if isinstance(shap_values, list):
        sv = shap_values[1][0]  # Class 1 (fraud) SHAP values
    elif len(shap_values.shape) > 1:
        sv = shap_values[0]
    else:
        sv = shap_values

    # Build feature attribution list
    attributions = []
    for i, col in enumerate(FEATURE_COLS):
        attributions.append({
            "feature": col,
            "value": float(features.iloc[0][col]),
            "shap_value": float(sv[i]),
            "abs_shap": float(abs(sv[i])),
            "direction": "increases risk" if sv[i] > 0 else "decreases risk",
        })

    # Sort by absolute SHAP value
    attributions.sort(key=lambda x: x["abs_shap"], reverse=True)

    return {
        "top_3_shap_features": attributions[:3],
        "all_attributions": attributions,
        "base_value": float(explainer.expected_value[1]) if isinstance(explainer.expected_value, (list, np.ndarray)) else float(explainer.expected_value),
    }


def generate_llm_explanation(
    transaction: dict,
    fraud_probability: float,
    risk_tier: str,
    shap_features: List[Dict],
    customer_context: str = "",
) -> str:
    """
    Generate a human-readable fraud explanation using GPT-4 via LLM router.

    Args:
        transaction: Transaction feature dict
        fraud_probability: Model's fraud probability
        risk_tier: "Low", "Medium", or "High"
        shap_features: Top SHAP-ranked features from get_shap_explanation()
        customer_context: Optional customer context string

    Returns:
        Human-readable explanation string
    """
    try:
        from src.api.llm_router import route
        from src.api.prompts.fraud_analysis import build_fraud_explanation_prompt

        # Convert SHAP features to the format expected by the prompt
        risk_factors = [
            {
                "feature": f["feature"],
                "value": f["value"],
                "importance": f["abs_shap"],
                "contribution": f["shap_value"],
            }
            for f in shap_features
        ]

        prompt = build_fraud_explanation_prompt(
            transaction=transaction,
            fraud_probability=fraud_probability,
            risk_tier=risk_tier,
            top_risk_factors=risk_factors,
            customer_context=customer_context,
        )

        result = route("fraud_reasoning", prompt)
        return result["response"]

    except Exception as e:
        # Fallback: generate a simple rule-based explanation
        return _generate_fallback_explanation(
            transaction, fraud_probability, risk_tier, shap_features
        )


def _generate_fallback_explanation(
    transaction: dict,
    fraud_probability: float,
    risk_tier: str,
    shap_features: List[Dict],
) -> str:
    """Generate a rule-based explanation when LLM is unavailable."""
    lines = [f"RISK ASSESSMENT ({risk_tier} — {fraud_probability:.1%} fraud probability):"]

    for f in shap_features[:3]:
        feature = f["feature"]
        value = f["value"]
        direction = f["direction"]

        if feature == "amount":
            lines.append(f"- Transaction amount ${value:,.2f} {direction}")
        elif feature == "amount_zscore":
            lines.append(f"- Amount is {abs(value):.1f} standard deviations from customer average ({direction})")
        elif feature == "device_new" and value == 1:
            lines.append(f"- Transaction from a new/unrecognized device ({direction})")
        elif feature == "geo_mismatch" and value == 1:
            lines.append(f"- Geographic location differs from customer's usual pattern ({direction})")
        elif feature == "hour":
            lines.append(f"- Transaction at {int(value)}:00 ({direction})")
        elif feature == "velocity_30m":
            lines.append(f"- {int(value)} transactions in last 30 minutes ({direction})")
        elif feature == "credit_score":
            lines.append(f"- Customer credit score: {int(value)} ({direction})")
        elif feature == "account_age_days":
            lines.append(f"- Account age: {int(value)} days ({direction})")
        elif feature == "merchant_risk":
            lines.append(f"- Merchant risk score: {value:.2f} ({direction})")
        else:
            lines.append(f"- {feature}: {value} ({direction})")

    if risk_tier == "High":
        lines.append("\nRECOMMENDED ACTION: Escalate for manual review. Contact customer to verify identity.")
    elif risk_tier == "Medium":
        lines.append("\nRECOMMENDED ACTION: Hold transaction pending additional verification.")
    else:
        lines.append("\nRECOMMENDED ACTION: Approve — low risk indicators.")

    return "\n".join(lines)


def store_fraud_alert(
    transaction_id: str,
    customer_id: str,
    fraud_probability: float,
    risk_tier: str,
    explanation: str,
    model_used: str = "ensemble",
) -> Dict:
    """
    Store a fraud alert with explanation in the fraud_alerts table.

    Args:
        transaction_id: ID of the flagged transaction
        customer_id: Customer identifier
        fraud_probability: Model's fraud probability
        risk_tier: Risk tier classification
        explanation: Human-readable explanation text
        model_used: Name of the model(s) used

    Returns:
        Dict with alert_id and status
    """
    engine = create_engine(DATABASE_URL)

    try:
        with engine.connect() as conn:
            # Ensure explanation column exists
            try:
                conn.execute(text("SELECT explanation FROM fraud_alerts LIMIT 1"))
            except Exception:
                try:
                    conn.execute(text("ALTER TABLE fraud_alerts ADD COLUMN explanation TEXT DEFAULT ''"))
                    conn.execute(text("ALTER TABLE fraud_alerts ADD COLUMN model_used TEXT DEFAULT ''"))
                    conn.commit()
                except Exception:
                    pass  # Columns may already exist

            # Insert alert
            conn.execute(text("""
                INSERT INTO fraud_alerts (customer_id, risk_score, reason, status, explanation, model_used, timestamp)
                VALUES (:cid, :score, :reason, :status, :explanation, :model, :ts)
            """), {
                "cid": customer_id,
                "score": fraud_probability,
                "reason": risk_tier,
                "status": "pending_review",
                "explanation": explanation[:2000],  # Truncate for DB
                "model": model_used,
                "ts": datetime.now().isoformat(),
            })
            conn.commit()

        return {"status": "stored", "customer_id": customer_id, "risk_tier": risk_tier}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def explain_transaction(
    transaction: dict,
    customer_id: str = "",
    use_llm: bool = False,
    customer_context: str = "",
) -> Dict:
    """
    Full explanation pipeline for a single transaction.

    1. Run fraud prediction
    2. Get SHAP feature attribution
    3. Generate explanation (rule-based or LLM)
    4. Optionally store in fraud_alerts table

    Args:
        transaction: Transaction feature dict
        customer_id: Optional customer ID for alert storage
        use_llm: If True, use GPT-4 for explanation (slower but richer)
        customer_context: Optional customer context for LLM prompt

    Returns:
        Dict with fraud_probability, risk_tier, shap_features, explanation
    """
    from src.models.fraud_detector import fraud_predict

    # Step 1: Predict
    prediction = fraud_predict(transaction)

    # Step 2: SHAP
    shap_result = get_shap_explanation(transaction)

    # Step 3: Determine risk tier
    prob = prediction["fraud_probability"]
    risk_tier = "High" if prob >= 0.7 else "Medium" if prob >= 0.3 else "Low"

    # Step 4: Generate explanation
    if use_llm:
        explanation = generate_llm_explanation(
            transaction, prob, risk_tier,
            shap_result["top_3_shap_features"],
            customer_context,
        )
    else:
        explanation = _generate_fallback_explanation(
            transaction, prob, risk_tier,
            shap_result["top_3_shap_features"],
        )

    # Step 5: Store alert if high risk
    alert = None
    if risk_tier in ("High", "Medium") and customer_id:
        alert = store_fraud_alert(
            transaction_id=transaction.get("transaction_id", "unknown"),
            customer_id=customer_id,
            fraud_probability=prob,
            risk_tier=risk_tier,
            explanation=explanation,
            model_used="xgboost_v2",
        )

    return {
        "fraud_probability": prob,
        "risk_tier": risk_tier,
        "is_fraud_predicted": prediction["is_fraud_predicted"],
        "shap_features": shap_result["top_3_shap_features"],
        "explanation": explanation,
        "alert_stored": alert,
    }


# --- CLI Demo ---
if __name__ == "__main__":
    print("=" * 60)
    print("Fraud Explanation Engine — Demo")
    print("=" * 60)

    sample_txn = {
        "amount": 5000.00,
        "hour": 2,
        "geo_mismatch": 1,
        "device_new": 1,
        "amount_zscore": 3.5,
        "velocity_30m": 4,
        "credit_score": 450,
        "account_age_days": 30,
        "is_weekend": 0,
        "merchant_risk": 0.8,
    }

    result = explain_transaction(sample_txn, customer_id="demo_001", use_llm=False)

    print(f"\nFraud Probability: {result['fraud_probability']:.2%}")
    print(f"Risk Tier: {result['risk_tier']}")
    print(f"\nTop SHAP Features:")
    for f in result["shap_features"]:
        print(f"  {f['feature']}: value={f['value']}, SHAP={f['shap_value']:.4f} ({f['direction']})")

    print(f"\nExplanation:\n{result['explanation']}")
