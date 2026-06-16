"""
Customer Risk Profiling — Phase 7.

Provides:
  - Structured risk profile per customer (risk_level, sentiment, fraud_risk,
    retention_probability)
  - Logistic regression retention model trained on customer features:
    avg_sentiment, support_ticket_count, fraud_flag_count, interaction_count,
    balance_trend (approximated as normalized balance)
  - Model saved to models/retention_model.pkl for reuse

Data sources (already in banking.db):
  - customers: 1,000 rows
  - enriched_transactions: aggregated features per customer
  - interactions, support_tickets, fraud_alerts, complaints
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
RETENTION_MODEL_PATH = os.path.join(MODEL_DIR, "retention_model.pkl")


class RiskProfiler:
    """
    Customer risk profiling engine with retention probability prediction.

    Generates structured risk profiles and trains a logistic regression
    model for retention probability based on customer behavior features.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._retention_model = None
        self._feature_scaler = None
        self._load_retention_model()

    # ==================================================================
    # Risk Profile Generation
    # ==================================================================

    def generate_risk_profile(self, customer_id: str) -> Dict:
        """
        Generate a structured risk profile for a customer.

        Returns:
            {
                "customer_id": "...",
                "risk_level": "Low" | "Medium" | "High",
                "sentiment": "Positive" | "Neutral" | "Negative",
                "fraud_risk": "Low" | "Medium" | "High",
                "retention_probability": 0.81,
                "risk_factors": [...],
                "generated_at": "..."
            }
        """
        # Fetch customer data
        customer = self._get_customer_data(customer_id)
        if customer is None:
            return {"customer_id": customer_id, "error": "Customer not found"}

        # Compute each risk dimension
        sentiment_label = self._assess_sentiment(customer_id)
        fraud_risk = self._assess_fraud_risk(customer_id)
        risk_level = self._assess_overall_risk(customer, sentiment_label, fraud_risk)
        retention_prob = self.predict_retention(customer_id)
        risk_factors = self._identify_risk_factors(customer, sentiment_label, fraud_risk)

        return {
            "customer_id": customer_id,
            "risk_level": risk_level,
            "sentiment": sentiment_label,
            "fraud_risk": fraud_risk,
            "retention_probability": retention_prob,
            "risk_factors": risk_factors,
            "generated_at": datetime.now().isoformat(),
        }

    def _get_customer_data(self, customer_id: str) -> Optional[Dict]:
        """Fetch customer profile data."""
        query = text("SELECT * FROM customers WHERE customer_id = :cid")
        df = pd.read_sql(query, self.engine, params={"cid": customer_id})
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def _assess_sentiment(self, customer_id: str) -> str:
        """Assess overall customer sentiment from interactions."""
        query = text("""
            SELECT AVG(sentiment_score) as avg_sentiment
            FROM interactions
            WHERE customer_id = :cid
        """)
        df = pd.read_sql(query, self.engine, params={"cid": customer_id})
        if df.empty or pd.isna(df.iloc[0]["avg_sentiment"]):
            return "Neutral"

        avg = float(df.iloc[0]["avg_sentiment"])
        if avg > 0.2:
            return "Positive"
        elif avg < -0.2:
            return "Negative"
        return "Neutral"

    def _assess_fraud_risk(self, customer_id: str) -> str:
        """Assess fraud risk based on transaction history."""
        # Count fraud incidents
        query = text("""
            SELECT COUNT(*) as fraud_count
            FROM transactions
            WHERE customer_id = :cid AND is_fraud = 1
        """)
        df = pd.read_sql(query, self.engine, params={"cid": customer_id})
        fraud_count = int(df.iloc[0]["fraud_count"]) if not df.empty else 0

        # Count fraud alerts
        try:
            query2 = text("""
                SELECT COUNT(*) as alert_count
                FROM fraud_alerts
                WHERE customer_id = :cid AND status != 'false_positive'
            """)
            df2 = pd.read_sql(query2, self.engine, params={"cid": customer_id})
            alert_count = int(df2.iloc[0]["alert_count"]) if not df2.empty else 0
        except Exception:
            alert_count = 0

        total_risk = fraud_count + alert_count
        if total_risk >= 3:
            return "High"
        elif total_risk >= 1:
            return "Medium"
        return "Low"

    def _assess_overall_risk(self, customer: Dict, sentiment: str, fraud_risk: str) -> str:
        """Compute overall risk level from multiple dimensions."""
        risk_score = 0

        # Credit score factor
        credit = int(customer.get("credit_score", 700))
        if credit < 500:
            risk_score += 3
        elif credit < 650:
            risk_score += 2
        elif credit < 750:
            risk_score += 1

        # Sentiment factor
        if sentiment == "Negative":
            risk_score += 2
        elif sentiment == "Neutral":
            risk_score += 1

        # Fraud factor
        if fraud_risk == "High":
            risk_score += 3
        elif fraud_risk == "Medium":
            risk_score += 1

        # Balance factor
        balance = float(customer.get("balance", 0))
        if balance < 1000:
            risk_score += 1

        # Account age factor
        age_days = int(customer.get("account_age_days", 365))
        if age_days < 180:
            risk_score += 1

        if risk_score >= 5:
            return "High"
        elif risk_score >= 3:
            return "Medium"
        return "Low"

    def _identify_risk_factors(self, customer: Dict, sentiment: str, fraud_risk: str) -> List[str]:
        """Identify specific risk factors for this customer."""
        factors = []

        credit = int(customer.get("credit_score", 700))
        if credit < 500:
            factors.append(f"Very low credit score ({credit})")
        elif credit < 650:
            factors.append(f"Below-average credit score ({credit})")

        balance = float(customer.get("balance", 0))
        if balance < 1000:
            factors.append(f"Low account balance (${balance:,.2f})")

        age_days = int(customer.get("account_age_days", 365))
        if age_days < 180:
            factors.append(f"New account ({age_days} days)")

        if sentiment == "Negative":
            factors.append("Negative interaction sentiment trend")

        if fraud_risk == "High":
            factors.append("High fraud risk — multiple fraud incidents")
        elif fraud_risk == "Medium":
            factors.append("Moderate fraud risk — prior fraud incident")

        if not factors:
            factors.append("No significant risk factors identified")

        return factors

    # ==================================================================
    # Retention Probability Model
    # ==================================================================

    def train_retention_model(self) -> Dict:
        """
        Train a logistic regression model for customer retention probability.

        Features (per TODO spec):
          - avg_sentiment: average interaction sentiment score
          - support_ticket_count: total support tickets
          - fraud_flag_count: number of fraud flags
          - interaction_count: total interactions (proxy for engagement)
          - balance_trend: normalized balance (proxy for financial health)

        Target: synthetic retention label derived from customer health signals.

        Returns:
            Training results with accuracy, feature importances, etc.
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, classification_report

        # Build feature matrix from customer data
        features_df = self._build_feature_matrix()
        if features_df is None or features_df.empty:
            return {"error": "No customer data available for training"}

        # Generate synthetic retention labels
        # Customers with good health signals → retained (1), poor signals → churned (0)
        features_df["retained"] = self._generate_retention_labels(features_df)

        feature_cols = [
            "avg_sentiment",
            "support_ticket_count",
            "fraud_flag_count",
            "interaction_count",
            "balance_normalized",
        ]

        X = features_df[feature_cols].fillna(0)
        y = features_df["retained"]

        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y,
        )

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train logistic regression (interpretable, explainable)
        model = LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight="balanced",
        )
        model.fit(X_train_scaled, y_train)

        # Evaluate
        y_pred = model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True)

        # Feature importances (logistic regression coefficients)
        coefficients = dict(zip(feature_cols, model.coef_[0].tolist()))

        # Save model + scaler
        os.makedirs(MODEL_DIR, exist_ok=True)
        with open(RETENTION_MODEL_PATH, "wb") as f:
            pickle.dump({"model": model, "scaler": scaler, "features": feature_cols}, f)

        self._retention_model = model
        self._feature_scaler = scaler

        return {
            "accuracy": round(accuracy, 4),
            "classification_report": report,
            "feature_coefficients": {k: round(v, 4) for k, v in coefficients.items()},
            "train_size": len(X_train),
            "test_size": len(X_test),
            "retention_rate": round(float(y.mean()), 4),
            "model_path": RETENTION_MODEL_PATH,
        }

    def predict_retention(self, customer_id: str) -> float:
        """
        Predict retention probability for a customer.

        Returns float in [0, 1] — probability of customer remaining.
        """
        if self._retention_model is None:
            return 0.75  # Default when model not trained

        features = self._get_customer_features(customer_id)
        if features is None:
            return 0.75

        feature_cols = [
            "avg_sentiment",
            "support_ticket_count",
            "fraud_flag_count",
            "interaction_count",
            "balance_normalized",
        ]

        X = pd.DataFrame([features])[feature_cols].fillna(0)
        X_scaled = self._feature_scaler.transform(X)
        prob = self._retention_model.predict_proba(X_scaled)[0]

        # Return probability of retained (class 1)
        return round(float(prob[1]), 4)

    def _build_feature_matrix(self) -> Optional[pd.DataFrame]:
        """Build feature matrix for all customers."""
        # Get all customers
        customers = pd.read_sql("SELECT customer_id, credit_score, balance, "
                                "sentiment_avg, account_age_days FROM customers",
                                self.engine)

        if customers.empty:
            return None

        # Aggregate interaction features
        interactions = pd.read_sql("""
            SELECT customer_id,
                   AVG(sentiment_score) as avg_sentiment,
                   COUNT(*) as interaction_count
            FROM interactions
            GROUP BY customer_id
        """, self.engine)

        # Support ticket count
        tickets = pd.read_sql("""
            SELECT customer_id, COUNT(*) as support_ticket_count
            FROM support_tickets
            GROUP BY customer_id
        """, self.engine)

        # Fraud count
        fraud = pd.read_sql("""
            SELECT customer_id, COUNT(*) as fraud_flag_count
            FROM transactions
            WHERE is_fraud = 1
            GROUP BY customer_id
        """, self.engine)

        # Merge all
        df = customers.merge(interactions, on="customer_id", how="left")
        df = df.merge(tickets, on="customer_id", how="left")
        df = df.merge(fraud, on="customer_id", how="left")

        # Fill NAs
        df["avg_sentiment"] = df["avg_sentiment"].fillna(df["sentiment_avg"])
        df["interaction_count"] = df["interaction_count"].fillna(0)
        df["support_ticket_count"] = df["support_ticket_count"].fillna(0)
        df["fraud_flag_count"] = df["fraud_flag_count"].fillna(0)

        # Normalize balance (0-1 scale, capped at $200k)
        df["balance_normalized"] = df["balance"].clip(0, 200000) / 200000.0

        return df

    def _generate_retention_labels(self, df: pd.DataFrame) -> pd.Series:
        """
        Generate synthetic retention labels from customer health signals.

        A customer is "retained" if they show positive health indicators.
        This creates a realistic training target based on actual data patterns.
        """
        # Compute a health score based on available signals
        health = pd.Series(0.0, index=df.index)

        # Good sentiment → retained
        health += (df["avg_sentiment"].fillna(0) + 1) / 2  # 0-1

        # Low ticket count → retained (normalized inversely)
        max_tickets = df["support_ticket_count"].max() or 1
        health += 1 - (df["support_ticket_count"] / max_tickets)

        # No fraud → retained
        health += (df["fraud_flag_count"] == 0).astype(float)

        # High engagement (some interactions) → retained
        max_interactions = df["interaction_count"].max() or 1
        health += (df["interaction_count"] / max_interactions).clip(0, 1)

        # Good balance → retained
        health += df["balance_normalized"]

        # Good credit → retained
        health += ((df["credit_score"] - 300) / 550).clip(0, 1)

        # Normalize to 0-1 and threshold
        health = health / 6.0  # 6 components
        # Add some noise for realism
        np.random.seed(42)
        health += np.random.normal(0, 0.05, len(health))

        # Top 75% retained, bottom 25% churned
        threshold = health.quantile(0.25)
        return (health > threshold).astype(int)

    def _get_customer_features(self, customer_id: str) -> Optional[Dict]:
        """Get feature vector for a single customer."""
        customer = pd.read_sql(
            text("SELECT credit_score, balance, sentiment_avg "
                 "FROM customers WHERE customer_id = :cid"),
            self.engine, params={"cid": customer_id},
        )
        if customer.empty:
            return None

        row = customer.iloc[0]

        # Interaction features
        interactions = pd.read_sql(
            text("SELECT AVG(sentiment_score) as avg_sentiment, "
                 "COUNT(*) as interaction_count FROM interactions "
                 "WHERE customer_id = :cid"),
            self.engine, params={"cid": customer_id},
        )

        # Ticket count
        tickets = pd.read_sql(
            text("SELECT COUNT(*) as support_ticket_count FROM support_tickets "
                 "WHERE customer_id = :cid"),
            self.engine, params={"cid": customer_id},
        )

        # Fraud count
        fraud = pd.read_sql(
            text("SELECT COUNT(*) as fraud_flag_count FROM transactions "
                 "WHERE customer_id = :cid AND is_fraud = 1"),
            self.engine, params={"cid": customer_id},
        )

        i_row = interactions.iloc[0] if not interactions.empty else {}
        t_row = tickets.iloc[0] if not tickets.empty else {}
        f_row = fraud.iloc[0] if not fraud.empty else {}

        return {
            "avg_sentiment": float(i_row.get("avg_sentiment") or row.get("sentiment_avg", 0)),
            "support_ticket_count": int(t_row.get("support_ticket_count", 0)),
            "fraud_flag_count": int(f_row.get("fraud_flag_count", 0)),
            "interaction_count": int(i_row.get("interaction_count", 0)),
            "balance_normalized": min(float(row.get("balance", 0)), 200000) / 200000.0,
        }

    def _load_retention_model(self):
        """Load the trained retention model if it exists."""
        if os.path.exists(RETENTION_MODEL_PATH):
            try:
                with open(RETENTION_MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                self._retention_model = data["model"]
                self._feature_scaler = data["scaler"]
            except Exception:
                pass

    # ==================================================================
    # Batch Risk Profiling
    # ==================================================================

    def batch_profile(self, limit: int = None) -> pd.DataFrame:
        """Generate risk profiles for all customers (or a limited batch)."""
        query = "SELECT customer_id FROM customers"
        if limit:
            query += f" LIMIT {limit}"

        customers = pd.read_sql(query, self.engine)
        results = []
        for _, row in customers.iterrows():
            profile = self.generate_risk_profile(row["customer_id"])
            results.append(profile)

        return pd.DataFrame(results)


# --- CLI ---
if __name__ == "__main__":
    profiler = RiskProfiler()

    print("=" * 60)
    print("Customer Risk Profiling — Phase 7")
    print("=" * 60)

    # Train retention model
    print("\nTraining retention probability model...")
    result = profiler.train_retention_model()
    print(f"  Accuracy:       {result['accuracy']:.4f}")
    print(f"  Retention rate: {result['retention_rate']:.4f}")
    print(f"  Train/Test:     {result['train_size']}/{result['test_size']}")
    print(f"  Model saved:    {result['model_path']}")
    print(f"\n  Feature coefficients:")
    for feat, coeff in result["feature_coefficients"].items():
        direction = "+ retained" if coeff > 0 else "- churn risk"
        print(f"    {feat:25s} {coeff:+.4f}  ({direction})")

    # Generate sample profiles
    print(f"\n{'-' * 60}")
    print("Sample risk profiles (first 5 customers):")
    batch = profiler.batch_profile(limit=5)
    for _, row in batch.iterrows():
        print(f"\n  Customer: {row['customer_id']}")
        print(f"    Risk Level:    {row['risk_level']}")
        print(f"    Sentiment:     {row['sentiment']}")
        print(f"    Fraud Risk:    {row['fraud_risk']}")
        print(f"    Retention:     {row['retention_probability']:.2%}")
        print(f"    Risk Factors:  {row['risk_factors']}")

    # Distribution
    print(f"\n{'-' * 60}")
    print("Batch profiling (first 50 customers)...")
    batch50 = profiler.batch_profile(limit=50)
    print(f"  Risk Level Distribution:")
    for level, count in batch50["risk_level"].value_counts().items():
        print(f"    {level}: {count} ({count/len(batch50)*100:.0f}%)")
    print(f"  Avg Retention Probability: {batch50['retention_probability'].mean():.2%}")
    print("=" * 60)
