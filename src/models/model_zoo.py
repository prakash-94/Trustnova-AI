"""
Multi-Model Fraud Detection Zoo.

Trains and compares 5 fraud detection models:
  1. XGBoost          — Supervised, SMOTE-balanced, gradient boosting
  2. Random Forest    — Supervised baseline comparison
  3. Isolation Forest — Unsupervised outlier detection
  4. Autoencoder      — Semi-supervised (PyTorch), reconstruction error
  5. LSTM             — Sequence model (PyTorch), 10-txn customer windows

All models are logged to MLflow for comparison.
Best model is exported to models/ directory.
"""
import os
import pickle
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_recall_curve,
    auc,
    f1_score,
    roc_auc_score,
    precision_score,
    recall_score,
    classification_report,
)
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE
import mlflow

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings("ignore", category=UserWarning)

# --- Configuration ---
FEATURE_COLS = [
    "amount", "hour", "geo_mismatch", "device_new", "amount_zscore",
    "velocity_30m", "credit_score", "account_age_days", "is_weekend", "merchant_risk",
]
TARGET_COL = "is_fraud"
MODEL_DIR = "models"
MLFLOW_EXPERIMENT = "fraud_detection"
DATA_PATH = "data/processed/enriched_transactions.csv"


# ============================================================
# Data Loading + Splitting
# ============================================================
def load_and_split(path: str = DATA_PATH):
    """Load data and perform 70/15/15 stratified split."""
    df = pd.read_csv(path)
    X = df[FEATURE_COLS].fillna(0)
    y = df[TARGET_COL]

    # 70/15/15 split
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full, y_train_full, test_size=0.176, random_state=42, stratify=y_train_full
    )

    print(f"Data: {len(df)} rows | Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")
    print(f"Fraud rate: Train={y_train.mean():.3%}, Val={y_val.mean():.3%}, Test={y_test.mean():.3%}")

    return X_train, X_val, X_test, y_train, y_val, y_test, df


def evaluate_model(y_true, y_prob, y_pred=None, threshold=0.5):
    """Compute standard fraud detection metrics."""
    if y_pred is None:
        y_pred = (y_prob >= threshold).astype(int)

    precision, recall, _ = precision_recall_curve(y_true, y_prob)
    pr_auc = auc(recall, precision)

    return {
        "pr_auc": round(pr_auc, 4),
        "roc_auc": round(roc_auc_score(y_true, y_prob), 4),
        "f1_score": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
    }


def save_model(model, name: str):
    """Save model to pickle."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, f"{name}.pkl")
    with open(path, "wb") as f:
        pickle.dump(model, f)
    print(f"  Saved: {path}")
    return path


# ============================================================
# Model 1: XGBoost
# ============================================================
def train_xgboost(X_train, y_train, X_val, y_val, X_test, y_test):
    """Train XGBoost with SMOTE and scale_pos_weight."""
    print("\n" + "=" * 50)
    print("Model 1: XGBoost (Gradient Boosting)")
    print("=" * 50)

    # SMOTE
    fraud_count = y_train.sum()
    non_fraud_count = len(y_train) - fraud_count
    target_fraud = int(0.10 * non_fraud_count / 0.90)

    if target_fraud > fraud_count:
        smote = SMOTE(
            sampling_strategy={1: target_fraud},
            random_state=42,
            k_neighbors=min(5, fraud_count - 1) if fraud_count > 1 else 1,
        )
        X_train_s, y_train_s = smote.fit_resample(X_train, y_train)
        print(f"  SMOTE: {len(y_train)} -> {len(y_train_s)} samples")
    else:
        X_train_s, y_train_s = X_train, y_train

    n_fraud = y_train_s.sum()
    n_non = len(y_train_s) - n_fraud
    spw = n_non / n_fraud if n_fraud > 0 else 1

    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.1,
        scale_pos_weight=spw, objective="binary:logistic",
        eval_metric="aucpr", random_state=42,
        min_child_weight=3, subsample=0.8, colsample_bytree=0.8, gamma=0.1,
    )
    model.fit(X_train_s, y_train_s, eval_set=[(X_val, y_val)], verbose=False)

    y_prob = model.predict_proba(X_test)[:, 1]
    metrics = evaluate_model(y_test, y_prob)
    save_model(model, "fraud_xgboost_v2")

    print(f"  PR-AUC: {metrics['pr_auc']}  |  F1: {metrics['f1_score']}  |  ROC-AUC: {metrics['roc_auc']}")
    return model, metrics


# ============================================================
# Model 2: Random Forest
# ============================================================
def train_random_forest(X_train, y_train, X_val, y_val, X_test, y_test):
    """Train Random Forest as baseline comparison."""
    print("\n" + "=" * 50)
    print("Model 2: Random Forest (Baseline)")
    print("=" * 50)

    model = RandomForestClassifier(
        n_estimators=200, max_depth=10, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_prob = model.predict_proba(X_test)[:, 1]
    metrics = evaluate_model(y_test, y_prob)
    save_model(model, "fraud_random_forest")

    print(f"  PR-AUC: {metrics['pr_auc']}  |  F1: {metrics['f1_score']}  |  ROC-AUC: {metrics['roc_auc']}")
    return model, metrics


# ============================================================
# Model 3: Isolation Forest
# ============================================================
def train_isolation_forest(X_train, y_train, X_val, y_val, X_test, y_test):
    """Train Isolation Forest for unsupervised outlier detection."""
    print("\n" + "=" * 50)
    print("Model 3: Isolation Forest (Unsupervised)")
    print("=" * 50)

    contamination = y_train.mean()  # Use actual fraud rate
    print(f"  Contamination: {contamination:.4f}")

    model = IsolationForest(
        n_estimators=200, contamination=contamination,
        random_state=42, n_jobs=-1,
    )
    model.fit(X_train)

    # Isolation Forest: decision_function returns anomaly score (lower = more anomalous)
    raw_scores = model.decision_function(X_test)
    # Convert to probability-like score (0-1, higher = more fraudulent)
    y_prob = 1 - (raw_scores - raw_scores.min()) / (raw_scores.max() - raw_scores.min() + 1e-8)

    metrics = evaluate_model(y_test, y_prob, threshold=0.5)
    save_model(model, "fraud_isolation_forest")

    print(f"  PR-AUC: {metrics['pr_auc']}  |  F1: {metrics['f1_score']}  |  ROC-AUC: {metrics['roc_auc']}")
    return model, metrics


# ============================================================
# Model 4: Autoencoder (PyTorch)
# ============================================================
class FraudAutoencoder(nn.Module):
    """Autoencoder trained on legitimate transactions only."""

    def __init__(self, input_dim=10):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 8),
            nn.ReLU(),
            nn.Linear(8, 4),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(4, 8),
            nn.ReLU(),
            nn.Linear(8, input_dim),
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded


def train_autoencoder(X_train, y_train, X_val, y_val, X_test, y_test):
    """Train autoencoder on legitimate transactions; flag high reconstruction error as fraud."""
    print("\n" + "=" * 50)
    print("Model 4: Autoencoder (PyTorch, Semi-supervised)")
    print("=" * 50)

    scaler = StandardScaler()

    # Train ONLY on legitimate transactions
    X_legit = X_train[y_train == 0]
    X_legit_scaled = scaler.fit_transform(X_legit)
    X_test_scaled = scaler.transform(X_test)
    X_val_scaled = scaler.transform(X_val)

    # PyTorch datasets
    train_tensor = torch.FloatTensor(X_legit_scaled)
    train_dataset = TensorDataset(train_tensor, train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)

    input_dim = X_train.shape[1]
    model = FraudAutoencoder(input_dim=input_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()

    # Train
    model.train()
    for epoch in range(50):
        total_loss = 0
        for batch_x, batch_target in train_loader:
            optimizer.zero_grad()
            output = model(batch_x)
            loss = criterion(output, batch_target)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        if (epoch + 1) % 10 == 0:
            avg_loss = total_loss / len(train_loader)
            print(f"  Epoch {epoch+1}/50 — Loss: {avg_loss:.6f}")

    # Determine threshold from validation set
    model.eval()
    with torch.no_grad():
        val_tensor = torch.FloatTensor(X_val_scaled)
        val_recon = model(val_tensor)
        val_errors = torch.mean((val_tensor - val_recon) ** 2, dim=1).numpy()

    # Set threshold at 95th percentile of legitimate reconstruction errors
    legit_val_errors = val_errors[y_val.values == 0]
    threshold = np.percentile(legit_val_errors, 95)
    print(f"  Reconstruction error threshold: {threshold:.6f}")

    # Evaluate on test set
    with torch.no_grad():
        test_tensor = torch.FloatTensor(X_test_scaled)
        test_recon = model(test_tensor)
        test_errors = torch.mean((test_tensor - test_recon) ** 2, dim=1).numpy()

    # Normalize errors to 0-1 probability
    max_error = max(test_errors.max(), threshold * 3)
    y_prob = np.clip(test_errors / max_error, 0, 1)

    metrics = evaluate_model(y_test, y_prob, threshold=threshold / max_error)

    # Save model + scaler + threshold together
    ae_package = {
        "model_state_dict": model.state_dict(),
        "scaler": scaler,
        "threshold": threshold,
        "input_dim": input_dim,
        "max_error": max_error,
    }
    save_model(ae_package, "fraud_autoencoder")

    print(f"  PR-AUC: {metrics['pr_auc']}  |  F1: {metrics['f1_score']}  |  ROC-AUC: {metrics['roc_auc']}")
    return ae_package, metrics


# ============================================================
# Model 5: LSTM (PyTorch)
# ============================================================
class FraudLSTM(nn.Module):
    """LSTM for sequence-based fraud detection on customer transaction windows."""

    def __init__(self, input_dim=10, hidden_dim=64, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        last_hidden = lstm_out[:, -1, :]  # Take last time step
        return self.classifier(last_hidden)


def create_sequences(df, feature_cols, target_col, window_size=10):
    """Create 10-transaction windows per customer for LSTM training."""
    sequences = []
    labels = []

    for cid, group in df.groupby("customer_id"):
        group = group.sort_values("timestamp") if "timestamp" in group.columns else group
        features = group[feature_cols].fillna(0).values
        targets = group[target_col].values

        for i in range(len(features) - window_size + 1):
            seq = features[i:i + window_size]
            label = targets[i + window_size - 1]  # Label of the last transaction
            sequences.append(seq)
            labels.append(label)

    return np.array(sequences), np.array(labels)


def train_lstm(X_train, y_train, X_val, y_val, X_test, y_test, df=None):
    """Train LSTM on 10-transaction customer windows."""
    print("\n" + "=" * 50)
    print("Model 5: LSTM (PyTorch, Sequence Model)")
    print("=" * 50)

    if df is None:
        print("  WARNING: Full dataframe required for sequence creation. Using fallback.")
        # Fallback: treat each row as a length-1 sequence (not ideal but functional)
        X_train_seq = X_train.values.reshape(-1, 1, X_train.shape[1])
        X_test_seq = X_test.values.reshape(-1, 1, X_test.shape[1])
        y_train_seq = y_train.values
        y_test_seq = y_test.values
    else:
        # Create proper sequences from full dataframe
        window_size = 10
        print(f"  Creating {window_size}-transaction windows per customer...")
        X_seq, y_seq = create_sequences(df, FEATURE_COLS, TARGET_COL, window_size)
        print(f"  Sequences: {len(X_seq)} | Fraud: {y_seq.sum()} ({y_seq.mean():.3%})")

        if len(X_seq) < 100:
            print("  Too few sequences. Using single-step fallback.")
            X_train_seq = X_train.values.reshape(-1, 1, X_train.shape[1])
            X_test_seq = X_test.values.reshape(-1, 1, X_test.shape[1])
            y_train_seq = y_train.values
            y_test_seq = y_test.values
        else:
            # Split sequences
            split_idx = int(len(X_seq) * 0.85)
            X_train_seq, X_test_seq = X_seq[:split_idx], X_seq[split_idx:]
            y_train_seq, y_test_seq = y_seq[:split_idx], y_seq[split_idx:]

    # Scale
    scaler = StandardScaler()
    orig_shape = X_train_seq.shape
    X_train_flat = X_train_seq.reshape(-1, X_train_seq.shape[-1])
    X_test_flat = X_test_seq.reshape(-1, X_test_seq.shape[-1])
    X_train_flat = scaler.fit_transform(X_train_flat)
    X_test_flat = scaler.transform(X_test_flat)
    X_train_seq = X_train_flat.reshape(orig_shape)
    X_test_seq = X_test_flat.reshape(-1, X_test_seq.shape[1] if len(X_test_seq.shape) > 2 else 1, X_test_seq.shape[-1])

    # PyTorch
    train_tensor = torch.FloatTensor(X_train_seq)
    train_labels = torch.FloatTensor(y_train_seq).unsqueeze(1)
    test_tensor = torch.FloatTensor(X_test_seq)

    train_dataset = TensorDataset(train_tensor, train_labels)
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)

    input_dim = X_train_seq.shape[-1]
    model = FraudLSTM(input_dim=input_dim, hidden_dim=64, num_layers=2)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.BCELoss()

    # Handle class imbalance with weighted loss
    pos_weight = (len(y_train_seq) - y_train_seq.sum()) / max(y_train_seq.sum(), 1)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight]))

    # Modify model to not use sigmoid (BCEWithLogitsLoss includes it)
    model.classifier[-1] = nn.Identity()

    # Train
    model.train()
    for epoch in range(30):
        total_loss = 0
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            output = model(batch_x)
            loss = criterion(output, batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        if (epoch + 1) % 10 == 0:
            avg_loss = total_loss / len(train_loader)
            print(f"  Epoch {epoch+1}/30 — Loss: {avg_loss:.4f}")

    # Evaluate
    model.eval()
    with torch.no_grad():
        raw_output = model(test_tensor)
        y_prob = torch.sigmoid(raw_output).squeeze().numpy()

    y_prob = np.clip(y_prob, 0, 1)

    if len(y_prob.shape) == 0:
        y_prob = np.array([float(y_prob)])

    metrics = evaluate_model(y_test_seq, y_prob)

    # Save
    lstm_package = {
        "model_state_dict": model.state_dict(),
        "scaler": scaler,
        "input_dim": input_dim,
        "hidden_dim": 64,
        "num_layers": 2,
    }
    save_model(lstm_package, "fraud_lstm")

    print(f"  PR-AUC: {metrics['pr_auc']}  |  F1: {metrics['f1_score']}  |  ROC-AUC: {metrics['roc_auc']}")
    return lstm_package, metrics


# ============================================================
# Full Training Pipeline
# ============================================================
def run_model_zoo():
    """Train all 5 models and compare in MLflow."""
    print("=" * 60)
    print("Banking AI — Multi-Model Fraud Detection Zoo")
    print("=" * 60)

    # Load and split
    X_train, X_val, X_test, y_train, y_val, y_test, df = load_and_split()

    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    results = {}

    # --- Model 1: XGBoost ---
    with mlflow.start_run(run_name="xgboost_v2"):
        model, metrics = train_xgboost(X_train, y_train, X_val, y_val, X_test, y_test)
        mlflow.log_params({"model_type": "XGBoost", "n_estimators": 200, "max_depth": 6, "smote": True})
        mlflow.log_metrics(metrics)
        results["XGBoost"] = metrics

    # --- Model 2: Random Forest ---
    with mlflow.start_run(run_name="random_forest"):
        model, metrics = train_random_forest(X_train, y_train, X_val, y_val, X_test, y_test)
        mlflow.log_params({"model_type": "RandomForest", "n_estimators": 200, "max_depth": 10})
        mlflow.log_metrics(metrics)
        results["Random Forest"] = metrics

    # --- Model 3: Isolation Forest ---
    with mlflow.start_run(run_name="isolation_forest"):
        model, metrics = train_isolation_forest(X_train, y_train, X_val, y_val, X_test, y_test)
        mlflow.log_params({"model_type": "IsolationForest", "n_estimators": 200})
        mlflow.log_metrics(metrics)
        results["Isolation Forest"] = metrics

    # --- Model 4: Autoencoder ---
    with mlflow.start_run(run_name="autoencoder"):
        model, metrics = train_autoencoder(X_train, y_train, X_val, y_val, X_test, y_test)
        mlflow.log_params({"model_type": "Autoencoder", "architecture": "10-8-4-8-10", "epochs": 50})
        mlflow.log_metrics(metrics)
        results["Autoencoder"] = metrics

    # --- Model 5: LSTM ---
    with mlflow.start_run(run_name="lstm"):
        model, metrics = train_lstm(X_train, y_train, X_val, y_val, X_test, y_test, df=df)
        mlflow.log_params({"model_type": "LSTM", "hidden_dim": 64, "num_layers": 2, "epochs": 30})
        mlflow.log_metrics(metrics)
        results["LSTM"] = metrics

    # --- Comparison ---
    print("\n" + "=" * 60)
    print("MODEL COMPARISON")
    print("=" * 60)
    print(f"{'Model':<20} {'PR-AUC':>8} {'ROC-AUC':>8} {'F1':>8} {'Precision':>10} {'Recall':>8}")
    print("-" * 60)

    best_model = None
    best_prauc = 0

    for name, m in results.items():
        marker = ""
        if m["pr_auc"] > best_prauc:
            best_prauc = m["pr_auc"]
            best_model = name
        print(f"{name:<20} {m['pr_auc']:>8.4f} {m['roc_auc']:>8.4f} {m['f1_score']:>8.4f} {m['precision']:>10.4f} {m['recall']:>8.4f}")

    print("-" * 60)
    print(f"Best model by PR-AUC: {best_model} ({best_prauc:.4f})")

    # XGBoost target check
    xgb_prauc = results["XGBoost"]["pr_auc"]
    print(f"\nXGBoost PR-AUC: {xgb_prauc:.4f} {'✓ PASS (> 0.85)' if xgb_prauc > 0.85 else '✗ BELOW TARGET (0.85)'}")

    print("=" * 60)
    return results


if __name__ == "__main__":
    run_model_zoo()
