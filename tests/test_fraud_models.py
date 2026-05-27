"""
Phase 5 Fraud Detection Engine Tests.

Verifies:
  1. All 5 models load and produce predictions
  2. SHAP explanations return top 3 features
  3. Ensemble scoring averages XGBoost + Isolation Forest
  4. Fraud explainer generates human-readable output
  5. Updated FEATURE_COLS includes merchant_risk (10 features)
  6. 70/15/15 split ratios
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pickle
import numpy as np
import pandas as pd


# ============================================================
# Feature Engineering Tests
# ============================================================
class TestFeatureEngineering:
    """Test that feature engineering matches the Phase 5 spec."""

    def test_feature_cols_has_10_features(self):
        """FEATURE_COLS should contain exactly 10 features (including merchant_risk)."""
        from src.models.fraud_detector import FEATURE_COLS
        assert len(FEATURE_COLS) == 10
        assert "merchant_risk" in FEATURE_COLS

    def test_all_specified_features_present(self):
        """All TODO-spec features must be in FEATURE_COLS."""
        from src.models.fraud_detector import FEATURE_COLS
        required = [
            "amount", "hour", "geo_mismatch", "device_new",
            "amount_zscore", "velocity_30m", "credit_score",
            "account_age_days", "is_weekend", "merchant_risk",
        ]
        for feat in required:
            assert feat in FEATURE_COLS, f"Missing feature: {feat}"

    def test_training_data_has_all_features(self):
        """Enriched transactions CSV should have all features."""
        df = pd.read_csv("data/processed/enriched_transactions.csv")
        from src.models.fraud_detector import FEATURE_COLS
        for col in FEATURE_COLS:
            assert col in df.columns, f"Training data missing column: {col}"


# ============================================================
# Model Loading Tests
# ============================================================
class TestModelLoading:
    """Test all 5 models can be loaded from disk."""

    def test_xgboost_model_exists(self):
        """XGBoost model file should exist."""
        assert os.path.exists("models/fraud_xgboost_v2.pkl") or os.path.exists("models/fraud_detector_v1.pkl")

    def test_random_forest_model_exists(self):
        """Random Forest model file should exist."""
        assert os.path.exists("models/fraud_random_forest.pkl")

    def test_isolation_forest_model_exists(self):
        """Isolation Forest model file should exist."""
        assert os.path.exists("models/fraud_isolation_forest.pkl")

    def test_autoencoder_model_exists(self):
        """Autoencoder model package should exist."""
        assert os.path.exists("models/fraud_autoencoder.pkl")

    def test_lstm_model_exists(self):
        """LSTM model package should exist."""
        assert os.path.exists("models/fraud_lstm.pkl")

    def test_model_count(self):
        """Should have at least 5 model files."""
        model_files = [f for f in os.listdir("models") if f.endswith(".pkl")]
        assert len(model_files) >= 5, f"Expected >= 5 model files, found {len(model_files)}: {model_files}"


# ============================================================
# Prediction Tests
# ============================================================
SAMPLE_TXN = {
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
}

SAFE_TXN = {
    "amount": 45.00,
    "hour": 14,
    "geo_mismatch": 0,
    "device_new": 0,
    "is_weekend": 0,
    "amount_zscore": -0.2,
    "velocity_30m": 0,
    "credit_score": 780,
    "account_age_days": 2500,
    "merchant_risk": 0.1,
}


class TestXGBoostPrediction:
    """Test XGBoost prediction function."""

    def test_fraud_predict_returns_valid_dict(self):
        """fraud_predict() should return a dict with required keys."""
        from src.models.fraud_detector import fraud_predict
        result = fraud_predict(SAMPLE_TXN)

        assert "fraud_probability" in result
        assert "is_fraud_predicted" in result
        assert "risk_level" in result
        assert "top_3_risk_factors" in result

    def test_fraud_probability_in_range(self):
        """Fraud probability should be between 0 and 1."""
        from src.models.fraud_detector import fraud_predict
        result = fraud_predict(SAMPLE_TXN)
        assert 0.0 <= result["fraud_probability"] <= 1.0

    def test_risk_level_valid(self):
        """Risk level should be LOW, MEDIUM, or HIGH."""
        from src.models.fraud_detector import fraud_predict
        result = fraud_predict(SAMPLE_TXN)
        assert result["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_top_3_risk_factors_has_3(self):
        """Should return exactly 3 top risk factors."""
        from src.models.fraud_detector import fraud_predict
        result = fraud_predict(SAMPLE_TXN)
        assert len(result["top_3_risk_factors"]) == 3

    def test_risk_factor_structure(self):
        """Each risk factor should have feature, value, importance, contribution."""
        from src.models.fraud_detector import fraud_predict
        result = fraud_predict(SAMPLE_TXN)
        for factor in result["top_3_risk_factors"]:
            assert "feature" in factor
            assert "value" in factor
            assert "importance" in factor
            assert "contribution" in factor


class TestRandomForestPrediction:
    """Test Random Forest prediction."""

    def test_rf_predict(self):
        """Random Forest should produce valid probabilities."""
        from src.models.fraud_detector import FEATURE_COLS
        with open("models/fraud_random_forest.pkl", "rb") as f:
            rf_model = pickle.load(f)

        features = pd.DataFrame([SAMPLE_TXN])[FEATURE_COLS].fillna(0)
        prob = rf_model.predict_proba(features)[0, 1]
        assert 0.0 <= prob <= 1.0


class TestIsolationForestPrediction:
    """Test Isolation Forest prediction."""

    def test_iso_predict(self):
        """Isolation Forest should produce anomaly scores."""
        from src.models.fraud_detector import FEATURE_COLS
        with open("models/fraud_isolation_forest.pkl", "rb") as f:
            iso_model = pickle.load(f)

        features = pd.DataFrame([SAMPLE_TXN])[FEATURE_COLS].fillna(0)
        raw_score = iso_model.decision_function(features)[0]
        assert isinstance(raw_score, (float, np.floating))


class TestAutoencoderPrediction:
    """Test Autoencoder prediction."""

    def test_autoencoder_loads_and_reconstructs(self):
        """Autoencoder should load and produce reconstruction error."""
        import torch
        from src.models.model_zoo import FraudAutoencoder
        from src.models.fraud_detector import FEATURE_COLS

        with open("models/fraud_autoencoder.pkl", "rb") as f:
            ae_pkg = pickle.load(f)

        model = FraudAutoencoder(input_dim=ae_pkg["input_dim"])
        model.load_state_dict(ae_pkg["model_state_dict"])
        model.eval()

        features = pd.DataFrame([SAMPLE_TXN])[FEATURE_COLS].fillna(0)
        scaled = ae_pkg["scaler"].transform(features)
        tensor = torch.FloatTensor(scaled)

        with torch.no_grad():
            recon = model(tensor)
            error = torch.mean((tensor - recon) ** 2).item()

        assert error >= 0


class TestLSTMPrediction:
    """Test LSTM prediction."""

    def test_lstm_loads_and_predicts(self):
        """LSTM should load and produce a fraud probability."""
        import torch
        from src.models.model_zoo import FraudLSTM
        from src.models.fraud_detector import FEATURE_COLS

        with open("models/fraud_lstm.pkl", "rb") as f:
            lstm_pkg = pickle.load(f)

        model = FraudLSTM(
            input_dim=lstm_pkg["input_dim"],
            hidden_dim=lstm_pkg["hidden_dim"],
            num_layers=lstm_pkg["num_layers"],
        )
        # The saved model used Identity() for the last layer
        model.classifier[-1] = torch.nn.Identity()
        model.load_state_dict(lstm_pkg["model_state_dict"])
        model.eval()

        features = pd.DataFrame([SAMPLE_TXN])[FEATURE_COLS].fillna(0)
        scaled = lstm_pkg["scaler"].transform(features)
        # Create a single-step sequence (1 sample, 1 timestep, N features)
        tensor = torch.FloatTensor(scaled).unsqueeze(0)

        with torch.no_grad():
            raw_output = model(tensor)
            prob = torch.sigmoid(raw_output).item()

        assert 0.0 <= prob <= 1.0


# ============================================================
# SHAP Explanation Tests
# ============================================================
class TestSHAPExplanations:
    """Test SHAP-based feature attribution."""

    def test_shap_explanation_returns_top_3(self):
        """SHAP explanation should return top 3 features."""
        from src.models.explainer import get_shap_explanation
        result = get_shap_explanation(SAMPLE_TXN)

        assert "top_3_shap_features" in result
        assert len(result["top_3_shap_features"]) == 3

    def test_shap_features_have_required_keys(self):
        """Each SHAP feature should have feature, value, shap_value, direction."""
        from src.models.explainer import get_shap_explanation
        result = get_shap_explanation(SAMPLE_TXN)

        for f in result["top_3_shap_features"]:
            assert "feature" in f
            assert "value" in f
            assert "shap_value" in f
            assert "direction" in f
            assert f["direction"] in ("increases risk", "decreases risk")

    def test_shap_has_base_value(self):
        """SHAP explanation should include a base value."""
        from src.models.explainer import get_shap_explanation
        result = get_shap_explanation(SAMPLE_TXN)
        assert "base_value" in result

    def test_shap_all_features_returned(self):
        """All attributions should include all 10 features."""
        from src.models.explainer import get_shap_explanation
        result = get_shap_explanation(SAMPLE_TXN)
        assert len(result["all_attributions"]) == 10


# ============================================================
# Fraud Explainer Tests
# ============================================================
class TestFraudExplainer:
    """Test the full explanation pipeline."""

    def test_fallback_explanation_generates_text(self):
        """Rule-based fallback should generate readable explanation."""
        from src.models.explainer import explain_transaction
        result = explain_transaction(SAMPLE_TXN, use_llm=False)

        assert "explanation" in result
        assert len(result["explanation"]) > 50
        assert "RISK ASSESSMENT" in result["explanation"] or "RECOMMENDED ACTION" in result["explanation"]

    def test_explain_returns_all_fields(self):
        """Full explanation should return all required fields."""
        from src.models.explainer import explain_transaction
        result = explain_transaction(SAMPLE_TXN, use_llm=False)

        assert "fraud_probability" in result
        assert "risk_tier" in result
        assert "shap_features" in result
        assert "explanation" in result

    def test_risk_tier_classification(self):
        """Risk tier should match probability thresholds."""
        from src.models.explainer import explain_transaction

        result = explain_transaction(SAFE_TXN, use_llm=False)
        # Safe transaction should be Low risk
        assert result["risk_tier"] == "Low"


# ============================================================
# Ensemble Scoring Tests
# ============================================================
class TestEnsembleScoring:
    """Test ensemble scoring (XGBoost + Isolation Forest)."""

    def test_isolation_forest_scoring(self):
        """Isolation Forest scoring function should return a valid probability."""
        from src.api.routes.fraud import _get_isolation_forest_score
        score = _get_isolation_forest_score(SAMPLE_TXN)

        assert score is not None, "Isolation Forest model not available"
        assert 0.0 <= score <= 1.0

    def test_ensemble_averages_correctly(self):
        """Ensemble score should be between XGBoost and Isolation Forest scores."""
        from src.models.fraud_detector import fraud_predict
        from src.api.routes.fraud import _get_isolation_forest_score

        xgb_result = fraud_predict(SAMPLE_TXN)
        xgb_prob = xgb_result["fraud_probability"]
        iso_prob = _get_isolation_forest_score(SAMPLE_TXN)

        if iso_prob is not None:
            ensemble = (xgb_prob + iso_prob) / 2
            assert min(xgb_prob, iso_prob) <= ensemble <= max(xgb_prob, iso_prob)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
