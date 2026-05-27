"""
Transaction Data Generator for the Banking AI System.

Generates 15,000+ synthetic banking transactions with realistic fraud patterns:
- Fraud rate: 1.5%
- Fraudulent txns: higher amounts, unusual hours, geo mismatch, new devices, high-risk merchants
- Legitimate txns: normal patterns with occasional anomalies

Fields: transaction_id, customer_id, amount, merchant, merchant_risk, location,
        timestamp, device_change, location_change, frequency, is_fraud,
        hour, is_weekend, category
        (+ backward-compat aliases: geo_mismatch, device_new)
"""
import pandas as pd
import numpy as np
from faker import Faker
import os
import random

fake = Faker()
Faker.seed(42)
np.random.seed(42)

# Merchant data
MERCHANTS = {
    "grocery": {
        "names": ["Walmart", "Kroger", "Whole Foods", "Trader Joe's", "Aldi", "Costco", "Safeway"],
        "risk": 1,
    },
    "food": {
        "names": ["McDonald's", "Starbucks", "Chipotle", "DoorDash", "Uber Eats", "Panera Bread"],
        "risk": 1,
    },
    "utilities": {
        "names": ["Electric Co.", "Water Utility", "Gas Company", "Internet Provider", "Phone Service"],
        "risk": 1,
    },
    "entertainment": {
        "names": ["Netflix", "Spotify", "AMC Theaters", "Steam", "PlayStation Store", "Disney+"],
        "risk": 2,
    },
    "shopping": {
        "names": ["Amazon", "Target", "Best Buy", "Apple Store", "Nike", "Nordstrom", "Zara"],
        "risk": 2,
    },
    "travel": {
        "names": ["United Airlines", "Delta", "Marriott Hotels", "Airbnb", "Hertz", "Expedia"],
        "risk": 3,
    },
    "transfer": {
        "names": ["Venmo", "Zelle", "PayPal", "Cash App", "Wire Transfer", "ACH Transfer"],
        "risk": 3,
    },
    "crypto": {
        "names": ["Coinbase", "Binance", "Kraken", "Crypto.com"],
        "risk": 5,
    },
    "gambling": {
        "names": ["DraftKings", "FanDuel", "BetMGM", "PokerStars"],
        "risk": 5,
    },
}

LOCATIONS = [
    "New York, NY", "Los Angeles, CA", "Chicago, IL", "Houston, TX", "Phoenix, AZ",
    "Philadelphia, PA", "San Antonio, TX", "San Diego, CA", "Dallas, TX", "Austin, TX",
    "Miami, FL", "Atlanta, GA", "Boston, MA", "Seattle, WA", "Denver, CO",
    "Portland, OR", "Nashville, TN", "Charlotte, NC", "San Francisco, CA", "Detroit, MI",
]

SUSPICIOUS_LOCATIONS = [
    "Lagos, Nigeria", "Moscow, Russia", "Bucharest, Romania", "Jakarta, Indonesia",
    "Shenzhen, China", "Unknown VPN", "Offshore IP", "Tor Exit Node",
]


def generate_transactions(n=15000, fraud_rate=0.015):
    """Generate n synthetic banking transactions."""
    # Load customers
    try:
        customers_df = pd.read_csv("data/raw/customers.csv")
        customer_ids = customers_df["customer_id"].tolist()
    except FileNotFoundError:
        print("Error: customers.csv not found. Run generate_customers.py first.")
        return

    categories = list(MERCHANTS.keys())
    fraud_categories = ["crypto", "gambling", "transfer", "travel", "shopping"]

    transactions = []
    for _ in range(n):
        customer_id = random.choice(customer_ids)
        is_fraud = 1 if random.random() < fraud_rate else 0

        if is_fraud:
            # Fraud patterns
            category = random.choice(fraud_categories)
            amount = round(np.random.lognormal(mean=5.5, sigma=1.2), 2)
            hour = random.choice([0, 1, 2, 3, 4, 23])
            location_change = 1 if random.random() < 0.7 else 0
            device_change = 1 if random.random() < 0.6 else 0
            merchant_risk = random.choice([4, 5])
            location = random.choice(SUSPICIOUS_LOCATIONS) if location_change else random.choice(LOCATIONS)
            frequency = random.randint(3, 10)  # High velocity
        else:
            # Normal patterns
            category = random.choices(categories, weights=[0.25, 0.20, 0.12, 0.12, 0.15, 0.08, 0.06, 0.01, 0.01])[0]
            amount = round(np.random.lognormal(mean=3.5, sigma=0.8), 2)
            hour = random.randint(7, 22)
            location_change = 1 if random.random() < 0.05 else 0
            device_change = 1 if random.random() < 0.1 else 0
            merchant_risk = MERCHANTS[category]["risk"]
            location = random.choice(LOCATIONS)
            frequency = random.randint(0, 2)

        merchant_data = MERCHANTS[category]
        merchant = random.choice(merchant_data["names"])

        txn = {
            "transaction_id": fake.uuid4()[:10],
            "customer_id": customer_id,
            "amount": amount,
            "merchant": merchant,
            "merchant_risk": merchant_risk,
            "category": category,
            "location": location,
            "hour": hour,
            "is_weekend": 1 if random.random() < 0.28 else 0,
            "device_change": device_change,
            "location_change": location_change,
            "frequency": frequency,
            "is_fraud": is_fraud,
            "timestamp": fake.date_time_between(start_date="-1y", end_date="now").isoformat(),
            # Backward-compatible aliases for ML models
            "geo_mismatch": location_change,
            "device_new": device_change,
        }
        transactions.append(txn)

    df = pd.DataFrame(transactions)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/transactions.csv", index=False)

    fraud_count = df["is_fraud"].sum()
    print(f"Generated {n} transactions -> data/raw/transactions.csv")
    print(f"  Fraud:      {fraud_count} ({fraud_count/n*100:.2f}%)")
    print(f"  Merchants:  {df['merchant'].nunique()} unique")
    print(f"  Locations:  {df['location'].nunique()} unique")
    print(f"  Amount:     ${df['amount'].min():.2f} - ${df['amount'].max():,.2f} (median ${df['amount'].median():.2f})")
    return df


if __name__ == "__main__":
    generate_transactions()
