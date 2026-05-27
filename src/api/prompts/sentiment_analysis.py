"""
Sentiment Analysis Prompt Template.

Classifies sentiment and extracts key complaints from
support tickets, chat transcripts, and interaction notes.

Routed to: GPT-3.5-turbo (sentiment)
"""


def build_sentiment_classification_prompt(text: str, source_type: str = "support_ticket") -> str:
    """
    Build a prompt for classifying sentiment and extracting complaints.

    Args:
        text: The text to analyze (support ticket, chat transcript, etc.)
        source_type: Type of source — "support_ticket", "chat_transcript", "complaint", "interaction_note"

    Returns:
        Formatted prompt string for the LLM
    """
    return f"""You are a Citizens Bank sentiment analysis AI. Classify the following 
{source_type.replace('_', ' ')} and extract key information.

TEXT:
{text}

RESPOND IN THIS EXACT JSON FORMAT:
{{
    "sentiment": "Positive" | "Neutral" | "Negative",
    "sentiment_score": <float from -1.0 to 1.0>,
    "key_issues": ["issue 1", "issue 2"],
    "customer_emotion": "satisfied" | "frustrated" | "angry" | "confused" | "neutral" | "appreciative",
    "urgency": "low" | "medium" | "high",
    "summary": "<1-sentence summary of the interaction>"
}}

RULES:
- sentiment_score: -1.0 = very negative, 0.0 = neutral, 1.0 = very positive
- key_issues: Extract 1-3 specific concerns or complaints
- urgency: "high" if customer mentions leaving, escalation, or legal action
- Return ONLY the JSON object, no other text
"""


def build_batch_sentiment_prompt(texts: list) -> str:
    """
    Build a prompt for batch sentiment analysis of multiple texts.

    Args:
        texts: List of dicts with 'id' and 'text' keys

    Returns:
        Formatted prompt string
    """
    texts_block = "\n---\n".join(
        f"ID: {t['id']}\nText: {t['text'][:500]}"
        for t in texts[:10]  # Cap at 10 per batch
    )

    return f"""You are a Citizens Bank sentiment analysis AI. Classify sentiment for each 
of the following texts.

TEXTS:
{texts_block}

RESPOND IN THIS EXACT JSON FORMAT (array of results):
[
    {{
        "id": "<text_id>",
        "sentiment": "Positive" | "Neutral" | "Negative",
        "sentiment_score": <float from -1.0 to 1.0>,
        "key_issue": "<primary concern in 5 words or less>"
    }},
    ...
]

Return ONLY the JSON array, no other text.
"""


def build_sentiment_trend_prompt(
    customer_id: str,
    sentiment_history: list,
) -> str:
    """
    Build a prompt for analyzing a customer's sentiment trend over time.

    Args:
        customer_id: The customer identifier
        sentiment_history: List of dicts with 'date', 'sentiment_score', 'source'

    Returns:
        Formatted prompt string
    """
    history_text = "\n".join(
        f"  {h.get('date', 'unknown')}: score={h.get('sentiment_score', 0):.2f} "
        f"({h.get('source', 'unknown')})"
        for h in sentiment_history
    )

    return f"""You are a Citizens Bank customer relationship AI. Analyze this customer's 
sentiment trend and provide insights.

CUSTOMER: {customer_id}

SENTIMENT HISTORY (chronological):
{history_text}

ANALYSIS REQUIRED:
1. TREND: Is sentiment improving, declining, or stable?
2. INFLECTION POINTS: When did significant changes occur?
3. RISK ASSESSMENT: Is this customer at risk of churning?
4. RECOMMENDED ACTIONS: What should the banker do?

Keep response concise (5-7 sentences max).
"""
