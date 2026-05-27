"""
Data Validation for the Banking AI System.

Performs automated checks on all generated datasets:
  - File existence and row counts
  - Null value detection in critical columns
  - Fraud rate range (0.5% - 5%)
  - Credit score range (300-850)
  - Positive transaction amounts
  - Row count consistency between raw and processed data
  - Referential integrity (customer IDs in transactions exist in customers)
"""
import pandas as pd
import os
import sys


def validate_data():
    """Run all validation checks on the banking datasets."""
    print("=" * 60)
    print("Banking AI — Data Validation")
    print("=" * 60)

    errors = []
    warnings = []

    # ─── 1. Check Raw Files Exist ───
    print("\n[1/6] Checking raw file existence...")
    raw_files = {
        "customers.csv": {"min_rows": 900, "required": True},
        "transactions.csv": {"min_rows": 14000, "required": True},
        "interactions.csv": {"min_rows": 4000, "required": True},
        "support_tickets.csv": {"min_rows": 2500, "required": True},
        "fraud_alerts.csv": {"min_rows": 100, "required": True},
        "chat_transcripts.csv": {"min_rows": 400, "required": True},
        "complaints.csv": {"min_rows": 900, "required": True},
    }

    for filename, spec in raw_files.items():
        path = f"data/raw/{filename}"
        if not os.path.exists(path):
            msg = f"{filename} missing from data/raw/"
            if spec["required"]:
                errors.append(msg)
                print(f"  FAIL: {msg}")
            else:
                warnings.append(msg)
                print(f"  WARN: {msg}")
            continue

        df = pd.read_csv(path)
        row_count = len(df)

        if row_count < spec["min_rows"]:
            warnings.append(f"{filename}: only {row_count} rows (expected {spec['min_rows']}+)")
            print(f"  WARN: {filename}: {row_count} rows (expected {spec['min_rows']}+)")
        else:
            print(f"  PASS: {filename}: {row_count:,} rows")

        null_count = df.isnull().sum().sum()
        if null_count > 0:
            null_cols = df.columns[df.isnull().any()].tolist()
            warnings.append(f"{filename}: {null_count} null values in columns {null_cols}")

    # ─── 2. Banking Documents ───
    print("\n[2/6] Checking banking documents...")
    docs_dir = "data/raw/banking_docs"
    if os.path.exists(docs_dir):
        doc_count = len([f for f in os.listdir(docs_dir) if f.endswith((".txt", ".pdf"))])
        if doc_count >= 10:
            print(f"  PASS: {doc_count} banking documents found")
        else:
            warnings.append(f"Only {doc_count} documents (expected 10+)")
            print(f"  WARN: {doc_count} documents (expected 10+)")
    else:
        errors.append("Banking docs directory missing")
        print(f"  FAIL: {docs_dir}/ not found")

    # ─── 3. Validate Processed Data ───
    print("\n[3/6] Validating processed data...")
    processed_path = "data/processed/enriched_transactions.csv"
    if not os.path.exists(processed_path):
        errors.append("enriched_transactions.csv missing from data/processed/")
        print(f"  FAIL: {processed_path} not found")
    else:
        df = pd.read_csv(processed_path)
        print(f"  Loaded: {len(df):,} rows x {len(df.columns)} columns")

        # Critical columns must not have nulls
        critical_cols = ["transaction_id", "customer_id", "amount", "is_fraud"]
        for col in critical_cols:
            if col in df.columns and df[col].isnull().any():
                errors.append(f"Null values in critical column: {col}")
                print(f"  FAIL: Nulls in {col}")
            elif col in df.columns:
                print(f"  PASS: {col} — no nulls")

        # Positive amounts
        if "amount" in df.columns:
            if (df["amount"] <= 0).any():
                errors.append("Negative or zero amounts found")
                print(f"  FAIL: Non-positive amounts found")
            else:
                print(f"  PASS: All amounts positive")

        # Fraud rate between 0.5% and 5%
        if "is_fraud" in df.columns:
            fraud_rate = df["is_fraud"].mean()
            if 0.005 <= fraud_rate <= 0.05:
                print(f"  PASS: Fraud rate {fraud_rate:.2%} (within 0.5%-5%)")
            else:
                errors.append(f"Fraud rate {fraud_rate:.2%} out of expected range")
                print(f"  FAIL: Fraud rate {fraud_rate:.2%} (expected 0.5%-5%)")

        # Credit score range
        if "credit_score" in df.columns:
            min_cs = df["credit_score"].min()
            max_cs = df["credit_score"].max()
            if 300 <= min_cs and max_cs <= 850:
                print(f"  PASS: Credit scores {min_cs}-{max_cs} (within 300-850)")
            else:
                errors.append(f"Credit scores out of range: {min_cs}-{max_cs}")
                print(f"  FAIL: Credit scores {min_cs}-{max_cs} (expected 300-850)")

    # ─── 4. Row Count Consistency ───
    print("\n[4/6] Checking row count consistency...")
    if os.path.exists("data/raw/transactions.csv") and os.path.exists(processed_path):
        raw_txns = pd.read_csv("data/raw/transactions.csv")
        processed_txns = pd.read_csv(processed_path)
        if len(raw_txns) == len(processed_txns):
            print(f"  PASS: Raw ({len(raw_txns):,}) == Processed ({len(processed_txns):,})")
        else:
            errors.append(f"Row count mismatch: Raw ({len(raw_txns):,}) vs Processed ({len(processed_txns):,})")
            print(f"  FAIL: Raw ({len(raw_txns):,}) != Processed ({len(processed_txns):,})")

    # ─── 5. Referential Integrity ───
    print("\n[5/6] Checking referential integrity...")
    if os.path.exists("data/raw/customers.csv") and os.path.exists("data/raw/transactions.csv"):
        customers = pd.read_csv("data/raw/customers.csv")
        transactions = pd.read_csv("data/raw/transactions.csv")
        customer_ids = set(customers["customer_id"])
        txn_customer_ids = set(transactions["customer_id"])

        orphan_ids = txn_customer_ids - customer_ids
        if len(orphan_ids) == 0:
            print(f"  PASS: All transaction customer_ids exist in customers table")
        else:
            errors.append(f"{len(orphan_ids)} orphaned customer_ids in transactions")
            print(f"  FAIL: {len(orphan_ids)} orphaned customer_ids")

    # ─── 6. SQLite Database ───
    print("\n[6/6] Checking SQLite database...")
    if os.path.exists("banking.db"):
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite:///banking.db")
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            table_names = [t[0] for t in tables]
            print(f"  Tables found: {table_names}")

            expected_tables = ["customers", "transactions", "interactions", "enriched_transactions"]
            for t in expected_tables:
                if t in table_names:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                    print(f"  PASS: {t} — {count:,} rows")
                else:
                    warnings.append(f"Table '{t}' not found in banking.db")
                    print(f"  WARN: Table '{t}' missing")
    else:
        errors.append("banking.db not found")
        print(f"  FAIL: banking.db not found")

    # ─── Summary ───
    print("\n" + "=" * 60)
    if errors:
        print(f"VALIDATION FAILED — {len(errors)} error(s), {len(warnings)} warning(s)")
        for e in errors:
            print(f"  [ERROR] {e}")
        for w in warnings:
            print(f"  [WARN]  {w}")
        return False
    elif warnings:
        print(f"VALIDATION PASSED with {len(warnings)} warning(s)")
        for w in warnings:
            print(f"  [WARN]  {w}")
        return True
    else:
        print("VALIDATION PASSED — All checks successful!")
        return True


if __name__ == "__main__":
    result = validate_data()
    sys.exit(0 if result else 1)
