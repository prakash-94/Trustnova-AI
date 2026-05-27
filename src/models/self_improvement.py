"""
Self-Improvement Loop for the Banking AI Fraud Detection System.

Provides:
- Feedback table in SQLite for banker overrides
- record_feedback() to store banker corrections
- retrain_model() to retrain XGBoost with feedback data
- Drift detection: alerts if PR-AUC drops >5% from baseline
"""
import os
import pickle
from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_recall_curve, auc
from imblearn.over_sampling import SMOTE
import xgboost as xgb
import mlflow
import mlflow.xgboost

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")
MODEL_DIR = "models"
MLFLOW_EXPERIMENT = "fraud_detection"

FEATURE_COLS = [
    "amount", "hour", "geo_mismatch", "device_new",
    "amount_zscore", "velocity_30m", "credit_score",
    "account_age_days", "is_weekend",
]
TARGET_COL = "is_fraud"


class SelfImprovementLoop:
    """Manages the feedback-driven retraining loop."""

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_feedback_table()
        self.baseline_pr_auc = None

    def _ensure_feedback_table(self):
        """Create the feedback table if it doesn't exist."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    txn_id TEXT NOT NULL,
                    predicted_fraud REAL NOT NULL,
                    banker_override INTEGER NOT NULL,
                    banker_notes TEXT,
                    timestamp TEXT NOT NULL
                )
            """))
            conn.commit()

    def record_feedback(
        self,
        txn_id: str,
        predicted_fraud: float,
        banker_says_fraud: bool,
        notes: str = ""
    ) -> Dict:
        """
        Record banker feedback on a fraud prediction.

        Args:
            txn_id: Transaction ID
            predicted_fraud: Model's predicted fraud probability
            banker_says_fraud: Banker's override (True = fraud, False = not fraud)
            notes: Optional banker notes

        Returns:
            Dict with status and feedback details
        """
        timestamp = datetime.now().isoformat()
        override_int = 1 if banker_says_fraud else 0

        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO feedback (txn_id, predicted_fraud, banker_override, banker_notes, timestamp)
                VALUES (:txn_id, :pred, :override, :notes, :ts)
            """), {
                "txn_id": txn_id,
                "pred": predicted_fraud,
                "override": override_int,
                "notes": notes,
                "ts": timestamp,
            })
            conn.commit()

        agreement = "AGREE" if (predicted_fraud >= 0.5) == banker_says_fraud else "DISAGREE"

        return {
            "status": "recorded",
            "txn_id": txn_id,
            "predicted_fraud": predicted_fraud,
            "banker_says_fraud": banker_says_fraud,
            "agreement": agreement,
            "timestamp": timestamp,
        }

    def get_feedback_stats(self) -> Dict:
        """Get summary statistics of all recorded feedback."""
        df = pd.read_sql("SELECT * FROM feedback", self.engine)
        if df.empty:
            return {"total_feedback": 0, "message": "No feedback recorded yet"}

        # Calculate agreement rate
        df["model_pred_fraud"] = (df["predicted_fraud"] >= 0.5).astype(int)
        df["agreed"] = df["model_pred_fraud"] == df["banker_override"]

        return {
            "total_feedback": len(df),
            "agreement_rate": round(df["agreed"].mean(), 4),
            "banker_fraud_count": int(df["banker_override"].sum()),
            "banker_not_fraud_count": int((1 - df["banker_override"]).sum()),
            "model_false_positives": int(
                ((df["model_pred_fraud"] == 1) & (df["banker_override"] == 0)).sum()
            ),
            "model_false_negatives": int(
                ((df["model_pred_fraud"] == 0) & (df["banker_override"] == 1)).sum()
            ),
        }

    def retrain_model(self) -> Dict:
        """
        Retrain the XGBoost fraud model using original data + feedback corrections.

        The feedback data acts as ground truth corrections:
        - If a banker overrides a prediction, the banker's label is used
        - Original labels are kept for transactions without feedback

        Returns:
            Dict with new model metrics and comparison to baseline
        """
        print("=" * 60)
        print("Self-Improvement: Retraining Fraud Model")
        print("=" * 60)

        # Load original data
        print("\n[1/5] Loading training data with feedback corrections...")
        df = pd.read_csv("data/processed/enriched_transactions.csv")
        feedback = pd.read_sql("SELECT * FROM feedback", self.engine)

        if feedback.empty:
            print("  No feedback data available. Using original labels only.")
        else:
            print(f"  Applying {len(feedback)} feedback corrections...")
            # Create a map of txn_id -> banker's label
            feedback_map = dict(zip(feedback["txn_id"], feedback["banker_override"]))

            # Override labels where feedback exists
            corrections_applied = 0
            for txn_id, banker_label in feedback_map.items():
                mask = df["transaction_id"] == txn_id
                if mask.any():
                    original = df.loc[mask, TARGET_COL].iloc[0]
                    if original != banker_label:
                        df.loc[mask, TARGET_COL] = banker_label
                        corrections_applied += 1

            print(f"  Applied {corrections_applied} label corrections from banker feedback")

        # Prepare features
        print("\n[2/5] Preparing features...")
        X = df[FEATURE_COLS].fillna(0)
        y = df[TARGET_COL]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # SMOTE
        print("\n[3/5] Applying SMOTE...")
        n_fraud = y_train.sum()
        n_non_fraud = len(y_train) - n_fraud
        target_fraud = int(0.10 * n_non_fraud / 0.90)

        if target_fraud > n_fraud:
            smote = SMOTE(
                sampling_strategy={1: target_fraud},
                random_state=42,
                k_neighbors=min(5, int(n_fraud) - 1) if n_fraud > 1 else 1
            )
            X_train, y_train = smote.fit_resample(X_train, y_train)
            print(f"  SMOTE applied. New fraud rate: {y_train.mean():.2%}")

        # Train
        print("\n[4/5] Training new model...")
        scale_pos_weight = (len(y_train) - y_train.sum()) / y_train.sum()
        model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=scale_pos_weight,
            objective="binary:logistic",
            eval_metric="aucpr",
            random_state=42,
            use_label_encoder=False,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.1,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        # Evaluate
        y_prob = model.predict_proba(X_test)[:, 1]
        precision, recall, _ = precision_recall_curve(y_test, y_prob)
        new_pr_auc = auc(recall, precision)

        # Log to MLflow
        print("\n[5/5] Logging to MLflow...")
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        with mlflow.start_run(run_name=f"retrain_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
            mlflow.log_params({
                "retrain": True,
                "feedback_count": len(feedback),
                "n_estimators": 200,
                "max_depth": 6,
            })
            mlflow.log_metric("pr_auc", new_pr_auc)
            mlflow.xgboost.log_model(model, "fraud_detector_retrained")

        # Save new model
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_model_path = os.path.join(MODEL_DIR, f"fraud_detector_{version}.pkl")
        os.makedirs(MODEL_DIR, exist_ok=True)
        with open(new_model_path, "wb") as f:
            pickle.dump(model, f)

        # Also update the main model file
        main_model_path = os.path.join(MODEL_DIR, "fraud_detector_v1.pkl")
        with open(main_model_path, "wb") as f:
            pickle.dump(model, f)

        # Drift detection
        drift_result = self.detect_drift(new_pr_auc)

        result = {
            "status": "retrained",
            "new_pr_auc": round(new_pr_auc, 4),
            "model_path": new_model_path,
            "feedback_applied": len(feedback),
            "drift_alert": drift_result,
            "timestamp": datetime.now().isoformat(),
        }

        print(f"\n  New PR-AUC: {new_pr_auc:.4f}")
        print(f"  Model saved: {new_model_path}")
        if drift_result.get("alert"):
            print(f"  DRIFT ALERT: {drift_result['message']}")
        else:
            print(f"  No drift detected.")

        print("\n" + "=" * 60)
        return result

    def detect_drift(self, current_pr_auc: float, threshold: float = 0.05) -> Dict:
        """
        Detect model drift by comparing current PR-AUC to baseline.
        Alert if drop > threshold (default 5%).
        """
        if self.baseline_pr_auc is None:
            # Try to load baseline from MLflow
            try:
                mlflow.set_experiment(MLFLOW_EXPERIMENT)
                runs = mlflow.search_runs(order_by=["start_time ASC"], max_results=1)
                if not runs.empty and "metrics.pr_auc" in runs.columns:
                    self.baseline_pr_auc = runs.iloc[0]["metrics.pr_auc"]
                else:
                    self.baseline_pr_auc = current_pr_auc
            except Exception:
                self.baseline_pr_auc = current_pr_auc

        drop = self.baseline_pr_auc - current_pr_auc
        drop_pct = drop / self.baseline_pr_auc if self.baseline_pr_auc > 0 else 0

        if drop_pct > threshold:
            return {
                "alert": True,
                "baseline_pr_auc": round(self.baseline_pr_auc, 4),
                "current_pr_auc": round(current_pr_auc, 4),
                "drop_percentage": round(drop_pct * 100, 2),
                "message": f"PR-AUC dropped {drop_pct*100:.1f}% from baseline "
                           f"({self.baseline_pr_auc:.4f} -> {current_pr_auc:.4f}). "
                           f"Consider investigating data quality or feature drift.",
            }
        else:
            return {
                "alert": False,
                "baseline_pr_auc": round(self.baseline_pr_auc, 4),
                "current_pr_auc": round(current_pr_auc, 4),
                "message": "No significant drift detected.",
            }

    def get_retraining_schedule(self) -> str:
        """Return the documented retraining schedule."""
        return """
RETRAINING SCHEDULE
===================
Frequency: Monthly (1st of each month) or on-demand

Automatic Triggers:
- 100+ new feedback records since last retrain
- PR-AUC drops >5% from baseline in monitoring

Manual Trigger:
- Run: python src/models/self_improvement.py --retrain
- Or via API: POST /retrain (admin access required)

Monitoring:
- MLflow dashboard tracks all experiments
- Drift alerts logged to console and stored in MLflow
"""


# --- CLI ---
if __name__ == "__main__":
    import sys

    loop = SelfImprovementLoop()

    if "--retrain" in sys.argv:
        loop.retrain_model()
    elif "--stats" in sys.argv:
        stats = loop.get_feedback_stats()
        print("Feedback Statistics:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    elif "--schedule" in sys.argv:
        print(loop.get_retraining_schedule())
    else:
        # Demo: record some sample feedback
        print("Self-Improvement Loop - Demo")
        print("=" * 50)

        # Get sample transactions
        engine = create_engine(DATABASE_URL)
        txns = pd.read_sql("SELECT transaction_id FROM transactions LIMIT 5", engine)

        if not txns.empty:
            # Simulate banker feedback
            print("\nRecording sample feedback...")
            for i, row in txns.iterrows():
                result = loop.record_feedback(
                    txn_id=row["transaction_id"],
                    predicted_fraud=0.85 if i == 0 else 0.15,
                    banker_says_fraud=(i == 0),  # First one is fraud
                    notes=f"Sample feedback for demo (transaction {i+1})"
                )
                print(f"  {result['agreement']}: txn={result['txn_id'][:10]}... "
                      f"model={result['predicted_fraud']:.2f}, banker={result['banker_says_fraud']}")

        # Show stats
        print("\n" + "-" * 50)
        stats = loop.get_feedback_stats()
        print("Feedback Statistics:")
        for k, v in stats.items():
            print(f"  {k}: {v}")

        print("\n" + loop.get_retraining_schedule())
