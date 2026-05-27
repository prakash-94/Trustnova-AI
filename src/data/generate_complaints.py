"""
Complaint Transcript Generator for the Banking AI System.

Generates 1,000+ customer complaint records with:
- Realistic complaint narratives covering common banking issues
- Resolution text from customer service perspective
- Sentiment scoring (mostly negative, as these are complaints)

Fields: complaint_id, customer_id, transcript_text, resolution_text, sentiment_score, timestamp
"""
import pandas as pd
import numpy as np
from faker import Faker
import os
import random

fake = Faker()
Faker.seed(42)
np.random.seed(42)

COMPLAINT_TEMPLATES = [
    {
        "category": "fees",
        "transcripts": [
            "I was charged a ${fee:.2f} maintenance fee on my checking account even though I maintain the minimum balance. I've been a customer for {years} years and this is unacceptable. I was told this account had no monthly fees when I opened it.",
            "My account was hit with an overdraft fee of ${fee:.2f} but the charge that triggered it was only ${small_amount:.2f}. The pending transactions weren't reflected in my available balance. This feels predatory.",
            "I received a notification about a new annual fee on my credit card. I was never informed this fee would be added. I've been paying my balance in full every month for {years} years.",
            "Three consecutive months I've been charged foreign transaction fees despite telling the bank I was traveling abroad and requesting a fee waiver.",
        ],
        "resolutions": [
            "Fee reversed as one-time courtesy. Customer reminded of minimum balance requirements. Account flagged for fee-free promotion eligibility.",
            "Overdraft fee reversed. Customer enrolled in overdraft protection program linked to savings account. Pending transaction display improvement escalated to product team.",
            "Annual fee waived for current year. Customer offered downgrade to no-annual-fee card or retention bonus of 15,000 points.",
            "All foreign transaction fees from the past 3 months reversed totaling ${refund:.2f}. Travel notification process reviewed with customer.",
        ],
        "sentiment_range": (-0.9, -0.4),
    },
    {
        "category": "service_quality",
        "transcripts": [
            "I waited in the branch for over an hour just to make a simple deposit. There were only two tellers working during lunch hour. This is the third time this has happened.",
            "I called customer support and was transferred {transfers} times before someone could answer my simple question about wire transfer limits. Each person asked me to repeat my information.",
            "The online banking system has been down twice this week during business hours. I couldn't pay my bills on time because of your outage, and now I'm worried about late fees.",
            "I scheduled an appointment with a financial advisor and they didn't show up. No call, no email, nothing. I took time off work for this meeting.",
            "Your mobile app logged me out during a bill payment and the payment went through twice. Now I have a double payment of ${amount:.2f} and an overdrawn checking account.",
        ],
        "resolutions": [
            "Manager contacted. Staffing schedule reviewed. Customer offered priority service line for future visits. Apology letter sent.",
            "Direct line to specialized support team provided. Customer complaint logged for call center training review. $25 service credit applied.",
            "Service outage acknowledged. Any resulting late fees will be reimbursed upon receipt submission. System stability improvements in progress.",
            "Advisor contacted. Rescheduled appointment with senior advisor. Complimentary financial review session added.",
            "Duplicate payment reversed within 24 hours. Overdraft fee waived. Customer shown how to enable payment confirmation alerts.",
        ],
        "sentiment_range": (-0.8, -0.3),
    },
    {
        "category": "account_access",
        "transcripts": [
            "I've been locked out of my account for 3 days now. I've called support twice and each time they say it's been 'escalated' but nothing happens. I can't pay my rent.",
            "My debit card was declined at the grocery store even though I have over ${balance:,.2f} in my account. This was extremely embarrassing in front of other customers.",
            "After the recent system update, my account shows the wrong balance. It's off by ${discrepancy:,.2f}. I'm very concerned about the accuracy of my account.",
            "I can't access my business account statements from before {months} months ago. The online portal says 'records unavailable.' I need these for my tax filing.",
        ],
        "resolutions": [
            "Account access restored immediately. Root cause: security hold triggered by IP change. Customer given direct contact for future issues. Apology credit of $50.",
            "Card hold released. Cause: fraud detection algorithm triggered by unusual purchase pattern. Customer profile updated. Temporary override code provided.",
            "Balance discrepancy identified as pending transaction timing issue. Correct balance confirmed. Written confirmation sent to customer.",
            "Historical statements recovered and sent via secure email. Portal access to 7-year statement history restored. System bug reported to IT.",
        ],
        "sentiment_range": (-0.9, -0.5),
    },
    {
        "category": "fraud_handling",
        "transcripts": [
            "It's been 3 weeks since I reported fraud on my account and I still haven't received my provisional credit. I've called {calls} times. I'm behind on my bills because of this.",
            "Someone opened a credit card in my name through your bank. When I reported it, the agent seemed to doubt my claim and asked if maybe I forgot about opening it. Very insulting.",
            "My replacement card after the fraud incident has the wrong name on it. This is the second replacement card with issues. I've been without a working card for {weeks} weeks.",
            "The fraud department closed my case saying the charges were 'verified' but I absolutely did not make those purchases. I have proof I was in a different city.",
        ],
        "resolutions": [
            "Provisional credit of ${credit:,.2f} issued immediately. Investigation expedited. Direct case manager assigned. Apology for delay with $100 inconvenience credit.",
            "Fraud case reopened with priority status. Agent feedback submitted to training department. Customer provided dedicated fraud analyst contact.",
            "Corrected card expedited via overnight shipping at no charge. Previous incorrect cards deactivated. Quality check added to card issuance process.",
            "Case reopened for re-investigation. Customer's travel documentation accepted as evidence. Internal fraud review team assigned.",
        ],
        "sentiment_range": (-0.95, -0.5),
    },
    {
        "category": "product_issues",
        "transcripts": [
            "I signed up for your premium checking account specifically for the cash back rewards, but the rewards haven't been posting for the past {months} months.",
            "The interest rate on my savings account dropped from {old_rate}% to {new_rate}% without any notification. I only discovered this when reviewing my statement.",
            "I was promised a bonus of ${bonus:,.0f} when I opened my account. It's been {months} months and the bonus hasn't been credited despite meeting all requirements.",
            "Your auto-pay system withdrew my mortgage payment twice this month. That's over ${amount:,.2f} taken from my account without authorization.",
        ],
        "resolutions": [
            "Missing cashback rewards totaling ${cashback:.2f} credited to account. System glitch identified and resolved. Monthly reward statements to be sent going forward.",
            "Rate change notification process reviewed. Customer offered rate match for 6-month promotional period. Automatic rate change alerts enabled.",
            "Bonus of ${bonus:,.0f} credited within 48 hours. Delay caused by system processing error. Apology letter with additional $25 credit sent.",
            "Duplicate payment reversed same-day. NSF protection confirmed. Auto-pay system audited. Customer given manual payment control option.",
        ],
        "sentiment_range": (-0.8, -0.3),
    },
]


def generate_complaints(n=1200):
    """Generate n complaint transcripts."""
    try:
        customers_df = pd.read_csv("data/raw/customers.csv")
        customer_ids = customers_df["customer_id"].tolist()
    except FileNotFoundError:
        print("Error: customers.csv not found. Run generate_customers.py first.")
        return

    complaints = []
    for _ in range(n):
        customer_id = random.choice(customer_ids)
        category_data = random.choice(COMPLAINT_TEMPLATES)

        # Fill in template variables
        format_vars = {
            "fee": round(random.uniform(12, 75), 2),
            "small_amount": round(random.uniform(3, 25), 2),
            "years": random.randint(2, 20),
            "amount": round(random.uniform(500, 5000), 2),
            "refund": round(random.uniform(15, 200), 2),
            "transfers": random.randint(3, 7),
            "balance": round(random.uniform(1000, 50000), 2),
            "discrepancy": round(random.uniform(50, 5000), 2),
            "months": random.randint(2, 12),
            "calls": random.randint(3, 10),
            "weeks": random.randint(2, 6),
            "credit": round(random.uniform(200, 8000), 2),
            "cashback": round(random.uniform(25, 300), 2),
            "bonus": random.choice([200, 300, 500, 750]),
            "old_rate": round(random.uniform(3.5, 5.0), 1),
            "new_rate": round(random.uniform(0.5, 2.0), 1),
        }

        transcript_template = random.choice(category_data["transcripts"])
        resolution_template = random.choice(category_data["resolutions"])

        try:
            transcript = transcript_template.format(**format_vars)
            resolution = resolution_template.format(**format_vars)
        except (KeyError, IndexError):
            transcript = transcript_template
            resolution = resolution_template

        lo, hi = category_data["sentiment_range"]
        sentiment_score = round(np.random.uniform(lo, hi), 2)

        complaint = {
            "complaint_id": fake.uuid4()[:12],
            "customer_id": customer_id,
            "category": category_data["category"],
            "transcript_text": transcript,
            "resolution_text": resolution,
            "sentiment_score": sentiment_score,
            "timestamp": fake.date_time_between(start_date="-1y", end_date="now").isoformat(),
        }
        complaints.append(complaint)

    df = pd.DataFrame(complaints)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/complaints.csv", index=False)

    print(f"Generated {n} complaints -> data/raw/complaints.csv")
    print(f"  Categories: {df['category'].value_counts().to_dict()}")
    print(f"  Sentiment:  {df['sentiment_score'].min():.2f} to {df['sentiment_score'].max():.2f} (mean {df['sentiment_score'].mean():.2f})")
    return df


if __name__ == "__main__":
    generate_complaints()
