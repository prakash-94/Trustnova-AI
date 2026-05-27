"""
Fraud Alert Generator for the Banking AI System.

Generates fraud alert records based on existing fraudulent transactions.
Each fraud transaction gets an alert with risk_score, reason, and status.
Also generates some false positive alerts from legitimate high-value transactions.

Fields: alert_id, customer_id, transaction_id, risk_score, reason, status, timestamp
Status: open, resolved, false_positive
"""
import pandas as pd
import numpy as np
from faker import Faker
import os
import random

fake = Faker()
Faker.seed(42)
np.random.seed(42)

FRAUD_REASONS = [
    "Transaction amount {amount_factor}x above customer average",
    "New device detected — first seen {hours_ago} hours ago",
    "Transaction originated from unusual location: {location}",
    "Multiple rapid transactions within {minutes}m window",
    "High-risk merchant category: {category}",
    "Card-not-present transaction from flagged IP range",
    "Cross-border transaction inconsistent with customer profile",
    "Unusual transaction time: {hour}:00 (customer typical: 9-17)",
    "Transaction velocity spike: {count} transactions in 30 minutes",
    "Amount ${amount:,.2f} exceeds daily spending pattern by {zscore:.1f} std deviations",
]


def generate_fraud_alerts():
    """Generate fraud alerts from existing transaction data."""
    try:
        txns = pd.read_csv("data/raw/transactions.csv")
        customers = pd.read_csv("data/raw/customers.csv")
    except FileNotFoundError:
        print("Error: transactions.csv or customers.csv not found. Run generators first.")
        return

    alerts = []

    # 1. Create alerts for all fraud transactions
    fraud_txns = txns[txns["is_fraud"] == 1]
    for _, txn in fraud_txns.iterrows():
        risk_score = round(np.random.uniform(0.65, 0.99), 2)

        # Generate realistic reason
        reason_template = random.choice(FRAUD_REASONS)
        reason = reason_template.format(
            amount_factor=round(np.random.uniform(2.5, 8.0), 1),
            hours_ago=random.randint(1, 48),
            location=txn.get("location", "Unknown"),
            minutes=random.choice([5, 10, 15, 30]),
            category=txn.get("category", "unknown"),
            hour=txn.get("hour", 2),
            count=random.randint(3, 12),
            amount=txn["amount"],
            zscore=round(np.random.uniform(2.0, 6.0), 1),
        )

        # Status: most are resolved, some still open
        status = random.choices(
            ["resolved", "open"],
            weights=[0.75, 0.25]
        )[0]

        alert = {
            "alert_id": fake.uuid4()[:12],
            "customer_id": txn["customer_id"],
            "transaction_id": txn["transaction_id"],
            "risk_score": risk_score,
            "reason": reason,
            "status": status,
            "timestamp": txn["timestamp"],
        }
        alerts.append(alert)

    # 2. Generate false positive alerts (legitimate txns flagged incorrectly)
    legit_txns = txns[txns["is_fraud"] == 0]
    # Pick ~5% of high-value legit transactions as false positives
    high_value = legit_txns[legit_txns["amount"] > legit_txns["amount"].quantile(0.95)]
    false_positive_sample = high_value.sample(n=min(len(high_value), int(len(fraud_txns) * 0.3)), random_state=42)

    for _, txn in false_positive_sample.iterrows():
        risk_score = round(np.random.uniform(0.35, 0.65), 2)

        reason_template = random.choice(FRAUD_REASONS)
        reason = reason_template.format(
            amount_factor=round(np.random.uniform(1.5, 3.0), 1),
            hours_ago=random.randint(1, 24),
            location=txn.get("location", "Unknown"),
            minutes=random.choice([15, 30]),
            category=txn.get("category", "unknown"),
            hour=txn.get("hour", 14),
            count=random.randint(2, 5),
            amount=txn["amount"],
            zscore=round(np.random.uniform(1.5, 3.0), 1),
        )

        alert = {
            "alert_id": fake.uuid4()[:12],
            "customer_id": txn["customer_id"],
            "transaction_id": txn["transaction_id"],
            "risk_score": risk_score,
            "reason": reason,
            "status": "false_positive",
            "timestamp": txn["timestamp"],
        }
        alerts.append(alert)

    df = pd.DataFrame(alerts)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/fraud_alerts.csv", index=False)

    print(f"Generated {len(df)} fraud alerts -> data/raw/fraud_alerts.csv")
    print(f"  Status:     {df['status'].value_counts().to_dict()}")
    print(f"  Risk score: {df['risk_score'].min():.2f} to {df['risk_score'].max():.2f} (mean {df['risk_score'].mean():.2f})")
    return df


if __name__ == "__main__":
    generate_fraud_alerts()
