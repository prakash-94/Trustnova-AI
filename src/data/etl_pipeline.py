"""
ETL Pipeline for the Banking AI System.

Loads all raw datasets, cleans and normalizes them, engineers features,
joins structured data, and writes everything to SQLite (banking.db).

Tables written:
  - customers              (raw customer profiles)
  - transactions            (raw transactions)
  - interactions            (banker interaction notes)
  - support_tickets         (customer support tickets)
  - fraud_alerts            (fraud alert records)
  - chat_transcripts        (multi-turn chat transcripts)
  - complaints              (complaint transcripts)
  - enriched_transactions   (transactions + customer data + engineered features)
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import os
import uuid
import random
from dotenv import load_dotenv
load_dotenv()
import hashlib
import datetime


def load_raw_data():
    """Load all raw CSV files."""
    data = {}

    files = {
        "customers": "data/raw/customers.csv",
        "transactions": "data/raw/transactions.csv",
        "interactions": "data/raw/interactions.csv",
        "support_tickets": "data/raw/support_tickets.csv",
        "fraud_alerts": "data/raw/fraud_alerts.csv",
        "chat_transcripts": "data/raw/chat_transcripts.csv",
        "complaints": "data/raw/complaints.csv",
    }

    for name, path in files.items():
        if os.path.exists(path):
            data[name] = pd.read_csv(path)
            print(f"  Loaded {name}: {len(data[name]):,} rows")
        else:
            print(f"  WARNING: {path} not found. Skipping.")

    return data


def aggregate_customer_sentiment(interactions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate interaction sentiment per customer."""
    agg = interactions.groupby("customer_id")["sentiment_score"].agg(["mean", "count"]).reset_index()
    agg.columns = ["customer_id", "avg_interaction_sentiment", "interaction_count"]
    return agg


def aggregate_support_tickets(tickets: pd.DataFrame) -> pd.DataFrame:
    """Aggregate support ticket counts per customer."""
    agg = tickets.groupby("customer_id").agg(
        ticket_count=("ticket_id", "count"),
        avg_ticket_sentiment=("sentiment", "mean"),
    ).reset_index()
    return agg


def aggregate_complaints(complaints: pd.DataFrame) -> pd.DataFrame:
    """Aggregate complaint counts per customer."""
    agg = complaints.groupby("customer_id").agg(
        complaint_count=("complaint_id", "count"),
        avg_complaint_sentiment=("sentiment_score", "mean"),
    ).reset_index()
    return agg


def aggregate_fraud_history(transactions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fraud incident counts per customer."""
    fraud = transactions.groupby("customer_id")["is_fraud"].sum().reset_index()
    fraud.columns = ["customer_id", "fraud_flag_count"]
    return fraud


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer ML features on the enriched transactions dataframe."""
    # amount_zscore: how many standard deviations the amount is from the customer's average
    customer_stats = df.groupby("customer_id")["amount"].agg(["mean", "std"]).reset_index()
    customer_stats.columns = ["customer_id", "customer_avg_amount", "customer_std_amount"]
    df = df.merge(customer_stats, on="customer_id", how="left")

    df["amount_zscore"] = (df["amount"] - df["customer_avg_amount"]) / df["customer_std_amount"]
    df["amount_zscore"] = df["amount_zscore"].fillna(0)  # Customers with 1 transaction

    # velocity_30m: simulated as Poisson-distributed transaction frequency
    # In a real system this would be computed from timestamps in real-time
    np.random.seed(42)
    df["velocity_30m"] = np.random.poisson(lam=0.5, size=len(df))

    # Ensure integer types for categorical features
    int_cols = ["hour", "is_weekend", "device_new", "geo_mismatch", "merchant_risk"]
    for col in int_cols:
        if col in df.columns:
            df[col] = df[col].astype(int)

    # device_change and location_change as integers (backward compat)
    if "device_change" in df.columns:
        df["device_change"] = df["device_change"].astype(int)
    if "location_change" in df.columns:
        df["location_change"] = df["location_change"].astype(int)

    # Drop helper columns
    df = df.drop(columns=["customer_avg_amount", "customer_std_amount"], errors="ignore")

    return df


def run_etl():
    """Full ETL pipeline."""
    print("=" * 60)
    print("Banking AI — ETL Pipeline")
    print("=" * 60)

    # Step 1: Load all raw data
    print("\n[1/6] Loading raw data...")
    data = load_raw_data()

    customers = data.get("customers")
    transactions = data.get("transactions")
    interactions = data.get("interactions")
    support_tickets = data.get("support_tickets")
    fraud_alerts = data.get("fraud_alerts")
    chat_transcripts = data.get("chat_transcripts")
    complaints = data.get("complaints")

    if customers is None or transactions is None:
        print("ERROR: customers.csv and transactions.csv are required.")
        return

    # Step 2: Aggregate sentiment and ticket data per customer
    print("\n[2/6] Aggregating customer metrics...")
    customer_enriched = customers.copy()

    if interactions is not None:
        sentiment_agg = aggregate_customer_sentiment(interactions)
        customer_enriched = customer_enriched.merge(sentiment_agg, on="customer_id", how="left")
        customer_enriched["avg_interaction_sentiment"] = customer_enriched["avg_interaction_sentiment"].fillna(0)
        customer_enriched["interaction_count"] = customer_enriched["interaction_count"].fillna(0).astype(int)
        print(f"  Interaction sentiment: {len(sentiment_agg)} customers")

    if support_tickets is not None:
        ticket_agg = aggregate_support_tickets(support_tickets)
        customer_enriched = customer_enriched.merge(ticket_agg, on="customer_id", how="left")
        customer_enriched["ticket_count"] = customer_enriched["ticket_count"].fillna(0).astype(int)
        customer_enriched["avg_ticket_sentiment"] = customer_enriched["avg_ticket_sentiment"].fillna(0)
        print(f"  Support tickets: {len(ticket_agg)} customers")

    if complaints is not None:
        complaint_agg = aggregate_complaints(complaints)
        customer_enriched = customer_enriched.merge(complaint_agg, on="customer_id", how="left")
        customer_enriched["complaint_count"] = customer_enriched["complaint_count"].fillna(0).astype(int)
        customer_enriched["avg_complaint_sentiment"] = customer_enriched["avg_complaint_sentiment"].fillna(0)
        print(f"  Complaints: {len(complaint_agg)} customers")

    fraud_agg = aggregate_fraud_history(transactions)
    customer_enriched = customer_enriched.merge(fraud_agg, on="customer_id", how="left")
    customer_enriched["fraud_flag_count"] = customer_enriched["fraud_flag_count"].fillna(0).astype(int)
    print(f"  Fraud history: {len(fraud_agg)} customers")

    # Step 3: Merge customer info onto transactions
    print("\n[3/6] Merging datasets...")
    df = transactions.merge(customer_enriched, on="customer_id", how="left")
    print(f"  Enriched transactions: {len(df):,} rows x {len(df.columns)} columns")

    # Step 4: Engineer features
    print("\n[4/6] Engineering features...")
    df = engineer_features(df)
    print(f"  Features added: amount_zscore, velocity_30m")
    print(f"  Final columns: {len(df.columns)}")

    # Step 5: Save processed data
    print("\n[5/6] Saving processed data...")
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv("data/processed/enriched_transactions.csv", index=False)
    print(f"  Saved: data/processed/enriched_transactions.csv ({len(df):,} rows)")

    # Step 6: Write all tables to SQLite
    print("\n[6/6] Writing to SQLite database...")
    db_url = os.getenv("DATABASE_URL", "sqlite:///banking.db")
    engine = create_engine(db_url)

    # -- Transform customers to match API schema ---------------------------
    def _seeded_rng(val, suffix):
        seed = int(hashlib.md5((str(val) + suffix).encode()).hexdigest(), 16) % (2**32)
        return random.Random(seed)

    customers_for_db = customers.copy()
    # Split "John Smith" → first_name + last_name
    def _split_name(n):
        parts = str(n).strip().split(' ', 1)
        return parts[0], (parts[1] if len(parts) > 1 else '')
    split = customers_for_db['name'].apply(_split_name)
    customers_for_db['first_name'] = split.apply(lambda x: x[0])
    customers_for_db['last_name'] = split.apply(lambda x: x[1])
    customers_for_db = customers_for_db.rename(columns={
        'risk_level': 'aml_risk_rating',
        'income': 'annual_income',
    })
    customers_for_db['kyc_status'] = 'pending'
    customers_for_db['segment'] = 'retail'
    customers_for_db['customer_type'] = 'individual'
    customers_for_db['is_pep'] = 0
    customers_for_db['is_sanctioned'] = 0
    customers_for_db['is_active'] = 1

    # -- Generate accounts (one per customer) ------------------------------
    accounts_rows = []
    for _, row in customers.iterrows():
        cid = row['customer_id']
        rng = _seeded_rng(cid, '_account')
        acct_num = 'AC' + ''.join(str(rng.randint(0, 9)) for _ in range(10))
        acct_id = str(rng.randint(10**18, 10**19 - 1))
        balance_cents = int(float(row['balance']) * 100)
        status = 'inactive' if rng.random() < 0.05 else 'active'
        accounts_rows.append({
            'id': acct_id,
            'customer_id': cid,
            'account_number': acct_num,
            'account_type': row['account_type'],
            'status': status,
            'balance_cents': balance_cents,
            'currency': 'USD',
            'opened_date': row['account_opened'],
        })
    accounts_df = pd.DataFrame(accounts_rows)
    print(f"  Generated accounts: {len(accounts_df):,} rows")

    # -- Generate loans (~40% of customers) --------------------------------
    _loan_types = ['home', 'auto', 'personal', 'education', 'business']
    _statuses = ['active', 'active', 'active', 'pending', 'closed']
    _purposes = {
        'home': 'Home purchase', 'auto': 'Vehicle purchase',
        'personal': 'Personal expenses', 'education': 'Education expenses',
        'business': 'Business expansion',
    }
    _collateral = {
        'home': 'real_estate', 'auto': 'vehicle',
        'business': 'business_assets', 'personal': None, 'education': None,
    }
    _interest_range = {
        'home': (3.5, 7.5), 'auto': (4.0, 12.0), 'personal': (6.0, 18.0),
        'education': (3.5, 8.0), 'business': (5.0, 15.0),
    }
    _terms = {
        'home': [180, 240, 360], 'auto': [36, 48, 60, 72],
        'personal': [12, 24, 36, 60], 'education': [120, 180, 240],
        'business': [60, 84, 120],
    }
    _amounts = {
        'home': (100000, 500000), 'auto': (15000, 60000),
        'personal': (5000, 50000), 'education': (10000, 80000),
        'business': (50000, 500000),
    }
    loans_rows = []
    for _, row in customers.iterrows():
        cid = row['customer_id']
        rng = _seeded_rng(cid, '_loan')
        if rng.random() > 0.40:
            continue
        lt = rng.choice(_loan_types)
        status = rng.choice(_statuses)
        lo, hi = _amounts[lt]
        principal = rng.randint(lo, hi)
        term_months = rng.choice(_terms[lt])
        lo_r, hi_r = _interest_range[lt]
        interest_rate = round(rng.uniform(lo_r, hi_r), 2)
        r_m = (interest_rate / 100) / 12
        if r_m > 0:
            mp = principal * r_m * (1 + r_m) ** term_months / ((1 + r_m) ** term_months - 1)
        else:
            mp = principal / term_months
        outstanding_pct = (
            0.0 if status == 'closed' else
            1.0 if status == 'pending' else
            rng.uniform(0.1, 0.95)
        )
        days_ago = rng.randint(30, 3650)
        orig_dt = datetime.date.today() - datetime.timedelta(days=days_ago)
        mat_dt = orig_dt + datetime.timedelta(days=int(term_months * 30.44))
        loan_id = uuid.UUID(int=rng.getrandbits(128)).hex[:8]
        loans_rows.append({
            'id': loan_id,
            'customer_id': cid,
            'loan_type': lt,
            'status': status,
            'purpose': _purposes[lt],
            'notes': '',
            'amount_cents': principal * 100,
            'outstanding_balance_cents': int(principal * 100 * outstanding_pct),
            'interest_rate': interest_rate,
            'term_months': term_months,
            'monthly_payment_cents': int(mp * 100),
            'collateral': _collateral[lt],
            'origination_date': str(orig_dt),
            'maturity_date': str(mat_dt),
            'created_at': str(orig_dt) + 'T00:00:00',
        })
    loans_df = pd.DataFrame(loans_rows) if loans_rows else pd.DataFrame()
    print(f"  Generated loans: {len(loans_df):,} rows")

    tables = {
        "customers": customers_for_db,
        "transactions": transactions,
        "interactions": interactions,
        "support_tickets": support_tickets,
        "fraud_alerts": fraud_alerts,
        "chat_transcripts": chat_transcripts,
        "complaints": complaints,
        "enriched_transactions": df,
        "accounts": accounts_df,
        "loans": loans_df,
    }

    for table_name, table_df in tables.items():
        if table_df is not None and not table_df.empty:
            table_df.to_sql(table_name, engine, if_exists="replace", index=False)
            print(f"  {table_name}: {len(table_df):,} rows")

    print("\n" + "=" * 60)
    print("ETL complete!")
    print(f"  Tables written: {sum(1 for v in tables.values() if v is not None and not v.empty)}")
    print(f"  Database: {db_url[:40]}...")
    print("=" * 60)
    return df


if __name__ == "__main__":
    run_etl()
