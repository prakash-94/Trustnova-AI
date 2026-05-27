"""
Phase 4 Prompt Template Verification Tests.

Tests each of the 4 prompt templates with 5 sample inputs each,
verifying output structure, content quality, and correct formatting.

Templates tested:
  1. fraud_analysis.py     — 5 transaction scenarios
  2. customer_summary.py   — 5 customer context scenarios
  3. banking_compliance.py — 5 compliance query scenarios
  4. sentiment_analysis.py — 5 text classification scenarios
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.api.prompts.fraud_analysis import (
    build_fraud_explanation_prompt,
    build_fraud_batch_summary_prompt,
)
from src.api.prompts.customer_summary import (
    build_customer_brief_prompt,
    build_customer_risk_prompt,
    build_customer_360_prompt,
)
from src.api.prompts.banking_compliance import (
    build_compliance_extraction_prompt,
    build_regulatory_check_prompt,
)
from src.api.prompts.sentiment_analysis import (
    build_sentiment_classification_prompt,
    build_batch_sentiment_prompt,
    build_sentiment_trend_prompt,
)


# ============================================================
# Sample Data Fixtures
# ============================================================

SAMPLE_TRANSACTIONS = [
    {
        "desc": "High-risk: large amount, new device, geo mismatch, 2am",
        "txn": {"amount": 5000, "hour": 2, "device_new": 1, "geo_mismatch": 1,
                "is_weekend": 0, "amount_zscore": 3.5, "velocity_30m": 4,
                "credit_score": 450, "account_age_days": 30},
        "prob": 0.95, "tier": "High",
        "factors": [
            {"feature": "amount", "value": 5000, "importance": 0.35, "contribution": 1750},
            {"feature": "device_new", "value": 1, "importance": 0.22, "contribution": 0.22},
            {"feature": "geo_mismatch", "value": 1, "importance": 0.18, "contribution": 0.18},
        ],
    },
    {
        "desc": "Medium-risk: moderate amount, unusual hour",
        "txn": {"amount": 1200, "hour": 23, "device_new": 0, "geo_mismatch": 0,
                "is_weekend": 1, "amount_zscore": 1.8, "velocity_30m": 2,
                "credit_score": 620, "account_age_days": 180},
        "prob": 0.55, "tier": "Medium",
        "factors": [
            {"feature": "amount_zscore", "value": 1.8, "importance": 0.30, "contribution": 0.54},
            {"feature": "hour", "value": 23, "importance": 0.15, "contribution": 3.45},
            {"feature": "velocity_30m", "value": 2, "importance": 0.12, "contribution": 0.24},
        ],
    },
    {
        "desc": "Low-risk: normal transaction",
        "txn": {"amount": 45, "hour": 14, "device_new": 0, "geo_mismatch": 0,
                "is_weekend": 0, "amount_zscore": -0.2, "velocity_30m": 0,
                "credit_score": 780, "account_age_days": 2500},
        "prob": 0.02, "tier": "Low",
        "factors": [
            {"feature": "credit_score", "value": 780, "importance": 0.10, "contribution": 78},
            {"feature": "account_age_days", "value": 2500, "importance": 0.08, "contribution": 200},
            {"feature": "amount", "value": 45, "importance": 0.35, "contribution": 15.75},
        ],
    },
    {
        "desc": "Suspicious velocity: many transactions in short window",
        "txn": {"amount": 200, "hour": 10, "device_new": 0, "geo_mismatch": 1,
                "is_weekend": 0, "amount_zscore": 0.5, "velocity_30m": 8,
                "credit_score": 700, "account_age_days": 900},
        "prob": 0.72, "tier": "High",
        "factors": [
            {"feature": "velocity_30m", "value": 8, "importance": 0.12, "contribution": 0.96},
            {"feature": "geo_mismatch", "value": 1, "importance": 0.18, "contribution": 0.18},
            {"feature": "amount_zscore", "value": 0.5, "importance": 0.30, "contribution": 0.15},
        ],
    },
    {
        "desc": "New account with large first purchase",
        "txn": {"amount": 3000, "hour": 15, "device_new": 1, "geo_mismatch": 0,
                "is_weekend": 0, "amount_zscore": 4.1, "velocity_30m": 1,
                "credit_score": 550, "account_age_days": 7},
        "prob": 0.81, "tier": "High",
        "factors": [
            {"feature": "account_age_days", "value": 7, "importance": 0.08, "contribution": 0.56},
            {"feature": "amount_zscore", "value": 4.1, "importance": 0.30, "contribution": 1.23},
            {"feature": "device_new", "value": 1, "importance": 0.22, "contribution": 0.22},
        ],
    },
]

SAMPLE_CUSTOMER_CONTEXTS = [
    "Name: John Smith\nCustomer ID: abc123\nBalance: $45,000\nCredit Score: 780\nAccount Age: 2500 days\nRisk Level: Low\nSentiment: Positive (0.7)\nLast Transaction: $120 at Whole Foods",
    "Name: Maria Garcia\nCustomer ID: def456\nBalance: $2,100\nCredit Score: 520\nAccount Age: 90 days\nRisk Level: High\nSentiment: Negative (-0.4)\n2 fraud alerts (1 false positive)",
    "Name: James Wilson\nCustomer ID: ghi789\nBalance: $125,000\nCredit Score: 820\nAccount Age: 3650 days\nRisk Level: Low\nSentiment: Neutral (0.1)\nWealth management client",
    "Name: Sarah Chen\nCustomer ID: jkl012\nBalance: $8,500\nCredit Score: 680\nAccount Age: 400 days\nRisk Level: Medium\nSentiment: Negative (-0.6)\n3 support tickets in last month",
    "Name: Robert Johnson\nCustomer ID: mno345\nBalance: $0.00\nCredit Score: 450\nAccount Age: 1200 days\nRisk Level: High\nSentiment: Very Negative (-0.9)\nAccount closure request pending",
]

SAMPLE_COMPLIANCE_QUERIES = [
    ("What is the CTR filing threshold for cash deposits?", "Section 4.1: Cash Transaction Reports (CTR) must be filed for any cash transaction exceeding $10,000..."),
    ("What KYC documents are required for a business account?", "Section 2.3: Business accounts require: Articles of Incorporation, EIN documentation, beneficial ownership declaration..."),
    ("What are the wire transfer limits for personal accounts?", "Section 5.2: Personal domestic wires limited to $50,000/day. International wires limited to $25,000/day..."),
    ("When must a SAR be filed?", "Section 4.5: Suspicious Activity Reports must be filed within 30 days when suspicious activity is detected involving $5,000 or more..."),
    ("What are the OFAC screening requirements?", "Section 6.1: All new accounts and wire transfers must be screened against OFAC SDN list before processing..."),
]

SAMPLE_SENTIMENT_TEXTS = [
    ("I've been waiting 3 weeks for my replacement card and nobody has followed up. This is unacceptable!", "support_ticket"),
    ("Thank you so much for resolving my issue quickly. The agent was very helpful and professional.", "support_ticket"),
    ("I want to close my account. Your fees are ridiculous and your app never works.", "complaint"),
    ("Can you tell me about your savings account interest rates? I'm comparing options.", "chat_transcript"),
    ("The branch manager personally called me to check on my mortgage application. Very impressed with the service.", "interaction_note"),
]


# ============================================================
# Fraud Analysis Prompt Tests
# ============================================================
class TestFraudAnalysisPrompts:
    """Test fraud_analysis.py with 5 sample transactions."""

    @pytest.mark.parametrize("sample", SAMPLE_TRANSACTIONS, ids=[s["desc"][:50] for s in SAMPLE_TRANSACTIONS])
    def test_fraud_explanation_prompt_structure(self, sample):
        """Each prompt should contain key sections and transaction details."""
        prompt = build_fraud_explanation_prompt(
            transaction=sample["txn"],
            fraud_probability=sample["prob"],
            risk_tier=sample["tier"],
            top_risk_factors=sample["factors"],
        )

        assert isinstance(prompt, str)
        assert len(prompt) > 200, "Prompt should be substantial"

        # Must contain key sections
        assert "TRANSACTION DETAILS" in prompt
        assert "MODEL OUTPUT" in prompt
        assert "TOP RISK FACTORS" in prompt
        assert "INSTRUCTIONS" in prompt

        # Must contain actual values
        assert f"${sample['txn']['amount']:,.2f}" in prompt
        assert f"{sample['prob']:.1%}" in prompt
        assert sample["tier"] in prompt

    @pytest.mark.parametrize("sample", SAMPLE_TRANSACTIONS, ids=[s["desc"][:50] for s in SAMPLE_TRANSACTIONS])
    def test_fraud_explanation_with_customer_context(self, sample):
        """Prompt should include customer context when provided."""
        prompt = build_fraud_explanation_prompt(
            transaction=sample["txn"],
            fraud_probability=sample["prob"],
            risk_tier=sample["tier"],
            top_risk_factors=sample["factors"],
            customer_context="Customer: John Smith, Balance: $45,000, Credit Score: 780",
        )
        assert "CUSTOMER CONTEXT" in prompt
        assert "John Smith" in prompt

    def test_batch_summary_prompt(self):
        """Batch summary prompt should list all alerts."""
        alerts = [
            {"amount": 5000, "risk_tier": "High", "fraud_probability": 0.95, "customer_id": "abc123"},
            {"amount": 200, "risk_tier": "Low", "fraud_probability": 0.1, "customer_id": "def456"},
            {"amount": 1200, "risk_tier": "Medium", "fraud_probability": 0.55, "customer_id": "ghi789"},
        ]
        prompt = build_fraud_batch_summary_prompt(alerts)
        assert "Alert 1" in prompt
        assert "Alert 2" in prompt
        assert "Alert 3" in prompt
        assert "$5,000" in prompt


# ============================================================
# Customer Summary Prompt Tests
# ============================================================
class TestCustomerSummaryPrompts:
    """Test customer_summary.py with 5 sample customer contexts."""

    @pytest.mark.parametrize("context", SAMPLE_CUSTOMER_CONTEXTS, ids=[c.split("\n")[0] for c in SAMPLE_CUSTOMER_CONTEXTS])
    def test_customer_brief_prompt_structure(self, context):
        """Brief prompt should contain instructions for 3 sentences."""
        prompt = build_customer_brief_prompt(context)

        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "CUSTOMER DATA" in prompt
        assert "3-sentence" in prompt or "Sentence 1" in prompt
        assert context in prompt  # Customer data should be embedded

    @pytest.mark.parametrize("context", SAMPLE_CUSTOMER_CONTEXTS, ids=[c.split("\n")[0] for c in SAMPLE_CUSTOMER_CONTEXTS])
    def test_customer_risk_prompt_structure(self, context):
        """Risk prompt should request structured risk assessment."""
        prompt = build_customer_risk_prompt(context)

        assert "RISK PROFILE" in prompt
        assert "FINANCIAL HEALTH" in prompt
        assert "RELATIONSHIP HEALTH" in prompt
        assert "RECOMMENDED ACTIONS" in prompt
        assert context in prompt

    @pytest.mark.parametrize("context", SAMPLE_CUSTOMER_CONTEXTS, ids=[c.split("\n")[0] for c in SAMPLE_CUSTOMER_CONTEXTS])
    def test_customer_360_prompt_structure(self, context):
        """360 prompt should request comprehensive narrative."""
        prompt = build_customer_360_prompt(context)

        assert "Customer 360" in prompt or "360" in prompt
        assert "CUSTOMER DATA" in prompt
        assert context in prompt
        assert len(prompt) > 200


# ============================================================
# Banking Compliance Prompt Tests
# ============================================================
class TestBankingCompliancePrompts:
    """Test banking_compliance.py with 5 compliance query scenarios."""

    @pytest.mark.parametrize(
        "query,context",
        SAMPLE_COMPLIANCE_QUERIES,
        ids=[q[:50] for q, _ in SAMPLE_COMPLIANCE_QUERIES],
    )
    def test_compliance_extraction_prompt_structure(self, query, context):
        """Compliance prompt should contain query, context, and citation instructions."""
        prompt = build_compliance_extraction_prompt(query, context)

        assert isinstance(prompt, str)
        assert "COMPLIANCE QUESTION" in prompt
        assert "RETRIEVED POLICY DOCUMENTS" in prompt
        assert "APPLICABLE POLICIES" in prompt
        assert query in prompt
        assert context in prompt
        # Must enforce citation format
        assert "According to" in prompt or "citation" in prompt.lower()

    @pytest.mark.parametrize(
        "query,context",
        SAMPLE_COMPLIANCE_QUERIES,
        ids=[q[:50] for q, _ in SAMPLE_COMPLIANCE_QUERIES],
    )
    def test_regulatory_check_prompt_structure(self, query, context):
        """Regulatory check prompt should reference key regulations."""
        prompt = build_regulatory_check_prompt(query)

        assert "BSA/AML" in prompt or "AML" in prompt
        assert "KYC" in prompt
        assert "CTR" in prompt
        assert "SAR" in prompt
        assert "OFAC" in prompt
        assert "COMPLIANCE STATUS" in prompt


# ============================================================
# Sentiment Analysis Prompt Tests
# ============================================================
class TestSentimentAnalysisPrompts:
    """Test sentiment_analysis.py with 5 sample texts."""

    @pytest.mark.parametrize(
        "text,source_type",
        SAMPLE_SENTIMENT_TEXTS,
        ids=[t[:40] for t, _ in SAMPLE_SENTIMENT_TEXTS],
    )
    def test_sentiment_classification_prompt_structure(self, text, source_type):
        """Sentiment prompt should request JSON output with required fields."""
        prompt = build_sentiment_classification_prompt(text, source_type)

        assert isinstance(prompt, str)
        assert text in prompt
        # Must request structured output
        assert "sentiment" in prompt.lower()
        assert "sentiment_score" in prompt
        assert "key_issues" in prompt
        assert "urgency" in prompt
        # Must specify the source type
        assert source_type.replace("_", " ") in prompt

    def test_batch_sentiment_prompt(self):
        """Batch prompt should handle multiple texts."""
        texts = [
            {"id": "t1", "text": "Great service, very helpful staff."},
            {"id": "t2", "text": "Terrible experience, waited 2 hours."},
            {"id": "t3", "text": "Can you help me reset my password?"},
        ]
        prompt = build_batch_sentiment_prompt(texts)

        assert "t1" in prompt
        assert "t2" in prompt
        assert "t3" in prompt
        assert "JSON" in prompt

    def test_sentiment_trend_prompt(self):
        """Trend prompt should include customer history."""
        history = [
            {"date": "2026-01-01", "sentiment_score": 0.8, "source": "chat"},
            {"date": "2026-02-01", "sentiment_score": 0.3, "source": "ticket"},
            {"date": "2026-03-01", "sentiment_score": -0.5, "source": "complaint"},
        ]
        prompt = build_sentiment_trend_prompt("cust_123", history)

        assert "cust_123" in prompt
        assert "TREND" in prompt
        assert "RISK ASSESSMENT" in prompt
        assert "0.80" in prompt or "0.8" in prompt


# ============================================================
# Cross-Template Consistency Tests
# ============================================================
class TestPromptConsistency:
    """Verify all prompts follow consistent patterns."""

    def test_all_prompts_are_strings(self):
        """Every prompt builder should return a non-empty string."""
        results = [
            build_fraud_explanation_prompt(SAMPLE_TRANSACTIONS[0]["txn"], 0.9, "High", SAMPLE_TRANSACTIONS[0]["factors"]),
            build_fraud_batch_summary_prompt([{"amount": 100, "risk_tier": "Low", "fraud_probability": 0.1, "customer_id": "x"}]),
            build_customer_brief_prompt("Test customer data"),
            build_customer_risk_prompt("Test customer data"),
            build_customer_360_prompt("Test customer data"),
            build_compliance_extraction_prompt("Test query", "Test context"),
            build_regulatory_check_prompt("Test transaction"),
            build_sentiment_classification_prompt("Test text", "support_ticket"),
            build_batch_sentiment_prompt([{"id": "1", "text": "test"}]),
            build_sentiment_trend_prompt("cust_1", [{"date": "2026-01-01", "sentiment_score": 0.5, "source": "chat"}]),
        ]

        for i, result in enumerate(results):
            assert isinstance(result, str), f"Prompt {i} is not a string"
            assert len(result) > 50, f"Prompt {i} is too short ({len(result)} chars)"

    def test_all_prompts_mention_citizens_bank(self):
        """All prompts should establish the Citizens Bank context."""
        prompts = [
            build_fraud_explanation_prompt(SAMPLE_TRANSACTIONS[0]["txn"], 0.9, "High", SAMPLE_TRANSACTIONS[0]["factors"]),
            build_customer_brief_prompt("Test"),
            build_compliance_extraction_prompt("Test", "Test"),
            build_sentiment_classification_prompt("Test", "support_ticket"),
        ]

        for prompt in prompts:
            assert "Citizens Bank" in prompt, f"Prompt missing 'Citizens Bank': {prompt[:100]}..."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
