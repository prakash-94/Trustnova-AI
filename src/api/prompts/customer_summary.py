"""
Customer Summary Prompt Template.

Generates concise 3-sentence customer briefs for pre-appointment
preparation by branch bankers.

Routed to: GPT-3.5-turbo (lookup) or GPT-4 (general)
"""


def build_customer_brief_prompt(customer_context: str) -> str:
    """
    Build a prompt for generating a 3-sentence customer brief.

    Args:
        customer_context: Full customer context string from customer_context.py

    Returns:
        Formatted prompt string for the LLM
    """
    return f"""You are a Citizens Bank AI assistant. A banker is about to meet this customer.
Generate a concise 3-sentence pre-appointment brief.

CUSTOMER DATA:
{customer_context}

INSTRUCTIONS:
1. Sentence 1: Who they are (name, account type, key metrics like balance/credit score).
2. Sentence 2: Recent activity and sentiment (positive/negative trends, recent transactions).
3. Sentence 3: Opportunities or risks (product recommendations, fraud flags, retention concerns).

Keep each sentence under 30 words. Be specific with numbers. Use professional tone.
"""


def build_customer_risk_prompt(customer_context: str) -> str:
    """
    Build a prompt for generating a detailed customer risk assessment.

    Args:
        customer_context: Full customer context string

    Returns:
        Formatted prompt string
    """
    return f"""You are a Citizens Bank risk assessment AI. Analyze this customer's risk profile.

CUSTOMER DATA:
{customer_context}

Provide a structured risk assessment:

RISK PROFILE:
  Risk Level: [Low/Medium/High]
  Key Concerns: [list any concerns]

FINANCIAL HEALTH:
  Balance Trend: [stable/growing/declining]
  Credit Quality: [excellent/good/fair/poor]

RELATIONSHIP HEALTH:
  Sentiment: [positive/neutral/negative]
  Engagement: [high/moderate/low]
  Retention Risk: [low/moderate/high]

RECOMMENDED ACTIONS:
  - [action 1]
  - [action 2]

Be concise and data-driven. Reference specific numbers from the customer data.
"""


def build_customer_360_prompt(customer_context: str) -> str:
    """
    Build a prompt for a full Customer 360 narrative.

    Args:
        customer_context: Full customer context string

    Returns:
        Formatted prompt string
    """
    return f"""You are a Citizens Bank relationship intelligence AI. Create a comprehensive 
Customer 360 profile narrative.

CUSTOMER DATA:
{customer_context}

Write a 4-5 paragraph narrative covering:
1. Customer Overview: Who they are, how long they've been a customer, their primary accounts.
2. Financial Snapshot: Balance, credit quality, recent transaction patterns.
3. Interaction History: Sentiment trends, recent support issues, complaint patterns.
4. Risk Assessment: Trust score interpretation, fraud history, retention probability.
5. Opportunities: Product cross-sell suggestions with reasoning.

Use professional banking language. Reference specific data points.
"""
