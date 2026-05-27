"""
Feedback Analyzer — Phase 8.

Generates weekly reports on AI response quality by analyzing
feedback patterns across models, prompt templates, and document types.
Alerts when rejection rate for any category exceeds 20%.

Reports:
  - Overall: total feedback, approval/rejection/edit rates
  - Per Model: rejection rate for gpt-4, gpt-3.5-turbo, etc.
  - Per Prompt Template: rejection rate for compliance, fraud, customer, sentiment
  - Per Doc Type: rejection rate by document category
  - Alerts: categories exceeding 20% rejection threshold
"""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")
REJECTION_ALERT_THRESHOLD = 0.20  # 20%


class FeedbackAnalyzer:
    """
    Analyzes AI feedback patterns to identify quality issues.

    Generates reports with rejection rates broken down by model,
    prompt template, and document type. Alerts when any category
    exceeds the rejection threshold.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)

    # ==================================================================
    # Weekly Report
    # ==================================================================

    def weekly_report(self, days: int = 7) -> Dict:
        """
        Generate a comprehensive weekly feedback report.

        Args:
            days: Number of days to look back (default 7)

        Returns:
            Dict with overall stats, per-model, per-template, per-doc-type
            breakdowns, and any triggered alerts.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        df = pd.read_sql(
            text("SELECT * FROM ai_feedback WHERE timestamp >= :cutoff"),
            self.engine,
            params={"cutoff": cutoff},
        )

        if df.empty:
            # Fall back to all-time data
            df = pd.read_sql("SELECT * FROM ai_feedback", self.engine)

        if df.empty:
            return {
                "period": f"Last {days} days",
                "total_feedback": 0,
                "message": "No feedback data available",
                "generated_at": datetime.now().isoformat(),
            }

        # Overall stats
        overall = self._compute_rates(df)

        # Per-model breakdown
        model_breakdown = self._breakdown_by_column(df, "model_used")

        # Per-template breakdown
        template_breakdown = self._breakdown_by_column(df, "prompt_template")

        # Per-doc-type breakdown
        doc_breakdown = self._breakdown_by_column(df, "doc_type")

        # Check alerts
        alerts = self.check_alert_thresholds(
            model_breakdown, template_breakdown, doc_breakdown
        )

        return {
            "period": f"Last {days} days",
            "total_feedback": len(df),
            "overall": overall,
            "by_model": model_breakdown,
            "by_prompt_template": template_breakdown,
            "by_doc_type": doc_breakdown,
            "alerts": alerts,
            "generated_at": datetime.now().isoformat(),
        }

    # ==================================================================
    # Alert Checking
    # ==================================================================

    def check_alert_thresholds(
        self,
        model_breakdown: Dict = None,
        template_breakdown: Dict = None,
        doc_breakdown: Dict = None,
    ) -> List[Dict]:
        """
        Check if any category exceeds the 20% rejection rate threshold.

        Returns list of triggered alerts.
        """
        if model_breakdown is None or template_breakdown is None:
            report = self.weekly_report()
            model_breakdown = report.get("by_model", {})
            template_breakdown = report.get("by_prompt_template", {})
            doc_breakdown = report.get("by_doc_type", {})

        alerts = []

        # Check models
        for model, stats in model_breakdown.items():
            if not model:
                continue
            rate = stats.get("rejection_rate", 0)
            if rate > REJECTION_ALERT_THRESHOLD:
                alerts.append({
                    "category": "model",
                    "name": model,
                    "rejection_rate": round(rate, 4),
                    "total_feedback": stats.get("total", 0),
                    "severity": "high" if rate > 0.35 else "medium",
                    "message": (
                        f"Model '{model}' has a {rate:.0%} rejection rate "
                        f"({stats.get('reject', 0)} rejections out of "
                        f"{stats.get('total', 0)} responses). "
                        f"Review model configuration or prompt templates."
                    ),
                })

        # Check templates
        for template, stats in template_breakdown.items():
            if not template:
                continue
            rate = stats.get("rejection_rate", 0)
            if rate > REJECTION_ALERT_THRESHOLD:
                alerts.append({
                    "category": "prompt_template",
                    "name": template,
                    "rejection_rate": round(rate, 4),
                    "total_feedback": stats.get("total", 0),
                    "severity": "high" if rate > 0.35 else "medium",
                    "message": (
                        f"Prompt template '{template}' has a {rate:.0%} rejection rate. "
                        f"Consider revising the template or reviewing corrections."
                    ),
                })

        # Check doc types
        if doc_breakdown:
            for doc_type, stats in doc_breakdown.items():
                if not doc_type:
                    continue
                rate = stats.get("rejection_rate", 0)
                if rate > REJECTION_ALERT_THRESHOLD:
                    alerts.append({
                        "category": "doc_type",
                        "name": doc_type,
                        "rejection_rate": round(rate, 4),
                        "total_feedback": stats.get("total", 0),
                        "severity": "medium",
                        "message": (
                            f"Document type '{doc_type}' responses have a {rate:.0%} "
                            f"rejection rate. Review indexed content quality."
                        ),
                    })

        # Store alerts in alerts table
        if alerts:
            self._store_alerts(alerts)

        return alerts

    # ==================================================================
    # Individual Breakdowns
    # ==================================================================

    def get_model_performance(self) -> Dict:
        """Get performance breakdown by model."""
        df = pd.read_sql("SELECT * FROM ai_feedback", self.engine)
        if df.empty:
            return {}
        return self._breakdown_by_column(df, "model_used")

    def get_template_performance(self) -> Dict:
        """Get performance breakdown by prompt template."""
        df = pd.read_sql("SELECT * FROM ai_feedback", self.engine)
        if df.empty:
            return {}
        return self._breakdown_by_column(df, "prompt_template")

    def get_doc_type_performance(self) -> Dict:
        """Get performance breakdown by document type."""
        df = pd.read_sql("SELECT * FROM ai_feedback", self.engine)
        if df.empty:
            return {}
        return self._breakdown_by_column(df, "doc_type")

    def get_trust_score_correlation(self) -> Dict:
        """Analyze correlation between trust score and feedback type."""
        df = pd.read_sql("SELECT feedback_type, trust_score FROM ai_feedback", self.engine)
        if df.empty:
            return {"message": "No data available"}

        result = {}
        for ftype in ["approve", "reject", "edit"]:
            subset = df[df["feedback_type"] == ftype]["trust_score"]
            if not subset.empty:
                result[ftype] = {
                    "count": len(subset),
                    "avg_trust_score": round(float(subset.mean()), 3),
                    "min_trust_score": round(float(subset.min()), 3),
                    "max_trust_score": round(float(subset.max()), 3),
                }
        return result

    # ==================================================================
    # Helpers
    # ==================================================================

    def _compute_rates(self, df: pd.DataFrame) -> Dict:
        """Compute approval/rejection/edit rates for a DataFrame."""
        total = len(df)
        if total == 0:
            return {"total": 0}

        counts = df["feedback_type"].value_counts().to_dict()
        approve = counts.get("approve", 0)
        reject = counts.get("reject", 0)
        edit = counts.get("edit", 0)

        return {
            "total": total,
            "approve": approve,
            "reject": reject,
            "edit": edit,
            "approval_rate": round(approve / total, 4),
            "rejection_rate": round(reject / total, 4),
            "edit_rate": round(edit / total, 4),
            "avg_trust_score": round(float(df["trust_score"].mean()), 3) if "trust_score" in df.columns else 0,
        }

    def _breakdown_by_column(self, df: pd.DataFrame, column: str) -> Dict:
        """Compute rates broken down by a grouping column."""
        result = {}
        if column not in df.columns:
            return result

        for group, group_df in df.groupby(column, dropna=False):
            key = str(group) if group else "unknown"
            result[key] = self._compute_rates(group_df)

        return result

    def _store_alerts(self, alerts: List[Dict]):
        """Store triggered alerts in the alerts table."""
        with self.engine.connect() as conn:
            for alert in alerts:
                conn.execute(text("""
                    INSERT INTO alerts
                    (customer_id, alert_type, severity, message, details, status, created_at)
                    VALUES (:cid, :atype, :sev, :msg, :details, 'open', :ts)
                """), {
                    "cid": "SYSTEM",
                    "atype": f"feedback_quality_{alert['category']}",
                    "sev": alert["severity"],
                    "msg": alert["message"],
                    "details": f"{alert['name']}: {alert['rejection_rate']:.0%} rejection rate",
                    "ts": datetime.now().isoformat(),
                })
            conn.commit()


# --- CLI ---
if __name__ == "__main__":
    analyzer = FeedbackAnalyzer()

    print("=" * 60)
    print("Feedback Analyzer - Weekly Report")
    print("=" * 60)

    report = analyzer.weekly_report(days=30)

    print(f"\nPeriod: {report['period']}")
    print(f"Total feedback: {report['total_feedback']}")

    if report["total_feedback"] == 0:
        print("No feedback data yet. Submit feedback through the /feedback endpoint.")
    else:
        overall = report.get("overall", {})
        print(f"\nOverall Rates:")
        print(f"  Approval:  {overall.get('approval_rate', 0):.0%} ({overall.get('approve', 0)})")
        print(f"  Rejection: {overall.get('rejection_rate', 0):.0%} ({overall.get('reject', 0)})")
        print(f"  Edit:      {overall.get('edit_rate', 0):.0%} ({overall.get('edit', 0)})")

        if report.get("by_model"):
            print(f"\nBy Model:")
            for model, stats in report["by_model"].items():
                print(f"  {model}: {stats['rejection_rate']:.0%} rejection "
                      f"({stats['total']} total)")

        if report.get("by_prompt_template"):
            print(f"\nBy Prompt Template:")
            for tmpl, stats in report["by_prompt_template"].items():
                print(f"  {tmpl}: {stats['rejection_rate']:.0%} rejection "
                      f"({stats['total']} total)")

        alerts = report.get("alerts", [])
        if alerts:
            print(f"\n{'!' * 60}")
            print(f"ALERTS ({len(alerts)}):")
            for a in alerts:
                print(f"  [{a['severity'].upper()}] {a['message']}")
        else:
            print(f"\nNo quality alerts triggered.")

    print("=" * 60)
