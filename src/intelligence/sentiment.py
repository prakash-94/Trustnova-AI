"""
Sentiment Analysis Pipeline — Phase 7.

Provides:
  - Batch processing of support tickets, complaints, and interactions
  - Unified `sentiment_scores` table storing per-item sentiment
  - Monthly trend computation per customer (last 6 months)
  - Declining sentiment alert detection (2+ consecutive declining months)
  - Manager alert generation stored in `alerts` table

Data sources (already in banking.db):
  - interactions: 4,500 rows with sentiment_label + sentiment_score
  - support_tickets: 3,000 rows with sentiment column
  - complaints: 1,200 rows with sentiment_score
  - chat_transcripts: 600 rows with sentiment_score
"""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text
from src.models.database import auto_pk
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")


class SentimentAnalyzer:
    """
    Batch sentiment analysis pipeline for banking customer intelligence.

    Processes all historical interaction data (support tickets, complaints,
    interactions, chat transcripts), stores unified scores in sentiment_scores
    table, computes monthly trends, and generates alerts for declining sentiment.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create required tables if they don't exist."""
        with self.engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS sentiment_scores (
                    id {auto_pk},
                    customer_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT,
                    sentiment_label TEXT NOT NULL,
                    sentiment_score REAL NOT NULL,
                    key_issue TEXT,
                    timestamp TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS alerts (
                    id {auto_pk},
                    customer_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT NOT NULL
                )
            """))
            conn.commit()

    # ==================================================================
    # Batch Processing
    # ==================================================================

    def batch_process_interactions(self) -> int:
        """Process all interaction records into sentiment_scores table."""
        df = pd.read_sql(
            "SELECT interaction_id, customer_id, sentiment_label, "
            "sentiment_score, topic, timestamp FROM interactions",
            self.engine,
        )
        if df.empty:
            return 0

        records = []
        for _, row in df.iterrows():
            records.append({
                "customer_id": row["customer_id"],
                "source_type": "interaction",
                "source_id": str(row["interaction_id"]),
                "sentiment_label": row["sentiment_label"],
                "sentiment_score": float(row["sentiment_score"]),
                "key_issue": str(row.get("topic", "")),
                "timestamp": str(row["timestamp"]),
                "processed_at": datetime.now().isoformat(),
            })

        self._insert_sentiment_records(records)
        return len(records)

    def batch_process_support_tickets(self) -> int:
        """Process all support tickets into sentiment_scores table."""
        df = pd.read_sql(
            "SELECT ticket_id, customer_id, issue, sentiment, timestamp "
            "FROM support_tickets",
            self.engine,
        )
        if df.empty:
            return 0

        records = []
        for _, row in df.iterrows():
            score = float(row["sentiment"])
            label = self._score_to_label(score)
            records.append({
                "customer_id": row["customer_id"],
                "source_type": "support_ticket",
                "source_id": str(row["ticket_id"]),
                "sentiment_label": label,
                "sentiment_score": score,
                "key_issue": str(row.get("issue", "")),
                "timestamp": str(row["timestamp"]),
                "processed_at": datetime.now().isoformat(),
            })

        self._insert_sentiment_records(records)
        return len(records)

    def batch_process_complaints(self) -> int:
        """Process all complaint records into sentiment_scores table."""
        df = pd.read_sql(
            "SELECT complaint_id, customer_id, category, sentiment_score, timestamp "
            "FROM complaints",
            self.engine,
        )
        if df.empty:
            return 0

        records = []
        for _, row in df.iterrows():
            score = float(row["sentiment_score"])
            label = self._score_to_label(score)
            records.append({
                "customer_id": row["customer_id"],
                "source_type": "complaint",
                "source_id": str(row["complaint_id"]),
                "sentiment_label": label,
                "sentiment_score": score,
                "key_issue": str(row.get("category", "")),
                "timestamp": str(row["timestamp"]),
                "processed_at": datetime.now().isoformat(),
            })

        self._insert_sentiment_records(records)
        return len(records)

    def batch_process_chat_transcripts(self) -> int:
        """Process all chat transcripts into sentiment_scores table."""
        df = pd.read_sql(
            "SELECT transcript_id, customer_id, topic, sentiment_score, timestamp "
            "FROM chat_transcripts",
            self.engine,
        )
        if df.empty:
            return 0

        records = []
        for _, row in df.iterrows():
            score = float(row["sentiment_score"])
            label = self._score_to_label(score)
            records.append({
                "customer_id": row["customer_id"],
                "source_type": "chat_transcript",
                "source_id": str(row["transcript_id"]),
                "sentiment_label": label,
                "sentiment_score": score,
                "key_issue": str(row.get("topic", "")),
                "timestamp": str(row["timestamp"]),
                "processed_at": datetime.now().isoformat(),
            })

        self._insert_sentiment_records(records)
        return len(records)

    def batch_analyze_all(self) -> Dict[str, int]:
        """
        Process ALL historical data sources into the sentiment_scores table.

        Returns count of records processed per source type.
        """
        # Clear existing records to avoid duplicates
        with self.engine.connect() as conn:
            conn.execute(text("DELETE FROM sentiment_scores"))
            conn.commit()

        results = {
            "interactions": self.batch_process_interactions(),
            "support_tickets": self.batch_process_support_tickets(),
            "complaints": self.batch_process_complaints(),
            "chat_transcripts": self.batch_process_chat_transcripts(),
        }
        results["total"] = sum(results.values())
        return results

    # ==================================================================
    # Monthly Trend Computation
    # ==================================================================

    def compute_monthly_trend(self, customer_id: str, months: int = 6) -> List[Dict]:
        """
        Compute monthly average sentiment for a customer over the last N months.

        Returns list of dicts with month, avg_score, count, and label.
        """
        query = text("""
            SELECT 
                strftime('%Y-%m', timestamp) as month,
                AVG(sentiment_score) as avg_score,
                COUNT(*) as count
            FROM sentiment_scores
            WHERE customer_id = :cid
            GROUP BY month
            ORDER BY month DESC
            LIMIT :months
        """)

        df = pd.read_sql(query, self.engine, params={"cid": customer_id, "months": months})

        if df.empty:
            # Fallback: compute from interactions table directly
            return self._compute_trend_from_interactions(customer_id, months)

        trend = []
        for _, row in df.iterrows():
            avg = float(row["avg_score"])
            trend.append({
                "month": row["month"],
                "avg_score": round(avg, 3),
                "count": int(row["count"]),
                "label": self._score_to_label(avg),
            })

        return list(reversed(trend))  # Chronological order

    def _compute_trend_from_interactions(self, customer_id: str, months: int) -> List[Dict]:
        """Fallback trend computation from raw interactions table."""
        query = text("""
            SELECT 
                strftime('%Y-%m', timestamp) as month,
                AVG(sentiment_score) as avg_score,
                COUNT(*) as count
            FROM interactions
            WHERE customer_id = :cid
            GROUP BY month
            ORDER BY month DESC
            LIMIT :months
        """)
        df = pd.read_sql(query, self.engine, params={"cid": customer_id, "months": months})

        if df.empty:
            return []

        trend = []
        for _, row in df.iterrows():
            avg = float(row["avg_score"])
            trend.append({
                "month": row["month"],
                "avg_score": round(avg, 3),
                "count": int(row["count"]),
                "label": self._score_to_label(avg),
            })

        return list(reversed(trend))

    # ==================================================================
    # Alert Detection
    # ==================================================================

    def detect_declining_sentiment(self, min_months: int = 2) -> List[Dict]:
        """
        Detect customers with declining sentiment for 2+ consecutive months.

        Returns list of flagged customers with their trend data.
        """
        # Get all customers
        customers = pd.read_sql("SELECT customer_id FROM customers", self.engine)
        flagged = []

        for _, row in customers.iterrows():
            cid = row["customer_id"]
            trend = self.compute_monthly_trend(cid, months=6)

            if len(trend) < min_months + 1:
                continue

            # Check for consecutive decline
            decline_count = 0
            for i in range(1, len(trend)):
                if trend[i]["avg_score"] < trend[i - 1]["avg_score"]:
                    decline_count += 1
                else:
                    decline_count = 0

                if decline_count >= min_months:
                    flagged.append({
                        "customer_id": cid,
                        "consecutive_declining_months": decline_count,
                        "current_avg_sentiment": trend[-1]["avg_score"],
                        "trend": trend,
                    })
                    break

        return flagged

    def generate_alerts(self, flagged_customers: List[Dict] = None) -> int:
        """
        Generate manager alerts for customers with declining sentiment.

        Returns count of alerts created.
        """
        if flagged_customers is None:
            flagged_customers = self.detect_declining_sentiment()

        alert_count = 0
        with self.engine.connect() as conn:
            for customer in flagged_customers:
                cid = customer["customer_id"]
                decline = customer["consecutive_declining_months"]
                current = customer["current_avg_sentiment"]

                severity = "high" if current < -0.3 or decline >= 3 else "medium"

                conn.execute(text("""
                    INSERT INTO alerts 
                    (customer_id, alert_type, severity, message, details, status, created_at)
                    VALUES (:cid, :atype, :sev, :msg, :details, 'open', :ts)
                """), {
                    "cid": cid,
                    "atype": "declining_sentiment",
                    "sev": severity,
                    "msg": (
                        f"Customer sentiment declining for {decline} consecutive months. "
                        f"Current average: {current:.2f}. Review required."
                    ),
                    "details": str(customer.get("trend", [])),
                    "ts": datetime.now().isoformat(),
                })
                alert_count += 1

            conn.commit()

        return alert_count

    # ==================================================================
    # Customer Sentiment Summary
    # ==================================================================

    def get_customer_sentiment_summary(self, customer_id: str) -> Dict:
        """
        Get a comprehensive sentiment summary for a single customer.

        Returns distribution, trend, and alert status.
        """
        # Overall stats from sentiment_scores
        query = text("""
            SELECT 
                COUNT(*) as total,
                AVG(sentiment_score) as avg_score,
                MIN(sentiment_score) as min_score,
                MAX(sentiment_score) as max_score
            FROM sentiment_scores
            WHERE customer_id = :cid
        """)
        stats = pd.read_sql(query, self.engine, params={"cid": customer_id})

        # Distribution
        dist_query = text("""
            SELECT sentiment_label, COUNT(*) as count
            FROM sentiment_scores
            WHERE customer_id = :cid
            GROUP BY sentiment_label
        """)
        dist = pd.read_sql(dist_query, self.engine, params={"cid": customer_id})

        # Source type breakdown
        source_query = text("""
            SELECT source_type, COUNT(*) as count, AVG(sentiment_score) as avg_score
            FROM sentiment_scores
            WHERE customer_id = :cid
            GROUP BY source_type
        """)
        sources = pd.read_sql(source_query, self.engine, params={"cid": customer_id})

        # Monthly trend
        trend = self.compute_monthly_trend(customer_id)

        # Determine overall direction
        if len(trend) >= 2:
            if trend[-1]["avg_score"] > trend[0]["avg_score"]:
                direction = "improving"
            elif trend[-1]["avg_score"] < trend[0]["avg_score"]:
                direction = "declining"
            else:
                direction = "stable"
        else:
            direction = "insufficient_data"

        row = stats.iloc[0] if not stats.empty else {}

        return {
            "customer_id": customer_id,
            "total_scored_items": int(row.get("total", 0)),
            "avg_sentiment": round(float(row.get("avg_score", 0) or 0), 3),
            "min_sentiment": round(float(row.get("min_score", 0) or 0), 3),
            "max_sentiment": round(float(row.get("max_score", 0) or 0), 3),
            "distribution": dict(zip(dist["sentiment_label"], dist["count"])) if not dist.empty else {},
            "by_source": sources.to_dict(orient="records") if not sources.empty else [],
            "monthly_trend": trend,
            "trend_direction": direction,
        }

    # ==================================================================
    # Helpers
    # ==================================================================

    def _score_to_label(self, score: float) -> str:
        """Convert numeric score to label."""
        if score > 0.2:
            return "Positive"
        elif score < -0.2:
            return "Negative"
        else:
            return "Neutral"

    def _insert_sentiment_records(self, records: List[Dict]):
        """Bulk insert sentiment records into the sentiment_scores table."""
        with self.engine.connect() as conn:
            for r in records:
                conn.execute(text("""
                    INSERT INTO sentiment_scores
                    (customer_id, source_type, source_id, sentiment_label,
                     sentiment_score, key_issue, timestamp, processed_at)
                    VALUES (:customer_id, :source_type, :source_id, :sentiment_label,
                            :sentiment_score, :key_issue, :timestamp, :processed_at)
                """), r)
            conn.commit()


# --- CLI ---
if __name__ == "__main__":
    analyzer = SentimentAnalyzer()

    print("=" * 60)
    print("Sentiment Analysis Pipeline — Batch Processing")
    print("=" * 60)

    results = analyzer.batch_analyze_all()
    print(f"\nProcessed records:")
    for source, count in results.items():
        print(f"  {source:20s} {count:>6,}")

    print(f"\n{'-' * 60}")
    print("Detecting declining sentiment...")
    flagged = analyzer.detect_declining_sentiment()
    print(f"  Flagged customers: {len(flagged)}")

    if flagged:
        alert_count = analyzer.generate_alerts(flagged)
        print(f"  Alerts created: {alert_count}")

        print(f"\n  Sample flagged customer:")
        sample = flagged[0]
        print(f"    Customer: {sample['customer_id']}")
        print(f"    Declining months: {sample['consecutive_declining_months']}")
        print(f"    Current sentiment: {sample['current_avg_sentiment']:.3f}")

    # Show summary for first customer
    import sqlite3
    conn = sqlite3.connect("banking.db")
    cid = conn.execute("SELECT customer_id FROM customers LIMIT 1").fetchone()[0]
    conn.close()

    print(f"\n{'-' * 60}")
    print(f"Sample Sentiment Summary — {cid}")
    summary = analyzer.get_customer_sentiment_summary(cid)
    print(f"  Total items:   {summary['total_scored_items']}")
    print(f"  Avg sentiment: {summary['avg_sentiment']}")
    print(f"  Distribution:  {summary['distribution']}")
    print(f"  Trend:         {summary['trend_direction']}")
    print(f"  Monthly trend: {summary['monthly_trend']}")
    print("=" * 60)
