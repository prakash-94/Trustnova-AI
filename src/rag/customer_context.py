"""
Customer Context Retrieval Module.

Given a customer_id, retrieves and merges:
- Structured profile data from SQLite (name, balance, credit score, etc.)
- Last 5 transactions
- Trust score (weighted composite)
- Sentiment trend from interactions
- RAG interaction notes from vector store
- Support ticket history
- Fraud alert history

This is the primary data source for the /customer/summary and /trust/score API endpoints.
"""
import os
from typing import Dict, Optional, List

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")


def get_db_engine():
    """Get SQLAlchemy engine."""
    return create_engine(DATABASE_URL)


def get_customer_profile(customer_id: str) -> Optional[Dict]:
    """Retrieve customer profile from SQLite (includes Phase 2 fields)."""
    engine = get_db_engine()
    query = text("SELECT * FROM customers WHERE customer_id = :cid")
    df = pd.read_sql(query, engine, params={"cid": customer_id})

    if df.empty:
        return None

    row = df.iloc[0]
    return {
        "customer_id": row["customer_id"],
        "name": row["name"],
        "email": row["email"],
        "age": int(row.get("age", 0)),
        "income": float(row.get("income", 0)),
        "credit_score": int(row["credit_score"]),
        "risk_level": str(row.get("risk_level", "Unknown")),
        "account_type": str(row.get("account_type", "checking")),
        "balance": float(row["balance"]),
        "account_opened": str(row.get("account_opened", "")),
        "account_age_days": int(row["account_age_days"]),
        "sentiment_avg": float(row["sentiment_avg"]),
        "created_at": str(row["created_at"]),
    }


def get_last_n_transactions(customer_id: str, n: int = 5) -> List[Dict]:
    """Retrieve last N transactions for a customer."""
    engine = get_db_engine()
    query = text("""
        SELECT transaction_id, amount, merchant, category, hour, is_weekend, 
               geo_mismatch, device_new, is_fraud, location, timestamp 
        FROM transactions 
        WHERE customer_id = :cid 
        ORDER BY timestamp DESC 
        LIMIT :n
    """)
    df = pd.read_sql(query, engine, params={"cid": customer_id, "n": n})
    return df.to_dict(orient="records")


def get_sentiment_trend(customer_id: str) -> Dict:
    """Get sentiment trend from interactions."""
    engine = get_db_engine()
    query = text("""
        SELECT sentiment_label, sentiment_score, channel, topic, timestamp, banker_note
        FROM interactions 
        WHERE customer_id = :cid 
        ORDER BY timestamp DESC
    """)
    df = pd.read_sql(query, engine, params={"cid": customer_id})

    if df.empty:
        return {
            "total_interactions": 0,
            "avg_sentiment": 0.0,
            "sentiment_distribution": {},
            "recent_notes": [],
        }

    return {
        "total_interactions": len(df),
        "avg_sentiment": round(df["sentiment_score"].mean(), 3),
        "sentiment_distribution": df["sentiment_label"].value_counts().to_dict(),
        "recent_notes": df.head(3)[["banker_note", "sentiment_label", "channel", "topic", "timestamp"]].to_dict(orient="records"),
    }


def get_support_tickets(customer_id: str) -> Dict:
    """Get support ticket summary for a customer."""
    engine = get_db_engine()
    try:
        query = text("""
            SELECT ticket_id, issue, sentiment, resolution, channel, timestamp
            FROM support_tickets 
            WHERE customer_id = :cid 
            ORDER BY timestamp DESC
        """)
        df = pd.read_sql(query, engine, params={"cid": customer_id})
    except Exception:
        return {"total_tickets": 0, "issues": {}, "recent_tickets": []}

    if df.empty:
        return {"total_tickets": 0, "issues": {}, "recent_tickets": []}

    return {
        "total_tickets": len(df),
        "issues": df["issue"].value_counts().to_dict(),
        "avg_sentiment": round(df["sentiment"].mean(), 3),
        "recent_tickets": df.head(3)[["issue", "sentiment", "resolution", "timestamp"]].to_dict(orient="records"),
    }


def get_fraud_history(customer_id: str) -> Dict:
    """Get fraud alert history for a customer."""
    engine = get_db_engine()
    try:
        query = text("""
            SELECT alert_id, risk_score, reason, status, timestamp
            FROM fraud_alerts 
            WHERE customer_id = :cid 
            ORDER BY timestamp DESC
        """)
        df = pd.read_sql(query, engine, params={"cid": customer_id})
    except Exception:
        return {"total_alerts": 0, "status_distribution": {}, "recent_alerts": []}

    if df.empty:
        return {"total_alerts": 0, "status_distribution": {}, "recent_alerts": []}

    return {
        "total_alerts": len(df),
        "status_distribution": df["status"].value_counts().to_dict(),
        "avg_risk_score": round(df["risk_score"].mean(), 3),
        "recent_alerts": df.head(3)[["risk_score", "reason", "status", "timestamp"]].to_dict(orient="records"),
    }


def get_trust_score(customer_id: str) -> Dict:
    """
    Calculate weighted trust score for a customer.

    Components:
    - Credit score:    30% (0-30 points)
    - Account age:     20% (0-20 points, max at 10 years)
    - Balance:         20% (0-20 points, max at $100k)
    - Sentiment:       15% (0-15 points)
    - Fraud history:   15% (0-15 points, deducted for fraud)
    """
    profile = get_customer_profile(customer_id)
    if not profile:
        return {"score": 0, "tier": "Unknown", "note": "Customer not found"}

    # Credit score component (0-30)
    credit_component = (profile["credit_score"] - 300) / 550 * 30

    # Account age component (0-20, max at 10 years)
    age_component = min(profile["account_age_days"] / 3650, 1.0) * 20

    # Balance component (0-20, max at $100k)
    balance_component = min(profile["balance"] / 100000, 1.0) * 20

    # Sentiment component (0-15)
    sentiment_component = (profile["sentiment_avg"] + 1) / 2 * 15

    # Fraud history component (0-15, reduced by fraud alerts)
    fraud = get_fraud_history(customer_id)
    fraud_count = fraud["total_alerts"]
    false_positive_count = fraud.get("status_distribution", {}).get("false_positive", 0)
    real_fraud_count = fraud_count - false_positive_count
    fraud_component = max(0, 15 - real_fraud_count * 5)  # -5 per real fraud alert

    score = round(credit_component + age_component + balance_component + sentiment_component + fraud_component, 1)
    score = max(0, min(100, score))

    if score >= 71:
        tier = "Trusted"
    elif score >= 41:
        tier = "Moderate"
    else:
        tier = "High Risk"

    return {
        "score": score,
        "tier": tier,
        "components": {
            "credit_score": round(credit_component, 1),
            "account_age": round(age_component, 1),
            "balance": round(balance_component, 1),
            "sentiment": round(sentiment_component, 1),
            "fraud_history": round(fraud_component, 1),
        },
    }


def get_rag_notes(customer_id: str, top_k: int = 3) -> List[Dict]:
    """Retrieve relevant interaction notes from vector store for a customer."""
    try:
        from src.rag.vector_store import similarity_search_interactions

        results = similarity_search_interactions(
            query=f"Customer {customer_id} interaction notes and history",
            k=top_k,
            filter_dict={"customer_id": customer_id},
        )

        notes = []
        for doc in results:
            notes.append({
                "note": doc.page_content[:300],
                "source": doc.metadata.get("source", ""),
                "sentiment": doc.metadata.get("sentiment_label", ""),
                "timestamp": doc.metadata.get("timestamp", ""),
            })
        return notes

    except Exception as e:
        return [{"note": f"RAG notes unavailable: {str(e)}", "source": "error"}]


def get_risk_profile(customer_id: str) -> Dict:
    """Get structured risk profile for a customer (Phase 7)."""
    try:
        from src.intelligence.risk_profile import RiskProfiler
        profiler = RiskProfiler()
        return profiler.generate_risk_profile(customer_id)
    except Exception as e:
        return {"error": f"Risk profile unavailable: {str(e)}"}


def get_recommendations(customer_id: str) -> List[Dict]:
    """Get product recommendations for a customer (Phase 7)."""
    try:
        from src.intelligence.recommender import ProductRecommender
        recommender = ProductRecommender()
        return recommender.recommend(customer_id)
    except Exception as e:
        return [{"error": f"Recommendations unavailable: {str(e)}"}]


def get_full_customer_context(customer_id: str) -> Dict:
    """
    Get the complete customer context - merging structured SQL data
    and unstructured RAG interaction notes.

    This is the main function used by the banker dashboard and chat system.
    Includes Phase 7: risk profiles and product recommendations.
    """
    profile = get_customer_profile(customer_id)
    if not profile:
        return {"error": f"Customer {customer_id} not found"}

    transactions = get_last_n_transactions(customer_id)
    sentiment = get_sentiment_trend(customer_id)
    trust_score = get_trust_score(customer_id)
    support = get_support_tickets(customer_id)
    fraud = get_fraud_history(customer_id)
    rag_notes = get_rag_notes(customer_id)
    risk_profile = get_risk_profile(customer_id)
    recommendations = get_recommendations(customer_id)

    return {
        "profile": profile,
        "last_5_transactions": transactions,
        "trust_score": trust_score,
        "sentiment_trend": sentiment,
        "support_tickets": support,
        "fraud_history": fraud,
        "rag_interaction_notes": rag_notes,
        "risk_profile": risk_profile,
        "recommendations": recommendations,
    }


def format_customer_context(context: Dict) -> str:
    """Format customer context as a readable string for the banker / LLM prompt."""
    if "error" in context:
        return f"Error: {context['error']}"

    p = context["profile"]
    ts = context["trust_score"]

    output = f"""
{'='*60}
CUSTOMER PROFILE - Pre-Appointment Brief
{'='*60}

Name:           {p['name']}
Customer ID:    {p['customer_id']}
Email:          {p['email']}
Age:            {p['age']}
Income:         ${p['income']:,.2f}
Account Type:   {p['account_type']}
Risk Level:     {p['risk_level']}
Balance:        ${p['balance']:,.2f}
Credit Score:   {p['credit_score']}
Account Age:    {p['account_age_days']} days
Member Since:   {p['account_opened']}

{'─'*60}
TRUST SCORE: {ts['score']}/100 - {ts['tier']}
  Credit:       {ts['components']['credit_score']}/30
  Account Age:  {ts['components']['account_age']}/20
  Balance:      {ts['components']['balance']}/20
  Sentiment:    {ts['components']['sentiment']}/15
  Fraud Hist:   {ts['components']['fraud_history']}/15

{'─'*60}
RECENT TRANSACTIONS:
"""
    for i, txn in enumerate(context["last_5_transactions"], 1):
        fraud_flag = " [!FRAUD]" if txn.get("is_fraud") else ""
        merchant = txn.get("merchant", txn.get("category", "unknown"))
        output += f"  {i}. ${txn['amount']:.2f} - {merchant} - {txn['timestamp']}{fraud_flag}\n"

    output += f"\n{'─'*60}\n"
    output += f"SENTIMENT TREND:\n"
    s = context["sentiment_trend"]
    output += f"  Total Interactions: {s['total_interactions']}\n"
    output += f"  Avg Sentiment:      {s['avg_sentiment']}\n"
    if s.get("sentiment_distribution"):
        output += f"  Distribution:       {s['sentiment_distribution']}\n"
    output += f"\n  Recent Notes:\n"
    for note in s.get("recent_notes", []):
        output += f"    • [{note['sentiment_label']}] {str(note['banker_note'])[:80]}...\n"

    # Support tickets
    st = context.get("support_tickets", {})
    if st.get("total_tickets", 0) > 0:
        output += f"\n{'─'*60}\n"
        output += f"SUPPORT TICKETS: {st['total_tickets']} total\n"
        output += f"  Issues: {st.get('issues', {})}\n"

    # Fraud history
    fh = context.get("fraud_history", {})
    if fh.get("total_alerts", 0) > 0:
        output += f"\n{'─'*60}\n"
        output += f"FRAUD ALERTS: {fh['total_alerts']} total\n"
        output += f"  Status: {fh.get('status_distribution', {})}\n"

    # Risk profile (Phase 7)
    rp = context.get("risk_profile", {})
    if rp and "error" not in rp:
        output += f"\n{'─'*60}\n"
        output += f"RISK PROFILE:\n"
        output += f"  Risk Level:    {rp.get('risk_level', 'Unknown')}\n"
        output += f"  Sentiment:     {rp.get('sentiment', 'Unknown')}\n"
        output += f"  Fraud Risk:    {rp.get('fraud_risk', 'Unknown')}\n"
        output += f"  Retention:     {rp.get('retention_probability', 0):.0%}\n"
        factors = rp.get('risk_factors', [])
        if factors:
            output += f"  Risk Factors:\n"
            for f in factors:
                output += f"    • {f}\n"

    # Product recommendations (Phase 7)
    recs = context.get("recommendations", [])
    if recs and not any("error" in r for r in recs):
        output += f"\n{'─'*60}\n"
        output += f"PRODUCT RECOMMENDATIONS:\n"
        for i, rec in enumerate(recs, 1):
            output += f"  [{i}] {rec['product']} ({rec.get('category', '')})\n"
            output += f"      {rec['reason']}\n"

    output += f"\n{'='*60}\n"
    return output


# --- CLI ---
if __name__ == "__main__":
    import sys

    engine = get_db_engine()
    sample = pd.read_sql("SELECT customer_id FROM customers LIMIT 1", engine)

    if len(sys.argv) > 1:
        cid = sys.argv[1]
    elif not sample.empty:
        cid = sample.iloc[0]["customer_id"]
        print(f"Using sample customer: {cid}")
    else:
        print("No customers found in database.")
        sys.exit(1)

    context = get_full_customer_context(cid)
    print(format_customer_context(context))
