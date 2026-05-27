"""
Fraud Detection Model for the Banking AI System.

Trains an XGBoost classifier on the enriched transactions dataset with SMOTE
oversampling. Evaluates using PR-AUC. Logs experiments to MLflow.
Exports model as a pickle file and provides a prediction function.
"""
import os
import pickle
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_recall_curve,
    auc,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from imblearn.over_sampling import SMOTE
import mlflow
import mlflow.xgboost

warnings.filterwarnings("ignore", category=UserWarning)

# --- Configuration ---
FEATURE_COLS = [
    "amount",
    "hour",
    "geo_mismatch",
    "device_new",
    "amount_zscore",
    "velocity_30m",
    "credit_score",
    "account_age_days",
    "is_weekend",
    "merchant_risk",
]
TARGET_COL = "is_fraud"
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "fraud_detector_v1.pkl")
MLFLOW_EXPERIMENT = "fraud_detection"


def load_training_data(path: str = "data/processed/enriched_transactions.csv") -> pd.DataFrame:
    """Load the enriched transactions dataset."""
    df = pd.read_csv(path)
    print(f"Loaded {len(df)} transactions. Fraud rate: {df[TARGET_COL].mean():.2%}")
    return df


def prepare_features(df: pd.DataFrame):
    """Extract features and target, handle missing values."""
    X = df[FEATURE_COLS].copy()
    y = df[TARGET_COL].copy()

    # Fill any NaN values
    X = X.fillna(0)

    return X, y


def apply_smote(X_train, y_train, target_fraud_ratio=0.10):
    """
    Apply SMOTE oversampling to balance the training set.
    Target: ~10% fraud in training data.
    """
    fraud_count = y_train.sum()
    non_fraud_count = len(y_train) - fraud_count

    # Calculate how many fraud samples we need for target ratio
    # target_ratio = fraud_new / (fraud_new + non_fraud)
    # fraud_new = target_ratio * non_fraud / (1 - target_ratio)
    target_fraud = int(target_fraud_ratio * non_fraud_count / (1 - target_fraud_ratio))

    if target_fraud <= fraud_count:
        print(f"  Fraud rate already >= {target_fraud_ratio:.0%}. Skipping SMOTE.")
        return X_train, y_train

    smote = SMOTE(
        sampling_strategy={1: target_fraud},
        random_state=42,
        k_neighbors=min(5, fraud_count - 1) if fraud_count > 1 else 1
    )

    X_resampled, y_resampled = smote.fit_resample(X_train, y_train)
    new_fraud_rate = y_resampled.mean()
    print(f"  SMOTE: {len(y_train)} -> {len(y_resampled)} samples. Fraud rate: {new_fraud_rate:.2%}")

    return X_resampled, y_resampled


def train_model(X_train, y_train, X_test, y_test):
    """
    Train XGBoost classifier with scale_pos_weight tuning.
    Returns the trained model and evaluation metrics.
    """
    # Calculate scale_pos_weight for imbalanced data
    n_fraud = y_train.sum()
    n_non_fraud = len(y_train) - n_fraud
    scale_pos_weight = n_non_fraud / n_fraud if n_fraud > 0 else 1

    params = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.1,
        "scale_pos_weight": scale_pos_weight,
        "objective": "binary:logistic",
        "eval_metric": "aucpr",
        "random_state": 42,
        "use_label_encoder": False,
        "min_child_weight": 3,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "gamma": 0.1,
    }

    model = xgb.XGBClassifier(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    # PR-AUC
    precision, recall, _ = precision_recall_curve(y_test, y_prob)
    pr_auc = auc(recall, precision)

    # ROC-AUC
    roc_auc_val = roc_auc_score(y_test, y_prob)

    # F1
    f1 = f1_score(y_test, y_pred)

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)

    metrics = {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc_val,
        "f1_score": f1,
        "precision": cm[1, 1] / (cm[1, 1] + cm[0, 1]) if (cm[1, 1] + cm[0, 1]) > 0 else 0,
        "recall": cm[1, 1] / (cm[1, 1] + cm[1, 0]) if (cm[1, 1] + cm[1, 0]) > 0 else 0,
        "confusion_matrix": cm.tolist(),
    }

    return model, metrics, params


def get_feature_importance(model, feature_names):
    """Get feature importance from the trained model."""
    importance = model.feature_importances_
    feature_imp = sorted(
        zip(feature_names, importance),
        key=lambda x: x[1],
        reverse=True
    )
    return feature_imp


def save_model(model, path: str = MODEL_PATH):
    """Save model to pickle file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)
    print(f"  Model saved to {path}")


def load_model(path: str = MODEL_PATH):
    """Load model from pickle file."""
    with open(path, "rb") as f:
        return pickle.load(f)


# Module-level model cache to avoid reloading from disk on every prediction
_cached_model = None


def get_cached_model(path: str = MODEL_PATH):
    """Get the cached model, loading from disk only once."""
    global _cached_model
    if _cached_model is None:
        _cached_model = load_model(path)
    return _cached_model


def fraud_predict(transaction: dict, model=None) -> dict:
    """
    Predict fraud probability for a single transaction.

    Args:
        transaction: dict with keys matching FEATURE_COLS
        model: XGBoost model (loads from cache if None)

    Returns:
        dict with 'fraud_probability', 'is_fraud_predicted', 'top_3_risk_factors'
    """
    if model is None:
        model = get_cached_model()

    # Prepare features
    features = pd.DataFrame([transaction])[FEATURE_COLS].fillna(0)
    
    # Predict
    fraud_prob = model.predict_proba(features)[0, 1]
    is_fraud = fraud_prob >= 0.5

    # Get top risk factors using feature importances and actual values
    importances = model.feature_importances_
    feature_contributions = []
    for i, col in enumerate(FEATURE_COLS):
        val = features.iloc[0][col]
        contribution = importances[i] * abs(val) if val != 0 else 0
        feature_contributions.append({
            "feature": col,
            "value": float(val),
            "importance": float(importances[i]),
            "contribution": float(contribution),
        })

    # Sort by contribution to get top risk factors
    feature_contributions.sort(key=lambda x: x["contribution"], reverse=True)
    top_3 = feature_contributions[:3]

    return {
        "fraud_probability": round(float(fraud_prob), 4),
        "is_fraud_predicted": bool(is_fraud),
        "risk_level": "HIGH" if fraud_prob > 0.7 else "MEDIUM" if fraud_prob > 0.3 else "LOW",
        "top_3_risk_factors": top_3,
    }


def run_training_pipeline():
    """Full training pipeline with MLflow logging."""
    print("=" * 60)
    print("Banking AI - Fraud Detection Training Pipeline")
    print("=" * 60)

    # Step 1: Load data
    print("\n[1/6] Loading training data...")
    df = load_training_data()

    # Step 2: Prepare features
    print("\n[2/6] Preparing features...")
    X, y = prepare_features(df)
    print(f"  Features: {FEATURE_COLS}")
    print(f"  Samples: {len(X)}, Fraud: {y.sum()} ({y.mean():.2%})")

    # Step 3: Train/val/test split (70/15/15 stratified)
    print("\n[3/6] Splitting data (70/15/15 stratified)...")
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full, y_train_full, test_size=0.176, random_state=42, stratify=y_train_full
    )  # 0.176 of 85% ≈ 15% of total
    print(f"  Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

    # Step 4: SMOTE oversampling
    print("\n[4/6] Applying SMOTE oversampling...")
    X_train_smote, y_train_smote = apply_smote(X_train, y_train)

    # Step 5: Train model with MLflow logging
    print("\n[5/6] Training XGBoost classifier...")

    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    with mlflow.start_run(run_name=f"fraud_detector_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
        model, metrics, params = train_model(X_train_smote, y_train_smote, X_test, y_test)

        # Log params
        mlflow.log_params({
            "n_estimators": params["n_estimators"],
            "max_depth": params["max_depth"],
            "learning_rate": params["learning_rate"],
            "scale_pos_weight": round(params["scale_pos_weight"], 2),
            "smote_applied": True,
            "train_size": len(X_train_smote),
            "test_size": len(X_test),
        })

        # Log metrics
        mlflow.log_metrics({
            "pr_auc": metrics["pr_auc"],
            "roc_auc": metrics["roc_auc"],
            "f1_score": metrics["f1_score"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
        })

        # Log model
        mlflow.xgboost.log_model(model, "fraud_detector")

        print(f"\n  Results:")
        print(f"  PR-AUC:    {metrics['pr_auc']:.4f} {'PASS' if metrics['pr_auc'] > 0.85 else 'BELOW TARGET (0.85)'}")
        print(f"  ROC-AUC:   {metrics['roc_auc']:.4f}")
        print(f"  F1 Score:  {metrics['f1_score']:.4f}")
        print(f"  Precision: {metrics['precision']:.4f}")
        print(f"  Recall:    {metrics['recall']:.4f}")
        print(f"  Confusion Matrix: {metrics['confusion_matrix']}")

    # Step 6: Save model & feature importance
    print("\n[6/6] Saving model...")
    save_model(model)

    # Feature importance
    feat_imp = get_feature_importance(model, FEATURE_COLS)
    print("\n  Feature Importance:")
    for feat, imp in feat_imp:
        bar = "#" * int(imp * 50)
        print(f"    {feat:20s} {imp:.4f} {bar}")

    # Quick prediction demo
    print("\n" + "-" * 60)
    print("Quick Prediction Demo:")
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
    result = fraud_predict(sample_txn, model)
    print(f"  Transaction: ${sample_txn['amount']} at {sample_txn['hour']}:00, new device, geo mismatch")
    print(f"  Fraud Probability: {result['fraud_probability']:.2%}")
    print(f"  Risk Level: {result['risk_level']}")
    print(f"  Top Risk Factors:")
    for factor in result["top_3_risk_factors"]:
        print(f"    - {factor['feature']}: value={factor['value']}, importance={factor['importance']:.4f}")

    print("\n" + "=" * 60)
    print("Training pipeline complete!")
    print("=" * 60)

    return model, metrics


if __name__ == "__main__":
    run_training_pipeline()
