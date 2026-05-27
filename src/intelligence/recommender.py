"""
Product Recommendation Engine — Phase 7.

Rule-based recommendation logic for banking product suggestions.
Analyzes customer profile, transaction patterns, and demographics
to generate top 3 product recommendations with reason strings.

Rules (from TODO.md):
  - High balance + good credit → Premium Savings / Investment Products
  - Frequent traveler (geo-diverse transactions) → Travel Rewards Credit Card
  - Young age + regular income → Starter Investment / HYSA
  - Additional rules for business accounts, retention, credit leverage

Returns top 3 recommendations sorted by confidence score.
"""
import os
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")


# ──────────────────────────────────────────────────────────────
# Product Catalog
# ──────────────────────────────────────────────────────────────

PRODUCTS = {
    "premium_savings": {
        "name": "Premium Savings Account",
        "category": "Savings & Deposits",
        "description": "High-yield savings with 4.25% APY for balances above $25,000",
    },
    "investment_portfolio": {
        "name": "Managed Investment Portfolio",
        "category": "Wealth Management",
        "description": "Professionally managed diversified portfolio with quarterly rebalancing",
    },
    "travel_credit_card": {
        "name": "Citizens Travel Rewards Card",
        "category": "Credit Cards",
        "description": "3x points on travel & dining, no foreign transaction fees, $200 travel credit",
    },
    "starter_investment": {
        "name": "Young Investor Starter Account",
        "category": "Wealth Management",
        "description": "Low-minimum investment account with automated recurring investments",
    },
    "hysa": {
        "name": "High-Yield Savings Account",
        "category": "Savings & Deposits",
        "description": "Online savings account with 4.50% APY, no minimum balance required",
    },
    "personal_loc": {
        "name": "Personal Line of Credit",
        "category": "Lending",
        "description": "Flexible credit line from $5,000-$50,000 with competitive rates",
    },
    "business_credit_card": {
        "name": "Business Rewards Card",
        "category": "Business Banking",
        "description": "2% cashback on all business purchases, expense tracking tools",
    },
    "business_loc": {
        "name": "Business Line of Credit",
        "category": "Business Banking",
        "description": "Working capital line from $10,000-$250,000 for business needs",
    },
    "dedicated_rm": {
        "name": "Dedicated Relationship Manager",
        "category": "Service Upgrade",
        "description": "Personal banker assigned for priority support and financial planning",
    },
    "mortgage_refi": {
        "name": "Mortgage Refinance",
        "category": "Lending",
        "description": "Refinance at today's competitive rates with reduced closing costs",
    },
    "cd_ladder": {
        "name": "CD Ladder Strategy",
        "category": "Savings & Deposits",
        "description": "Structured CD portfolio with staggered maturities for optimal yield",
    },
}


class ProductRecommender:
    """
    Rule-based product recommendation engine for banking customers.

    Analyzes customer demographics, account data, transaction patterns,
    and sentiment to generate personalized product recommendations.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)

    def recommend(self, customer_id: str, max_recommendations: int = 3) -> List[Dict]:
        """
        Generate product recommendations for a customer.

        Args:
            customer_id: The customer ID
            max_recommendations: Maximum number of recommendations (default 3)

        Returns:
            List of dicts with product, reason, confidence, and category
        """
        # Gather customer data
        customer = self._get_customer_data(customer_id)
        if customer is None:
            return []

        transaction_stats = self._get_transaction_stats(customer_id)
        sentiment_data = self._get_sentiment_data(customer_id)
        ticket_count = self._get_ticket_count(customer_id)

        # Apply all recommendation rules
        candidates = []

        candidates.extend(self._rule_high_balance_good_credit(customer))
        candidates.extend(self._rule_frequent_traveler(customer, transaction_stats))
        candidates.extend(self._rule_young_professional(customer))
        candidates.extend(self._rule_retention_intervention(customer, sentiment_data, ticket_count))
        candidates.extend(self._rule_credit_leverage(customer))
        candidates.extend(self._rule_business_account(customer))
        candidates.extend(self._rule_high_balance_stable(customer))
        candidates.extend(self._rule_mortgage_opportunity(customer))

        # Deduplicate by product key, keeping highest confidence
        seen = {}
        for rec in candidates:
            key = rec["product"]
            if key not in seen or rec["confidence"] > seen[key]["confidence"]:
                seen[key] = rec

        # Sort by confidence and return top N
        sorted_recs = sorted(seen.values(), key=lambda x: x["confidence"], reverse=True)
        return sorted_recs[:max_recommendations]

    # ==================================================================
    # Recommendation Rules
    # ==================================================================

    def _rule_high_balance_good_credit(self, customer: Dict) -> List[Dict]:
        """High balance ($50k+) + credit ≥ 750 → Premium Savings / Investment."""
        recs = []
        balance = float(customer.get("balance", 0))
        credit = int(customer.get("credit_score", 0))

        if balance >= 50000 and credit >= 750:
            recs.append({
                "product": "Managed Investment Portfolio",
                "product_key": "investment_portfolio",
                "category": "Wealth Management",
                "reason": (
                    f"With a balance of ${balance:,.0f} and excellent credit ({credit}), "
                    f"a managed investment portfolio can help grow your wealth with "
                    f"professional oversight."
                ),
                "confidence": 0.92,
            })
            recs.append({
                "product": "Premium Savings Account",
                "product_key": "premium_savings",
                "category": "Savings & Deposits",
                "reason": (
                    f"Your ${balance:,.0f} balance qualifies for our Premium Savings "
                    f"with 4.25% APY — significantly higher than standard rates."
                ),
                "confidence": 0.88,
            })
        elif balance >= 25000 and credit >= 700:
            recs.append({
                "product": "Premium Savings Account",
                "product_key": "premium_savings",
                "category": "Savings & Deposits",
                "reason": (
                    f"Your ${balance:,.0f} balance qualifies for Premium Savings "
                    f"with enhanced rates. Good credit ({credit}) supports future "
                    f"investment opportunities."
                ),
                "confidence": 0.78,
            })

        return recs

    def _rule_frequent_traveler(self, customer: Dict, txn_stats: Dict) -> List[Dict]:
        """Geo-diverse transactions (3+ unique locations) → Travel Credit Card."""
        recs = []
        unique_locations = txn_stats.get("unique_locations", 0)

        if unique_locations >= 3:
            recs.append({
                "product": "Citizens Travel Rewards Card",
                "product_key": "travel_credit_card",
                "category": "Credit Cards",
                "reason": (
                    f"Your transactions span {unique_locations} different locations, "
                    f"indicating frequent travel. Earn 3x points on travel & dining "
                    f"with no foreign transaction fees."
                ),
                "confidence": 0.85,
            })

        return recs

    def _rule_young_professional(self, customer: Dict) -> List[Dict]:
        """Age ≤ 35 + income ≥ $40k → Starter Investment / HYSA."""
        recs = []
        age = int(customer.get("age", 0))
        income = float(customer.get("income", 0))

        if age <= 35 and income >= 40000:
            recs.append({
                "product": "Young Investor Starter Account",
                "product_key": "starter_investment",
                "category": "Wealth Management",
                "reason": (
                    f"At {age} with a ${income:,.0f} income, starting to invest early "
                    f"can significantly grow your wealth through compound returns."
                ),
                "confidence": 0.83,
            })
            recs.append({
                "product": "High-Yield Savings Account",
                "product_key": "hysa",
                "category": "Savings & Deposits",
                "reason": (
                    f"Build your emergency fund with 4.50% APY. At your career stage, "
                    f"a strong savings foundation supports future financial goals."
                ),
                "confidence": 0.80,
            })

        return recs

    def _rule_retention_intervention(self, customer: Dict, sentiment: Dict, ticket_count: int) -> List[Dict]:
        """High tickets + negative sentiment → Dedicated Relationship Manager."""
        recs = []
        avg_sentiment = float(sentiment.get("avg_sentiment", 0))

        if ticket_count >= 3 and avg_sentiment < -0.1:
            recs.append({
                "product": "Dedicated Relationship Manager",
                "product_key": "dedicated_rm",
                "category": "Service Upgrade",
                "reason": (
                    f"With {ticket_count} support tickets and below-average satisfaction, "
                    f"a dedicated relationship manager can provide personalized attention "
                    f"and resolve ongoing concerns."
                ),
                "confidence": 0.90,
            })

        return recs

    def _rule_credit_leverage(self, customer: Dict) -> List[Dict]:
        """Low balance + good credit → Personal Line of Credit."""
        recs = []
        balance = float(customer.get("balance", 0))
        credit = int(customer.get("credit_score", 0))

        if balance < 10000 and credit >= 700:
            recs.append({
                "product": "Personal Line of Credit",
                "product_key": "personal_loc",
                "category": "Lending",
                "reason": (
                    f"Your strong credit score ({credit}) qualifies you for a "
                    f"personal line of credit, providing flexible access to funds "
                    f"at competitive rates."
                ),
                "confidence": 0.72,
            })

        return recs

    def _rule_business_account(self, customer: Dict) -> List[Dict]:
        """Business account type → Business products."""
        recs = []
        account_type = str(customer.get("account_type", "")).lower()

        if "business" in account_type:
            recs.append({
                "product": "Business Rewards Card",
                "product_key": "business_credit_card",
                "category": "Business Banking",
                "reason": (
                    "As a business account holder, earn 2% cashback on all business "
                    "purchases with integrated expense tracking tools."
                ),
                "confidence": 0.82,
            })
            recs.append({
                "product": "Business Line of Credit",
                "product_key": "business_loc",
                "category": "Business Banking",
                "reason": (
                    "Access working capital from $10,000-$250,000 to manage "
                    "cash flow and fund business growth opportunities."
                ),
                "confidence": 0.75,
            })

        return recs

    def _rule_high_balance_stable(self, customer: Dict) -> List[Dict]:
        """High balance ($100k+) → CD Ladder Strategy."""
        recs = []
        balance = float(customer.get("balance", 0))

        if balance >= 100000:
            recs.append({
                "product": "CD Ladder Strategy",
                "product_key": "cd_ladder",
                "category": "Savings & Deposits",
                "reason": (
                    f"With ${balance:,.0f} in deposits, a CD ladder strategy can "
                    f"lock in higher rates while maintaining periodic liquidity."
                ),
                "confidence": 0.76,
            })

        return recs

    def _rule_mortgage_opportunity(self, customer: Dict) -> List[Dict]:
        """Good credit + high income + no existing mortgage → Mortgage."""
        recs = []
        credit = int(customer.get("credit_score", 0))
        income = float(customer.get("income", 0))
        age = int(customer.get("age", 0))

        if credit >= 700 and income >= 80000 and 28 <= age <= 50:
            recs.append({
                "product": "Mortgage Refinance",
                "product_key": "mortgage_refi",
                "category": "Lending",
                "reason": (
                    f"With a credit score of {credit} and ${income:,.0f} income, "
                    f"you qualify for competitive mortgage rates. Explore homeownership "
                    f"or refinancing options."
                ),
                "confidence": 0.65,
            })

        return recs

    # ==================================================================
    # Data Fetchers
    # ==================================================================

    def _get_customer_data(self, customer_id: str) -> Optional[Dict]:
        """Fetch customer profile from DB."""
        query = text("SELECT * FROM customers WHERE customer_id = :cid")
        df = pd.read_sql(query, self.engine, params={"cid": customer_id})
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def _get_transaction_stats(self, customer_id: str) -> Dict:
        """Get transaction statistics for recommendation rules."""
        query = text("""
            SELECT 
                COUNT(*) as total_transactions,
                AVG(amount) as avg_amount,
                MAX(amount) as max_amount,
                COUNT(DISTINCT location) as unique_locations
            FROM transactions
            WHERE customer_id = :cid
        """)
        df = pd.read_sql(query, self.engine, params={"cid": customer_id})
        if df.empty:
            return {"total_transactions": 0, "avg_amount": 0, "max_amount": 0, "unique_locations": 0}
        row = df.iloc[0]
        return {
            "total_transactions": int(row["total_transactions"]),
            "avg_amount": float(row.get("avg_amount", 0) or 0),
            "max_amount": float(row.get("max_amount", 0) or 0),
            "unique_locations": int(row.get("unique_locations", 0) or 0),
        }

    def _get_sentiment_data(self, customer_id: str) -> Dict:
        """Get sentiment summary for recommendation rules."""
        query = text("""
            SELECT AVG(sentiment_score) as avg_sentiment
            FROM interactions
            WHERE customer_id = :cid
        """)
        df = pd.read_sql(query, self.engine, params={"cid": customer_id})
        if df.empty:
            return {"avg_sentiment": 0.0}
        return {"avg_sentiment": float(df.iloc[0].get("avg_sentiment", 0) or 0)}

    def _get_ticket_count(self, customer_id: str) -> int:
        """Get support ticket count for a customer."""
        query = text("SELECT COUNT(*) as cnt FROM support_tickets WHERE customer_id = :cid")
        df = pd.read_sql(query, self.engine, params={"cid": customer_id})
        return int(df.iloc[0]["cnt"]) if not df.empty else 0


# --- CLI ---
if __name__ == "__main__":
    recommender = ProductRecommender()

    print("=" * 60)
    print("Product Recommendation Engine — Phase 7")
    print("=" * 60)

    # Get sample customers
    engine = create_engine(DATABASE_URL)
    customers = pd.read_sql("SELECT customer_id, name, age, income, credit_score, "
                            "balance, account_type FROM customers LIMIT 10", engine)

    for _, c in customers.iterrows():
        cid = c["customer_id"]
        recs = recommender.recommend(cid)

        print(f"\n{'-' * 60}")
        print(f"Customer: {c['name']} ({cid})")
        print(f"  Age: {c['age']} | Income: ${c['income']:,.0f} | "
              f"Credit: {c['credit_score']} | Balance: ${c['balance']:,.0f} | "
              f"Type: {c['account_type']}")

        if not recs:
            print("  No recommendations at this time.")
            continue

        for i, rec in enumerate(recs, 1):
            print(f"\n  [{i}] {rec['product']} ({rec['category']})")
            print(f"      Confidence: {rec['confidence']:.0%}")
            print(f"      Reason: {rec['reason']}")

    print(f"\n{'=' * 60}")
