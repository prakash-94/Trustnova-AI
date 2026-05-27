"""
Support Ticket Generator for the Banking AI System.

Generates 3,000+ synthetic support tickets with:
- 5 issue categories: billing dispute, app login, fraud report, product inquiry, account closure
- Sentiment distribution: mostly neutral/positive, negative for disputes and closures
- Multiple channels: phone, email, chat, branch, mobile app

Fields: ticket_id, customer_id, issue, sentiment, resolution, timestamp, channel
"""
import pandas as pd
import numpy as np
from faker import Faker
import os
import random

fake = Faker()
Faker.seed(42)
np.random.seed(42)

ISSUES = {
    "billing_dispute": {
        "descriptions": [
            "Overcharged on monthly account maintenance fee",
            "Duplicate charge from merchant appeared on statement",
            "Unauthorized subscription charge detected",
            "Foreign transaction fee applied incorrectly",
            "ATM withdrawal fee dispute — was supposed to be fee-free",
            "Interest rate charged higher than agreed upon",
            "Late payment fee applied despite on-time payment",
            "Cashback reward not credited to account",
        ],
        "resolutions": [
            "Fee reversed. Customer notified via email.",
            "Duplicate charge refunded. Merchant flagged for review.",
            "Charge reversed. Customer advised to contact merchant.",
            "Fee waived as a one-time courtesy. Policy explained.",
            "ATM fee refunded. Network partner list provided.",
            "Rate corrected. Difference refunded.",
            "Late fee waived. Payment date confirmed.",
            "Cashback manually credited. System error logged.",
        ],
        "sentiment_range": (-0.8, -0.2),
        "weight": 0.20,
    },
    "app_login": {
        "descriptions": [
            "Unable to log in to mobile banking app after update",
            "Two-factor authentication code not being received",
            "Password reset link not working",
            "App crashes on launch after iOS update",
            "Biometric login (Face ID) stopped working",
            "Session timeout too frequent — keeps logging out",
        ],
        "resolutions": [
            "Password reset completed. Customer logged in successfully.",
            "2FA method switched to authenticator app.",
            "Reset link re-sent. Customer confirmed access.",
            "App reinstall resolved the issue.",
            "Biometric re-enrolled. Working correctly now.",
            "Session timeout extended to 30 minutes per customer request.",
        ],
        "sentiment_range": (-0.5, 0.1),
        "weight": 0.18,
    },
    "fraud_report": {
        "descriptions": [
            "Customer reports unauthorized purchase on credit card",
            "Suspicious wire transfer initiated from account",
            "ATM withdrawal in a city the customer has never visited",
            "Multiple small charges from unknown online merchants",
            "Identity theft suspected — new accounts opened in customer's name",
            "Card skimming suspected at gas station",
        ],
        "resolutions": [
            "Card blocked. Replacement issued. Fraud investigation opened.",
            "Wire transfer reversed. Account frozen pending review.",
            "ATM transaction disputed. Provisional credit issued.",
            "Charges reversed. Card reissued with new number.",
            "Identity theft affidavit filed. Accounts secured. Credit bureaus notified.",
            "Card replaced. Merchant reported to fraud team.",
        ],
        "sentiment_range": (-0.9, -0.3),
        "weight": 0.15,
    },
    "product_inquiry": {
        "descriptions": [
            "Interested in opening a high-yield savings account",
            "Asking about mortgage pre-approval requirements",
            "Wants information on business checking account features",
            "Inquiring about CD rates and terms",
            "Questions about credit card rewards program",
            "Looking for auto loan rate comparison",
            "Interested in wealth management services",
        ],
        "resolutions": [
            "Brochure sent. Appointment scheduled with advisor.",
            "Pre-qualification checklist provided. Application link sent.",
            "Business banking package details emailed. Follow-up scheduled.",
            "Current CD rates provided. Online application link shared.",
            "Rewards program details explained. Upgrade offer presented.",
            "Auto loan calculator link provided. Pre-approval initiated.",
            "Referred to wealth management team. Consultation booked.",
        ],
        "sentiment_range": (0.1, 0.7),
        "weight": 0.30,
    },
    "account_closure": {
        "descriptions": [
            "Customer wants to close savings account — moving to competitor",
            "Closing account due to relocation to another state",
            "Dissatisfied with service quality — wants to close all accounts",
            "Closing dormant account that hasn't been used in 2 years",
            "Estate closure — account holder deceased",
            "Student account closure after graduation",
        ],
        "resolutions": [
            "Retention offer presented. Customer declined. Account closure initiated.",
            "Account closed. Final balance transferred to new bank.",
            "Manager callback scheduled. Retention offer accepted — account kept open.",
            "Dormant account closed. Remaining balance check mailed.",
            "Condolences offered. Estate documentation collected. Account to be closed after probate.",
            "Account closed. Customer transitioned to regular checking.",
        ],
        "sentiment_range": (-0.7, -0.1),
        "weight": 0.17,
    },
}

CHANNELS = ["phone", "email", "chat", "branch", "mobile_app"]
CHANNEL_WEIGHTS = [0.30, 0.20, 0.25, 0.15, 0.10]


def generate_support_tickets(n=3000):
    """Generate n synthetic support tickets."""
    try:
        customers_df = pd.read_csv("data/raw/customers.csv")
        customer_ids = customers_df["customer_id"].tolist()
    except FileNotFoundError:
        print("Error: customers.csv not found. Run generate_customers.py first.")
        return

    issue_types = list(ISSUES.keys())
    issue_weights = [ISSUES[i]["weight"] for i in issue_types]

    tickets = []
    for _ in range(n):
        customer_id = random.choice(customer_ids)
        issue_type = random.choices(issue_types, weights=issue_weights)[0]
        issue_data = ISSUES[issue_type]

        sentiment_lo, sentiment_hi = issue_data["sentiment_range"]
        sentiment = round(np.random.uniform(sentiment_lo, sentiment_hi), 2)

        ticket = {
            "ticket_id": fake.uuid4()[:12],
            "customer_id": customer_id,
            "issue": issue_type,
            "issue_description": random.choice(issue_data["descriptions"]),
            "sentiment": sentiment,
            "resolution": random.choice(issue_data["resolutions"]),
            "channel": random.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
            "timestamp": fake.date_time_between(start_date="-1y", end_date="now").isoformat(),
        }
        tickets.append(ticket)

    df = pd.DataFrame(tickets)
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv("data/raw/support_tickets.csv", index=False)

    print(f"Generated {n} support tickets -> data/raw/support_tickets.csv")
    print(f"  Issues:    {df['issue'].value_counts().to_dict()}")
    print(f"  Channels:  {df['channel'].value_counts().to_dict()}")
    print(f"  Sentiment: {df['sentiment'].min():.2f} to {df['sentiment'].max():.2f} (mean {df['sentiment'].mean():.2f})")
    return df


if __name__ == "__main__":
    generate_support_tickets()
