"""
Customer Data Generator for the Banking AI System.

Generates 1,000 synthetic banking customers with realistic distributions:
- Lognormal balance distribution (skewed like real wealth)
- Normal credit score distribution centered around 680
- Risk level derived from credit_score + balance
- Multiple account types with weighted distribution
- Demographics: age, income (correlated with account type)

Fields: customer_id, name, email, age, income, credit_score, risk_level,
        account_type, balance, account_opened, account_age_days, avg_sentiment, created_at
"""
import pandas as pd
import numpy as np
from faker import Faker
from datetime import datetime, timedelta
import os

fake = Faker()
Faker.seed(42)
np.random.seed(42)

# Account types with weighted distribution
ACCOUNT_TYPES = {
    "checking": 0.35,
    "savings": 0.25,
    "business": 0.10,
    "premium": 0.08,
    "student": 0.07,
    "joint": 0.08,
    "retirement": 0.07,
}


def assign_risk_level(credit_score: int, balance: float) -> str:
    """Assign risk level based on credit score and balance."""
    if credit_score >= 720 and balance >= 10000:
        return "Low"
    elif credit_score >= 620 and balance >= 2000:
        return "Medium"
    else:
        return "High"


def generate_customers(n=1000):
    """Generate n synthetic banking customers."""
    account_type_names = list(ACCOUNT_TYPES.keys())
    account_type_weights = list(ACCOUNT_TYPES.values())

    customers = []
    for _ in range(n):
        # Account type (weighted)
        account_type = np.random.choice(account_type_names, p=account_type_weights)

        # Age: 18-85, roughly normal around 42
        age = int(np.clip(np.random.normal(42, 14), 18, 85))

        # Income: correlated with account type
        if account_type == "student":
            income = round(np.random.lognormal(mean=9.5, sigma=0.4), 2)   # ~$13K
        elif account_type in ("premium", "business"):
            income = round(np.random.lognormal(mean=11.5, sigma=0.5), 2)  # ~$100K+
        elif account_type == "retirement":
            income = round(np.random.lognormal(mean=10.5, sigma=0.6), 2)  # ~$36K
        else:
            income = round(np.random.lognormal(mean=10.8, sigma=0.7), 2)  # ~$50K

        # Balance: lognormal distribution (skewed like real wealth)
        balance = round(np.random.lognormal(mean=9.2, sigma=0.8), 2)

        # Credit score: 300 to 850, roughly normal around 680
        credit_score = int(np.clip(np.random.normal(680, 70), 300, 850))

        # Risk level: derived from credit_score and balance
        risk_level = assign_risk_level(credit_score, balance)

        # Sentiment average: -1.0 to 1.0, slightly positive bias
        avg_sentiment = round(np.random.uniform(-0.5, 0.8), 2)

        # Account age: 30 to 5000 days
        account_age_days = np.random.randint(30, 5000)

        # Account opened date (derived from account_age_days)
        account_opened = (datetime.now() - timedelta(days=int(account_age_days))).strftime("%Y-%m-%d")

        customer = {
            "customer_id": fake.uuid4()[:8],
            "name": fake.name(),
            "email": fake.email(),
            "age": age,
            "income": income,
            "credit_score": credit_score,
            "risk_level": risk_level,
            "account_type": account_type,
            "balance": balance,
            "account_opened": account_opened,
            "account_age_days": account_age_days,
            "sentiment_avg": avg_sentiment,
            "created_at": fake.date_time_between(start_date="-10y", end_date="now").isoformat(),
        }
        customers.append(customer)

    df = pd.DataFrame(customers)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/customers.csv", index=False)

    # Summary
    print(f"Generated {n} customers -> data/raw/customers.csv")
    print(f"  Risk distribution: {df['risk_level'].value_counts().to_dict()}")
    print(f"  Account types:     {df['account_type'].value_counts().to_dict()}")
    print(f"  Credit score:      {df['credit_score'].min()}-{df['credit_score'].max()} (mean {df['credit_score'].mean():.0f})")
    print(f"  Balance:           ${df['balance'].min():,.2f} - ${df['balance'].max():,.2f} (median ${df['balance'].median():,.2f})")
    return df


if __name__ == "__main__":
    generate_customers()
