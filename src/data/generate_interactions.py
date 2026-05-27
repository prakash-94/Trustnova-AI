"""
Banker Interaction Notes Generator for the Banking AI System.

Generates 4,500+ banker interaction notes with:
- Multiple channels: branch, phone, email, chat, video
- Topic categorization: mortgage, savings, complaint, fraud, general, loan, investment
- Sentiment-weighted note templates
- Realistic banker language

Fields: interaction_id, customer_id, channel, topic, sentiment_label,
        sentiment_score, banker_notes, timestamp
"""
import pandas as pd
import numpy as np
from faker import Faker
import os
import random

fake = Faker()
Faker.seed(42)
np.random.seed(42)

CHANNELS = ["branch", "phone", "email", "chat", "video"]
CHANNEL_WEIGHTS = [0.25, 0.30, 0.15, 0.20, 0.10]

TOPICS = {
    "mortgage": {
        "positive": [
            "Customer visited to discuss mortgage options. Very satisfied with current rates. Pre-approval submitted.",
            "Mortgage refinance discussion — customer excited about potential savings of $350/month.",
            "First-time homebuyer consultation. Customer appreciated the detailed walkthrough of the process.",
            "Mortgage rate lock completed. Customer happy with the 6.2% fixed rate.",
        ],
        "neutral": [
            "Routine mortgage payment inquiry. Provided payoff timeline and amortization schedule.",
            "Customer asked about switching from variable to fixed rate. Options presented.",
            "Escrow account review completed. No changes needed at this time.",
        ],
        "negative": [
            "Customer frustrated with mortgage processing delays. Escalated to underwriting team.",
            "Mortgage application denied due to DTI ratio. Customer upset. Alternative options discussed.",
        ],
        "weight": 0.15,
    },
    "savings": {
        "positive": [
            "Opened a new savings account. Expressed interest in long-term wealth management.",
            "Customer delighted with HYSA rate increase. Deposited additional $15,000.",
            "Discussed retirement savings goals. Customer opened a Roth IRA.",
            "CD ladder strategy explained and implemented. Customer invested $50,000 across 4 terms.",
        ],
        "neutral": [
            "Updated contact information and address. Routine account maintenance.",
            "Savings account balance inquiry. Statement copy provided.",
            "Customer asked about minimum balance requirements. Policy explained.",
        ],
        "negative": [
            "Customer dissatisfied with savings interest rate compared to online banks.",
            "Early CD withdrawal request due to emergency. Penalty explained and waived.",
        ],
        "weight": 0.15,
    },
    "complaint": {
        "positive": [
            "Previous complaint about mobile app resolved. Customer confirmed satisfaction.",
            "Follow-up on overdraft fee complaint. Fee refunded. Customer now satisfied.",
        ],
        "neutral": [
            "Customer filed complaint about branch wait times. Logged and forwarded to manager.",
            "Online banking outage complaint acknowledged. ETR communicated.",
        ],
        "negative": [
            "Frustrated with wait times at the branch. Mentioned considering other banks.",
            "Complained about overdraft fees. Requested a reversal which was denied per policy.",
            "Customer escalated complaint to manager. Dissatisfied with resolution timeline.",
            "Multiple failed attempts to reach support. Customer very frustrated.",
            "Expressed concern over recent transaction delays. Wants compensation.",
        ],
        "weight": 0.15,
    },
    "fraud": {
        "positive": [
            "Fraud case resolved. Customer confirmed all charges have been reversed.",
            "Customer grateful for quick fraud detection. New card issued same-day.",
        ],
        "neutral": [
            "Fraud investigation update provided. Customer aware of ongoing review.",
            "Card replacement issued after suspected compromise. Temporary limit set.",
        ],
        "negative": [
            "Customer upset about unauthorized charges. Emergency card block initiated.",
            "Fraud claim taking longer than expected. Customer demanding immediate resolution.",
            "Reported issues with the fraud hotline hold times. Escalated internally.",
        ],
        "weight": 0.10,
    },
    "general": {
        "positive": [
            "Routine check-in. Customer is happy with the mobile app interface and services.",
            "Customer praised the new branch renovations. Positive overall experience.",
            "Discussed financial wellness program. Customer enrolled in budgeting tools.",
        ],
        "neutral": [
            "Standard account maintenance performed. No issues reported.",
            "Deposited a large check from tax return. Verified hold policy.",
            "Inquired about international wire transfer fees and processes.",
            "Requested a replacement debit card due to wear and tear.",
        ],
        "negative": [
            "Customer reported issues with the web portal login. Tech support ticket raised.",
            "Unsatisfied with the interest rates on personal loans compared to competitors.",
        ],
        "weight": 0.20,
    },
    "loan": {
        "positive": [
            "Personal loan approved. Customer happy with the terms and rate.",
            "Auto loan consultation. Customer pre-approved for $35,000 at 5.9%.",
            "Student loan refinance completed. Customer saving $200/month.",
        ],
        "neutral": [
            "Loan payment schedule reviewed. Customer requests bi-weekly payments.",
            "Loan balance inquiry. Payoff quote generated and emailed.",
        ],
        "negative": [
            "Loan application denied due to insufficient credit history. Customer disappointed.",
            "Customer struggling with loan payments. Discussed hardship deferment options.",
        ],
        "weight": 0.13,
    },
    "investment": {
        "positive": [
            "Discussed retirement planning. Positive outlook on future investments. Portfolio growing 12% YTD.",
            "Customer excited about new managed portfolio option. Transferred $25,000 from savings.",
        ],
        "neutral": [
            "Investment portfolio quarterly review. Performance in line with benchmarks.",
            "Customer asked about ESG fund options. Information packet provided.",
        ],
        "negative": [
            "Customer concerned about recent market volatility impacting their portfolio.",
            "Unhappy with investment advisory fees. Compared to robo-advisor alternatives.",
        ],
        "weight": 0.12,
    },
}


def generate_interactions(n=4500):
    """Generate n banker interaction notes."""
    try:
        customers_df = pd.read_csv("data/raw/customers.csv")
        customer_ids = customers_df["customer_id"].tolist()
    except FileNotFoundError:
        print("Error: customers.csv not found. Run generate_customers.py first.")
        return

    topic_names = list(TOPICS.keys())
    topic_weights = [TOPICS[t]["weight"] for t in topic_names]

    interactions = []
    for _ in range(n):
        customer_id = random.choice(customer_ids)
        topic = random.choices(topic_names, weights=topic_weights)[0]
        topic_data = TOPICS[topic]

        # Weighted sentiment: 50% positive, 30% neutral, 20% negative
        sentiment_label = random.choices(
            ["positive", "neutral", "negative"],
            weights=[0.50, 0.30, 0.20]
        )[0]

        # Select note from matching sentiment category
        notes_pool = topic_data.get(sentiment_label, topic_data.get("neutral", ["General interaction."]))
        banker_note = random.choice(notes_pool)

        # Sentiment score correlated with label
        if sentiment_label == "positive":
            sentiment_score = round(random.uniform(0.3, 0.9), 2)
        elif sentiment_label == "negative":
            sentiment_score = round(random.uniform(-0.9, -0.3), 2)
        else:
            sentiment_score = round(random.uniform(-0.1, 0.1), 2)

        interaction = {
            "interaction_id": fake.uuid4()[:12],
            "customer_id": customer_id,
            "channel": random.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
            "topic": topic,
            "sentiment_label": sentiment_label,
            "sentiment_score": sentiment_score,
            "banker_note": banker_note,
            "timestamp": fake.date_time_between(start_date="-1y", end_date="now").isoformat(),
        }
        interactions.append(interaction)

    df = pd.DataFrame(interactions)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/interactions.csv", index=False)

    print(f"Generated {n} interactions -> data/raw/interactions.csv")
    print(f"  Topics:    {df['topic'].value_counts().to_dict()}")
    print(f"  Channels:  {df['channel'].value_counts().to_dict()}")
    print(f"  Sentiment: {df['sentiment_label'].value_counts().to_dict()}")
    return df


if __name__ == "__main__":
    generate_interactions()
