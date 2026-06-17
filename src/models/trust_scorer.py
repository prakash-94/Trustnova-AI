"""
Trust Score Engine for the Banking AI System.

Calculates a composite trust score (0-100) for each customer using:
- account_age (weight: 0.20)
- credit_score (weight: 0.30)
- fraud_history (weight: 0.25)
- sentiment_avg (weight: 0.15)
- interaction_count (weight: 0.10)

Maps to tiers: High Risk (0-40), Moderate (41-70), Trusted (71-100).
Stores score history in SQLite.
"""
import os
from datetime import datetime
from typing import Dict, Optional, List

import pandas as pd
from sqlalchemy import create_engine, text
from src.models.database import auto_pk

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")

# --- Weight Configuration ---
WEIGHTS = {
    "account_age": 0.20,
    "credit_score": 0.30,
    "fraud_history": 0.25,
    "sentiment_avg": 0.15,
    "interaction_count": 0.10,
}

TIERS = {
    "High Risk": (0, 40),
    "Moderate": (41, 70),
    "Trusted": (71, 100),
}


class TrustScoreCalculator:
    """
    Calculates and manages trust scores for banking customers.
    
    Score components (all normalized to 0-100 before weighting):
    - account_age:       Older accounts → higher score. Max at 10 years (3650 days).
    - credit_score:      300-850 mapped to 0-100.
    - fraud_history:     100 if no fraud, decreasing with each fraud incident.
    - sentiment_avg:     -1.0 to 1.0 mapped to 0-100.
    - interaction_count: More interactions → higher (up to a cap).
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_trust_scores_table()

    def _ensure_trust_scores_table(self):
        """Create the trust_scores table if it doesn't exist."""
        with self.engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS trust_scores (
                    id {auto_pk},
                    customer_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    tier TEXT NOT NULL,
                    account_age_component REAL,
                    credit_score_component REAL,
                    fraud_history_component REAL,
                    sentiment_component REAL,
                    interaction_component REAL,
                    timestamp TEXT NOT NULL
                )
            """))
            conn.commit()

    def _get_customer_data(self, customer_id: str) -> Optional[Dict]:
        """Fetch customer data, trying multiple table/column schemas for resilience."""
        attempts = [
            "SELECT * FROM customers WHERE customer_id = :cid",
            "SELECT * FROM customers WHERE id = :cid",
            "SELECT * FROM customers_new WHERE id = :cid",
            "SELECT * FROM customers_new WHERE customer_id = :cid",
        ]
        for q in attempts:
            try:
                df = pd.read_sql(text(q), self.engine, params={"cid": customer_id})
                if not df.empty:
                    return df.iloc[0].to_dict()
            except Exception:
                continue
        return None

    def _get_fraud_count(self, customer_id: str) -> int:
        """Count fraud incidents for a customer."""
        query = text("""
            SELECT COUNT(*) as fraud_count
            FROM enriched_transactions
            WHERE customer_id = :cid AND is_fraud = 1
        """)
        result = pd.read_sql(query, self.engine, params={"cid": customer_id})
        return int(result.iloc[0]["fraud_count"])

    def _get_interaction_stats(self, customer_id: str) -> Dict:
        """Get interaction statistics for a customer."""
        query = text("""
            SELECT 
                COUNT(*) as interaction_count,
                AVG(sentiment_score) as avg_sentiment
            FROM interactions 
            WHERE customer_id = :cid
        """)
        result = pd.read_sql(query, self.engine, params={"cid": customer_id})
        row = result.iloc[0]
        return {
            "interaction_count": int(row["interaction_count"]) if pd.notna(row["interaction_count"]) else 0,
            "avg_sentiment": float(row["avg_sentiment"]) if pd.notna(row["avg_sentiment"]) else 0.0,
        }

    def _normalize_account_age(self, age_days: int) -> float:
        """Normalize account age to 0-100. Max score at 10 years (3650 days)."""
        return min(age_days / 3650.0, 1.0) * 100

    def _normalize_credit_score(self, credit_score: int) -> float:
        """Normalize credit score (300-850) to 0-100."""
        return max(0, min(100, (credit_score - 300) / 550.0 * 100))

    def _normalize_fraud_history(self, fraud_count: int) -> float:
        """
        Score fraud history. 
        0 fraud = 100, each fraud incident reduces by 25, minimum 0.
        """
        return max(0, 100 - fraud_count * 25)

    def _normalize_sentiment(self, sentiment_avg: float) -> float:
        """Normalize sentiment (-1.0 to 1.0) to 0-100."""
        return (sentiment_avg + 1.0) / 2.0 * 100

    def _normalize_interaction_count(self, count: int) -> float:
        """
        Normalize interaction count. Cap at 20 interactions for max score.
        More interactions = more engaged customer = higher trust.
        """
        return min(count / 20.0, 1.0) * 100

    def _get_tier(self, score: float) -> str:
        """Map score to tier."""
        if score <= 40:
            return "High Risk"
        elif score <= 70:
            return "Moderate"
        else:
            return "Trusted"

    def calculate(self, customer_id: str) -> Dict:
        """
        Calculate trust score for a customer.

        Returns:
            Dict with score, tier, components, and metadata.
        """
        # Fetch data
        customer = self._get_customer_data(customer_id)
        if not customer:
            return {
                "customer_id": customer_id,
                "score": 0,
                "tier": "Unknown",
                "error": "Customer not found",
            }

        fraud_count = self._get_fraud_count(customer_id)
        interaction_stats = self._get_interaction_stats(customer_id)

        # Compute account age from created_at if account_age_days not available
        age_days = customer.get("account_age_days") or 0
        if not age_days and customer.get("created_at"):
            try:
                created = datetime.fromisoformat(str(customer["created_at"])[:19])
                age_days = (datetime.now() - created).days
            except Exception:
                age_days = 0

        credit = int(customer.get("credit_score") or 650)

        # Calculate components (normalized to 0-100)
        components = {
            "account_age": self._normalize_account_age(int(age_days)),
            "credit_score": self._normalize_credit_score(credit),
            "fraud_history": self._normalize_fraud_history(fraud_count),
            "sentiment_avg": self._normalize_sentiment(interaction_stats["avg_sentiment"]),
            "interaction_count": self._normalize_interaction_count(interaction_stats["interaction_count"]),
        }

        # Calculate weighted score
        score = sum(
            components[key] * WEIGHTS[key]
            for key in WEIGHTS
        )
        score = round(max(0, min(100, score)), 1)

        tier = self._get_tier(score)

        result = {
            "customer_id": customer_id,
            "score": score,
            "tier": tier,
            "components": {k: round(v, 1) for k, v in components.items()},
            "weights": WEIGHTS,
            "fraud_incidents": fraud_count,
            "total_interactions": interaction_stats["interaction_count"],
            "timestamp": datetime.now().isoformat(),
        }

        # Store in history
        self._store_score(result)

        return result

    def _store_score(self, result: Dict):
        """Store trust score in the history table."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO trust_scores 
                (customer_id, score, tier, account_age_component, credit_score_component,
                 fraud_history_component, sentiment_component, interaction_component, timestamp)
                VALUES (:cid, :score, :tier, :age, :credit, :fraud, :sentiment, :interaction, :ts)
            """), {
                "cid": result["customer_id"],
                "score": result["score"],
                "tier": result["tier"],
                "age": result["components"]["account_age"],
                "credit": result["components"]["credit_score"],
                "fraud": result["components"]["fraud_history"],
                "sentiment": result["components"]["sentiment_avg"],
                "interaction": result["components"]["interaction_count"],
                "ts": result["timestamp"],
            })
            conn.commit()

    def get_score_history(self, customer_id: str, limit: int = 10) -> List[Dict]:
        """Get historical trust scores for a customer."""
        query = text("""
            SELECT score, tier, timestamp 
            FROM trust_scores 
            WHERE customer_id = :cid 
            ORDER BY timestamp DESC 
            LIMIT :limit
        """)
        df = pd.read_sql(query, self.engine, params={"cid": customer_id, "limit": limit})
        return df.to_dict(orient="records")

    def update_on_event(self, event: Dict):
        """
        Recalculate trust score based on a new event.

        Supported event types:
        - 'fraud_detected': A transaction was flagged as fraud
        - 'fraud_cleared': A fraud flag was removed (false positive)
        - 'positive_interaction': A positive banker interaction
        - 'negative_interaction': A negative banker interaction
        - 'general': General recalculation

        Args:
            event: dict with 'customer_id', 'event_type', and optional 'details'
        """
        customer_id = event.get("customer_id")
        event_type = event.get("event_type", "general")

        if not customer_id:
            return {"error": "customer_id is required"}

        # Simply recalculate — the underlying data should already be updated
        # before calling this method
        result = self.calculate(customer_id)
        result["triggered_by"] = event_type

        return result

    def batch_calculate(self, limit: int = None) -> pd.DataFrame:
        """
        Calculate trust scores for all customers (or a limited batch).
        Returns a DataFrame with scores.
        """
        try:
            query = "SELECT customer_id FROM customers"
            if limit:
                query += f" LIMIT {limit}"
            customers = pd.read_sql(query, self.engine)
        except Exception:
            query = "SELECT id AS customer_id FROM customers"
            if limit:
                query += f" LIMIT {limit}"
            customers = pd.read_sql(query, self.engine)
        
        results = []
        for _, row in customers.iterrows():
            score = self.calculate(row["customer_id"])
            results.append(score)

        df = pd.DataFrame(results)
        return df


def format_trust_score(result: Dict) -> str:
    """Format trust score for display."""
    if "error" in result:
        return f"Error: {result['error']}"

    output = f"""
{'='*50}
TRUST SCORE REPORT
{'='*50}
Customer ID:     {result['customer_id']}
Score:           {result['score']}/100
Tier:            {result['tier']}
Fraud Incidents: {result['fraud_incidents']}

COMPONENT BREAKDOWN:
"""
    for component, value in result["components"].items():
        weight = WEIGHTS[component]
        weighted = round(value * weight, 1)
        bar = "#" * int(value / 5)
        output += f"  {component:20s} {value:6.1f}/100 x {weight:.2f} = {weighted:5.1f}  {bar}\n"

    output += f"\n{'='*50}\n"
    return output


# --- CLI ---
if __name__ == "__main__":
    import sys

    calculator = TrustScoreCalculator()

    # Get a sample customer or use CLI arg
    if len(sys.argv) > 1:
        cid = sys.argv[1]
    else:
        customers = pd.read_sql("SELECT customer_id FROM customers LIMIT 5", calculator.engine)
        if customers.empty:
            print("No customers found in database.")
            sys.exit(1)

        print("Calculating trust scores for first 5 customers...\n")
        for _, row in customers.iterrows():
            result = calculator.calculate(row["customer_id"])
            print(format_trust_score(result))

        # Distribution summary
        print("\n" + "=" * 50)
        print("BATCH CALCULATION (first 50 customers):")
        batch = calculator.batch_calculate(limit=50)
        print(f"  Average Score:  {batch['score'].mean():.1f}")
        print(f"  Median Score:   {batch['score'].median():.1f}")
        print(f"  Tier Distribution:")
        tier_counts = batch["tier"].value_counts()
        for tier, count in tier_counts.items():
            print(f"    {tier}: {count} ({count/len(batch)*100:.0f}%)")
