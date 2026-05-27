"""
Chat Transcript Generator for the Banking AI System.

Generates 500+ multi-turn customer-agent chat transcripts as JSON arrays.
Each transcript covers a realistic banking conversation scenario.

Fields: transcript_id, customer_id, topic, turns (JSON array), sentiment_score, timestamp
Turn format: [{"role": "customer", "text": "..."}, {"role": "agent", "text": "..."}, ...]
"""
import pandas as pd
import numpy as np
from faker import Faker
import os
import random
import json

fake = Faker()
Faker.seed(42)
np.random.seed(42)

# Chat scenario templates — each is a list of (customer, agent) turn pairs
CHAT_SCENARIOS = {
    "balance_inquiry": {
        "turns": [
            ("Hi, I'd like to check my account balance.", "Hello! I'd be happy to help. Could you please verify your account number or the last 4 digits of your SSN?"),
            ("Sure, my account ends in 4523.", "Thank you for verifying. Your current checking account balance is ${balance:,.2f} as of today."),
            ("What about my savings?", "Your savings account balance is ${savings:,.2f}. Would you like a detailed statement?"),
            ("No, that's all. Thanks!", "You're welcome! Is there anything else I can help with today?"),
        ],
        "sentiment_range": (0.2, 0.6),
    },
    "fraud_report": {
        "turns": [
            ("I just noticed a charge on my card I didn't make!", "I'm sorry to hear that. Let me help you right away. Can you tell me which charge looks suspicious?"),
            ("There's a ${fraud_amount:,.2f} charge from a store in another state. I haven't been there.", "I understand your concern. I'm going to flag this transaction and temporarily block your card to prevent further unauthorized charges."),
            ("Please do. How did this happen?", "There are several ways cards can be compromised. We'll investigate this thoroughly. In the meantime, I'll issue you a replacement card."),
            ("How long will the investigation take?", "Typically 5-10 business days. You'll receive provisional credit within 48 hours. I'll also set up transaction alerts on your new card."),
            ("Okay, thank you for acting quickly.", "Of course. Your security is our priority. You'll receive the new card in 3-5 business days. Is there anything else?"),
        ],
        "sentiment_range": (-0.6, -0.1),
    },
    "loan_inquiry": {
        "turns": [
            ("I'm interested in a personal loan. What rates do you offer?", "Great question! Our personal loan rates start at 6.99% APR for qualified borrowers. The rate depends on your credit score and loan amount."),
            ("I'm looking to borrow about $15,000.", "For a $15,000 personal loan, you could qualify for rates between 6.99% and 12.99% APR with terms of 36 to 60 months."),
            ("What would my monthly payment be at the lowest rate?", "At 6.99% APR over 48 months, your monthly payment would be approximately $359. Would you like to start an application?"),
            ("Yes, let's do it. What do I need?", "Excellent! You'll need a valid ID, proof of income (last 2 pay stubs), and your SSN for the credit check. I can start the pre-qualification right now."),
        ],
        "sentiment_range": (0.1, 0.7),
    },
    "account_issue": {
        "turns": [
            ("I can't access my online banking. It keeps saying wrong password.", "I'm sorry for the inconvenience. Let me help you regain access. When did you last successfully log in?"),
            ("About a week ago. I tried resetting but the email never came.", "I see. Let me verify your email on file. It shows as j***@email.com. Is that correct?"),
            ("No, that's my old email! I updated it last month.", "I apologize for the confusion. It appears the email update may not have fully processed. Let me correct that now and send a fresh reset link."),
            ("Thank you. I was really worried I was locked out permanently.", "Not at all! Your account is secure. I've sent the reset link to your updated email. You should receive it within 2 minutes."),
            ("Got it! I'm in now. Thank you so much.", "Wonderful! I'd also recommend enabling two-factor authentication for extra security. Would you like me to set that up?"),
        ],
        "sentiment_range": (-0.3, 0.3),
    },
    "card_services": {
        "turns": [
            ("I'd like to increase my credit limit.", "I'd be happy to look into that for you. You currently have a ${limit:,.0f} limit. How much of an increase are you looking for?"),
            ("I'd like to double it if possible.", "Let me review your account history. You've been a customer for {years} years with an excellent payment record. I can submit a request for a ${new_limit:,.0f} limit."),
            ("That would be great. Will it affect my credit score?", "A limit increase request may involve a soft or hard inquiry depending on the review. In your case, we can do a soft pull first with no impact to your score."),
            ("Perfect, let's proceed.", "Request submitted! You should receive a decision within 1-2 business days via email. Is there anything else I can help with?"),
        ],
        "sentiment_range": (0.2, 0.7),
    },
    "complaint": {
        "turns": [
            ("I've been on hold for 45 minutes! This is unacceptable.", "I sincerely apologize for the long wait time. I understand how frustrating that must be. How can I help you today?"),
            ("I was charged a $35 overdraft fee but I had money in my account!", "I'm sorry about that. Let me look into this immediately. Can you tell me which transaction triggered the fee?"),
            ("The charge from yesterday. My balance was positive before it!", "I see the issue. There was a pending authorization that reduced your available balance before the charge posted. I understand this is confusing."),
            ("That's ridiculous. I want the fee reversed.", "I completely understand your frustration. Given your account history, I'm going to reverse this fee as a courtesy. You should see the credit within 24 hours."),
            ("Fine. You need to fix this system though.", "You're absolutely right, and I appreciate your feedback. I'll escalate this to our product team. Is there anything else I can help with?"),
        ],
        "sentiment_range": (-0.8, -0.2),
    },
    "transfer_help": {
        "turns": [
            ("I need to wire money internationally. How do I do that?", "I can help with that! International wire transfers can be done online or in-branch. Where are you sending the funds?"),
            ("To the UK. About $5,000.", "For a GBP transfer of approximately $5,000, the wire fee is $45 for online transfers. You'll need the recipient's IBAN and SWIFT code."),
            ("How long does it take?", "International wires typically take 1-3 business days. We use competitive exchange rates updated in real-time. Would you like to initiate the transfer now?"),
            ("Yes, I have the IBAN ready.", "Let me guide you through the process. I'll also set up a transfer confirmation email so you can track when the funds arrive."),
        ],
        "sentiment_range": (0.0, 0.5),
    },
    "mortgage_inquiry": {
        "turns": [
            ("We're looking to buy our first home. Where do we start?", "Congratulations! That's exciting. The first step is getting pre-approved. This gives you a clear picture of what you can afford."),
            ("What do we need for pre-approval?", "You'll need proof of income, 2 years of tax returns, bank statements, and employment verification. Your credit score will also be reviewed."),
            ("Our combined income is about $120,000 and scores are around 740.", "With those numbers, you're in a strong position! You could potentially qualify for a loan up to $400,000-$450,000 depending on your debts."),
            ("What rates are you offering?", "Current 30-year fixed rates start at 6.25% for well-qualified borrowers like yourselves. We also offer ARM options starting at 5.75%. Shall I schedule a meeting with our mortgage specialist?"),
            ("Yes please!", "Wonderful! I've booked you with Sarah Chen, our senior mortgage advisor, for Thursday at 2 PM. She'll walk you through all your options. Congratulations again!"),
        ],
        "sentiment_range": (0.3, 0.8),
    },
}


def generate_chat_transcripts(n=600):
    """Generate n multi-turn chat transcripts."""
    try:
        customers_df = pd.read_csv("data/raw/customers.csv")
        customer_ids = customers_df["customer_id"].tolist()
    except FileNotFoundError:
        print("Error: customers.csv not found. Run generate_customers.py first.")
        return

    scenarios = list(CHAT_SCENARIOS.keys())
    transcripts = []

    for _ in range(n):
        customer_id = random.choice(customer_ids)
        scenario_key = random.choice(scenarios)
        scenario = CHAT_SCENARIOS[scenario_key]

        # Build turn list with filled-in templates
        turns = []
        for customer_text, agent_text in scenario["turns"]:
            # Fill in placeholder values
            format_vars = {
                "balance": round(np.random.uniform(500, 50000), 2),
                "savings": round(np.random.uniform(1000, 100000), 2),
                "fraud_amount": round(np.random.uniform(50, 5000), 2),
                "limit": random.choice([3000, 5000, 7500, 10000, 15000]),
                "new_limit": random.choice([10000, 15000, 20000, 25000, 30000]),
                "years": random.randint(2, 15),
            }
            try:
                c_text = customer_text.format(**format_vars)
                a_text = agent_text.format(**format_vars)
            except (KeyError, IndexError):
                c_text = customer_text
                a_text = agent_text

            turns.append({"role": "customer", "text": c_text})
            turns.append({"role": "agent", "text": a_text})

        lo, hi = scenario["sentiment_range"]
        sentiment_score = round(np.random.uniform(lo, hi), 2)

        transcript = {
            "transcript_id": fake.uuid4()[:12],
            "customer_id": customer_id,
            "topic": scenario_key,
            "turns": json.dumps(turns),
            "num_turns": len(turns),
            "sentiment_score": sentiment_score,
            "timestamp": fake.date_time_between(start_date="-1y", end_date="now").isoformat(),
        }
        transcripts.append(transcript)

    df = pd.DataFrame(transcripts)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/chat_transcripts.csv", index=False)

    print(f"Generated {n} chat transcripts -> data/raw/chat_transcripts.csv")
    print(f"  Topics:    {df['topic'].value_counts().to_dict()}")
    print(f"  Avg turns: {df['num_turns'].mean():.1f}")
    print(f"  Sentiment: {df['sentiment_score'].min():.2f} to {df['sentiment_score'].max():.2f}")
    return df


if __name__ == "__main__":
    generate_chat_transcripts()
