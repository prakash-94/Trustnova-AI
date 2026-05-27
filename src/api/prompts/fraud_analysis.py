"""
Fraud Analysis Prompt Template.

Generates human-readable explanations for flagged transactions
using risk factors, SHAP-style feature contributions, and
contextual pattern analysis.

Routed to: GPT-4 (fraud_reasoning)
"""


def build_fraud_explanation_prompt(
    transaction: dict,
    fraud_probability: float,
    risk_tier: str,
    top_risk_factors: list,
    customer_context: str = "",
) -> str:
    """
    Build a structured prompt for explaining why a transaction was flagged.

    Args:
        transaction: Dict of transaction features
        fraud_probability: Model's predicted fraud probability (0-1)
        risk_tier: "Low", "Medium", or "High"
        top_risk_factors: List of dicts with feature, value, importance, contribution
        customer_context: Optional customer profile string

    Returns:
        Formatted prompt string for the LLM
    """
    factors_text = "\n".join(
        f"  - {f['feature']}: value={f['value']}, "
        f"model_importance={f['importance']:.4f}, "
        f"contribution_score={f['contribution']:.4f}"
        for f in top_risk_factors
    )

    prompt = f"""You are a fraud analysis AI for Citizens Bank. A transaction has been 
flagged by the fraud detection model. Generate a clear, banker-friendly explanation.

TRANSACTION DETAILS:
  Amount:         ${transaction.get('amount', 0):,.2f}
  Time:           {transaction.get('hour', 0)}:00
  New Device:     {'Yes' if transaction.get('device_new', 0) else 'No'}
  Geo Mismatch:   {'Yes' if transaction.get('geo_mismatch', 0) else 'No'}
  Weekend:        {'Yes' if transaction.get('is_weekend', 0) else 'No'}
  Amount Z-Score: {transaction.get('amount_zscore', 0):.2f}
  Velocity (30m): {transaction.get('velocity_30m', 0)} transactions
  Credit Score:   {transaction.get('credit_score', 700)}
  Account Age:    {transaction.get('account_age_days', 365)} days

MODEL OUTPUT:
  Fraud Probability: {fraud_probability:.1%}
  Risk Tier:         {risk_tier}

TOP RISK FACTORS (from XGBoost feature importance):
{factors_text}

{f'CUSTOMER CONTEXT:{chr(10)}{customer_context}' if customer_context else ''}

INSTRUCTIONS:
1. Explain WHY this transaction is {risk_tier} risk in 3-5 bullet points.
2. Each bullet should reference a specific risk factor and explain it in plain English.
3. Use concrete values (e.g., "$5,000 is 3.5 standard deviations above average").
4. Suggest a recommended action for the banker (approve, hold, escalate).
5. Keep the tone professional and concise.

Format your response as:
RISK ASSESSMENT:
- [bullet points]

RECOMMENDED ACTION: [action]
"""
    return prompt


def build_fraud_batch_summary_prompt(alerts: list) -> str:
    """
    Build a prompt for summarizing a batch of fraud alerts.

    Args:
        alerts: List of fraud alert dicts

    Returns:
        Formatted prompt string
    """
    alerts_text = "\n".join(
        f"  Alert {i+1}: ${a.get('amount', 0):,.2f} | "
        f"Risk: {a.get('risk_tier', 'Unknown')} | "
        f"Probability: {a.get('fraud_probability', 0):.1%} | "
        f"Customer: {a.get('customer_id', 'unknown')}"
        for i, a in enumerate(alerts)
    )

    return f"""You are a fraud monitoring AI for Citizens Bank. Summarize the following 
batch of fraud alerts for the branch manager.

ALERTS:
{alerts_text}

Provide:
1. A 2-sentence overview of the alert batch
2. The highest-priority alert and why
3. Any patterns you notice (common merchants, time patterns, etc.)
4. Recommended triage order

Keep it concise and actionable.
"""
