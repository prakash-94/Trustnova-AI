"""
Prompt Optimizer — Phase 8.

Analyzes correction patterns from banker feedback to detect
underperforming prompt templates and suggest improvements.

When a prompt template accumulates 10+ rejections:
  1. Extracts correction_text from rejected/edited responses
  2. Identifies common correction themes (keyword frequency analysis)
  3. Generates improvement suggestions based on patterns
  4. Logs new prompt version to prompt_versions table

Tables:
  prompt_versions — version history:
    template_name, version, old_prompt_hash, suggestion, reason,
    rejection_count, status ('suggested'|'applied'|'dismissed'), created_at
"""
import os
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")
REJECTION_THRESHOLD = 10  # Minimum rejections before suggesting improvements


class PromptOptimizer:
    """
    Analyzes feedback corrections to suggest prompt template improvements.

    When a prompt template accumulates enough rejections, the optimizer
    extracts common correction patterns and generates concrete improvement
    suggestions based on keyword frequency analysis.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine = create_engine(db_url)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create prompt_versions table if it doesn't exist."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    old_prompt_hash TEXT,
                    suggestion TEXT NOT NULL,
                    reason TEXT,
                    rejection_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'suggested',
                    created_at TEXT NOT NULL
                )
            """))
            conn.commit()

    # ==================================================================
    # Optimization Check
    # ==================================================================

    def check_optimization_needed(self) -> List[Dict]:
        """
        Check which prompt templates have accumulated enough rejections
        to warrant optimization.

        Returns list of templates that need improvement.
        """
        df = pd.read_sql(
            "SELECT prompt_template, feedback_type FROM ai_feedback",
            self.engine,
        )

        if df.empty:
            return []

        # Count rejections + edits per template
        negative = df[df["feedback_type"].isin(["reject", "edit"])]
        counts = negative["prompt_template"].value_counts()

        needs_optimization = []
        for template, count in counts.items():
            if count >= REJECTION_THRESHOLD:
                # Check if we already suggested for this count level
                existing = pd.read_sql(
                    text("SELECT MAX(rejection_count) as max_count FROM prompt_versions "
                         "WHERE template_name = :t"),
                    self.engine,
                    params={"t": template},
                )

                last_count = int(existing.iloc[0]["max_count"] or 0) if not existing.empty else 0

                # Only suggest again if rejections have grown by 10+
                if count >= last_count + REJECTION_THRESHOLD or last_count == 0:
                    needs_optimization.append({
                        "template_name": template,
                        "rejection_count": int(count),
                        "total_feedback": int(len(df[df["prompt_template"] == template])),
                        "rejection_rate": round(
                            count / len(df[df["prompt_template"] == template]), 4
                        ),
                    })

        return needs_optimization

    # ==================================================================
    # Improvement Suggestion
    # ==================================================================

    def suggest_improvement(self, template_name: str) -> Dict:
        """
        Analyze correction patterns for a template and suggest improvements.

        Extracts correction texts from rejected/edited responses,
        identifies common themes via keyword frequency, and generates
        concrete improvement suggestions.

        Args:
            template_name: The prompt template to analyze

        Returns:
            Dict with analysis results and improvement suggestions
        """
        # Get rejected/edited feedback for this template
        df = pd.read_sql(
            text("SELECT prompt, response_text, correction_text, feedback_type, "
                 "trust_score FROM ai_feedback "
                 "WHERE prompt_template = :t AND feedback_type IN ('reject', 'edit') "
                 "ORDER BY timestamp DESC"),
            self.engine,
            params={"t": template_name},
        )

        if df.empty:
            return {
                "template_name": template_name,
                "status": "no_data",
                "message": "No rejection data available for this template",
            }

        # Extract correction themes
        corrections = df[df["correction_text"].notna() & (df["correction_text"] != "")]
        themes = self._extract_themes(corrections)
        common_issues = self._identify_common_issues(df)

        # Generate improvement suggestions
        suggestions = self._generate_suggestions(template_name, themes, common_issues, df)

        # Store suggestion
        suggestion_text = "\n".join(suggestions) if suggestions else "No specific suggestions"
        reason = "; ".join(common_issues[:3]) if common_issues else "High rejection rate"

        self._log_suggestion(
            template_name=template_name,
            suggestion=suggestion_text,
            reason=reason,
            rejection_count=len(df),
        )

        return {
            "template_name": template_name,
            "rejection_count": len(df),
            "corrections_with_text": len(corrections),
            "avg_trust_score": round(float(df["trust_score"].mean()), 3),
            "common_themes": themes,
            "common_issues": common_issues,
            "suggestions": suggestions,
            "status": "suggestion_generated",
        }

    def _extract_themes(self, corrections_df: pd.DataFrame) -> List[Dict]:
        """
        Extract common themes from correction texts using keyword frequency.
        """
        if corrections_df.empty:
            return []

        # Combine all correction texts
        all_text = " ".join(corrections_df["correction_text"].fillna("").tolist()).lower()

        # Remove common stop words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "dare",
            "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
            "into", "through", "during", "before", "after", "above", "below",
            "between", "out", "off", "over", "under", "again", "further",
            "then", "once", "that", "this", "these", "those", "and", "but",
            "or", "nor", "not", "so", "if", "it", "its", "no", "yes",
        }

        # Tokenize and count
        words = re.findall(r'\b[a-z]{3,}\b', all_text)
        filtered = [w for w in words if w not in stop_words]
        word_counts = Counter(filtered)

        # Get top themes
        themes = []
        for word, count in word_counts.most_common(10):
            if count >= 2:  # At least mentioned twice
                themes.append({
                    "keyword": word,
                    "frequency": count,
                    "relevance": round(count / len(filtered) if filtered else 0, 4),
                })

        return themes

    def _identify_common_issues(self, df: pd.DataFrame) -> List[str]:
        """Identify common issue patterns from feedback data."""
        issues = []

        # Low trust score pattern
        avg_trust = df["trust_score"].mean()
        if avg_trust < 60:
            issues.append(f"Low average trust score ({avg_trust:.0f}/100) suggests retrieval quality issues")

        # Check if corrections mention specific patterns
        corrections = df["correction_text"].fillna("").str.lower()
        all_corrections = " ".join(corrections)

        pattern_checks = {
            "incorrect": "Factual accuracy issues detected in corrections",
            "wrong": "Incorrect information reported by bankers",
            "outdated": "Potentially outdated information in responses",
            "missing": "Missing information reported in corrections",
            "policy": "Policy-related accuracy issues",
            "threshold": "Threshold or limit values may be incorrect",
            "rate": "Rate or percentage values may need updating",
            "amount": "Monetary amounts may be inaccurate",
        }

        for keyword, description in pattern_checks.items():
            if keyword in all_corrections:
                issues.append(description)

        if not issues:
            issues.append("General quality concerns based on rejection pattern")

        return issues[:5]

    def _generate_suggestions(
        self,
        template_name: str,
        themes: List[Dict],
        issues: List[str],
        df: pd.DataFrame,
    ) -> List[str]:
        """Generate concrete improvement suggestions."""
        suggestions = []

        # Theme-based suggestions
        theme_keywords = [t["keyword"] for t in themes[:5]]
        if theme_keywords:
            suggestions.append(
                f"Add explicit instructions about: {', '.join(theme_keywords)}. "
                f"These topics appear frequently in banker corrections."
            )

        # Trust score-based suggestions
        avg_trust = df["trust_score"].mean()
        if avg_trust < 50:
            suggestions.append(
                "Consider increasing the number of retrieved context chunks "
                "to improve response accuracy and coverage."
            )
        elif avg_trust < 70:
            suggestions.append(
                "Add a verification step in the prompt template requiring "
                "the model to cite specific sources for each claim."
            )

        # Correction pattern suggestions
        corrections = df["correction_text"].fillna("").str.lower()
        all_corrections = " ".join(corrections)

        if "policy" in all_corrections or "regulation" in all_corrections:
            suggestions.append(
                "Include a directive to always reference the specific policy "
                "section and version number when discussing regulations."
            )

        if "amount" in all_corrections or "threshold" in all_corrections:
            suggestions.append(
                "Add explicit instructions to verify numerical values "
                "(amounts, thresholds, rates) against source documents."
            )

        if "outdated" in all_corrections:
            suggestions.append(
                "Add a recency check directive: instruct the model to flag "
                "when information may be outdated and recommend verification."
            )

        # General improvement
        suggestions.append(
            f"Review the '{template_name}' template structure. With "
            f"{len(df)} negative feedback items, consider restructuring "
            f"the prompt to be more specific about expected output format."
        )

        return suggestions[:5]

    # ==================================================================
    # Version Logging
    # ==================================================================

    def _log_suggestion(
        self,
        template_name: str,
        suggestion: str,
        reason: str,
        rejection_count: int,
    ):
        """Log a prompt improvement suggestion to the prompt_versions table."""
        # Get next version number
        existing = pd.read_sql(
            text("SELECT MAX(version) as max_v FROM prompt_versions "
                 "WHERE template_name = :t"),
            self.engine,
            params={"t": template_name},
        )
        next_version = int(existing.iloc[0]["max_v"] or 0) + 1 if not existing.empty else 1

        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO prompt_versions
                (template_name, version, suggestion, reason,
                 rejection_count, status, created_at)
                VALUES (:t, :v, :s, :r, :rc, 'suggested', :ts)
            """), {
                "t": template_name,
                "v": next_version,
                "s": suggestion,
                "r": reason,
                "rc": rejection_count,
                "ts": datetime.now().isoformat(),
            })
            conn.commit()

    def get_suggestion_history(self, template_name: str = None) -> List[Dict]:
        """Get history of prompt improvement suggestions."""
        if template_name:
            df = pd.read_sql(
                text("SELECT * FROM prompt_versions WHERE template_name = :t "
                     "ORDER BY created_at DESC"),
                self.engine,
                params={"t": template_name},
            )
        else:
            df = pd.read_sql(
                "SELECT * FROM prompt_versions ORDER BY created_at DESC",
                self.engine,
            )

        return df.to_dict(orient="records")

    def get_prompt_health(self) -> Dict:
        """
        Get overall prompt template health report.

        Returns per-template rejection counts, suggestions generated,
        and overall health assessment.
        """
        # Get feedback per template
        feedback_df = pd.read_sql(
            "SELECT prompt_template, feedback_type FROM ai_feedback",
            self.engine,
        )

        if feedback_df.empty:
            return {
                "total_templates_tracked": 0,
                "message": "No feedback data available",
            }

        # Get suggestions
        suggestions_df = pd.read_sql(
            "SELECT template_name, COUNT(*) as suggestion_count, "
            "MAX(rejection_count) as max_rejections "
            "FROM prompt_versions GROUP BY template_name",
            self.engine,
        )

        templates = {}
        for template, group in feedback_df.groupby("prompt_template"):
            total = len(group)
            rejections = len(group[group["feedback_type"].isin(["reject", "edit"])])

            suggestion_info = suggestions_df[
                suggestions_df["template_name"] == template
            ]
            num_suggestions = int(
                suggestion_info.iloc[0]["suggestion_count"]
            ) if not suggestion_info.empty else 0

            templates[str(template)] = {
                "total_feedback": total,
                "rejections": rejections,
                "rejection_rate": round(rejections / total, 4) if total > 0 else 0,
                "suggestions_generated": num_suggestions,
                "needs_attention": rejections >= REJECTION_THRESHOLD,
            }

        return {
            "total_templates_tracked": len(templates),
            "templates": templates,
            "optimization_threshold": REJECTION_THRESHOLD,
            "needs_optimization": [
                t for t, info in templates.items() if info["needs_attention"]
            ],
        }


# --- CLI ---
if __name__ == "__main__":
    optimizer = PromptOptimizer()

    print("=" * 60)
    print("Prompt Optimizer - Health Report")
    print("=" * 60)

    health = optimizer.get_prompt_health()
    print(f"\nTemplates tracked: {health.get('total_templates_tracked', 0)}")

    if health.get("total_templates_tracked", 0) > 0:
        for tmpl, info in health.get("templates", {}).items():
            flag = " [!]" if info["needs_attention"] else ""
            print(f"\n  {tmpl}{flag}:")
            print(f"    Total feedback: {info['total_feedback']}")
            print(f"    Rejections:     {info['rejections']} ({info['rejection_rate']:.0%})")
            print(f"    Suggestions:    {info['suggestions_generated']}")

        needs = health.get("needs_optimization", [])
        if needs:
            print(f"\nTemplates needing optimization: {needs}")
            for tmpl in needs:
                print(f"\n  Generating suggestions for '{tmpl}'...")
                result = optimizer.suggest_improvement(tmpl)
                for s in result.get("suggestions", []):
                    print(f"    -> {s}")
    else:
        print("No feedback data yet.")
        print("Submit feedback through /feedback to start tracking prompt quality.")

    print("=" * 60)
