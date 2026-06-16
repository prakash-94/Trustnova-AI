"""
Query intent classifier for TrustNova Hybrid Enterprise RAG.
Routes queries to the right data sources (DB, documents, or both).
"""
import re

# intent → list of regex patterns (case-insensitive, applied to lowercased query)
_PATTERNS: dict[str, list[str]] = {
    "risk": [
        r"high.?risk", r"medium.?risk", r"low.?risk", r"critical.?risk",
        r"risk.?profile", r"risk.?rating", r"aml.?risk", r"credit.?risk",
        r"risky", r"risk.?score", r"risk.?tier", r"risk.?level",
        r"risk.?customer", r"customer.{0,20}risk", r"risk.{0,20}customer",
        r"(pull|show|list|get|display).{0,25}risk",
        r"customers?.{0,15}(at|with).{0,10}risk",
    ],
    "fraud": [
        r"fraud.?alert", r"fraud.?case", r"suspicious.?activity",
        r"flagged.?transaction", r"fraud.?detection", r"fraud.?report",
        r"active.?fraud", r"open.?alert", r"fraud.?queue",
        r"(show|list|pull|get|display).{0,20}fraud",
        r"aml.?alert", r"transaction.?fraud",
    ],
    "customer": [
        r"customer.?profile", r"customer.?history", r"customer.?detail",
        r"customer.?info", r"customer.?summary", r"client.?profile",
        r"360.?view", r"customer.?360",
        r"(show|find|get|pull|display).{0,20}customer",
        r"who.?is.{0,40}(customer|client)",
        r"tell.?me.?about.{0,30}(customer|client)",
        r"show.{0,20}(history|profile).{0,20}for",
    ],
    "transaction": [
        r"transaction.?history", r"recent.?transaction",
        r"payment.?history", r"transfer.?history",
        r"spending.?pattern", r"transaction.?summary",
        r"(show|list|get|pull).{0,20}transaction",
        r"latest.?transaction", r"txn.?history",
    ],
    "account": [
        r"account.?balance", r"account.?detail", r"account.?summary",
        r"checking.?account", r"savings.?account", r"account.?status",
        r"(show|list|get|pull).{0,20}account",
        r"account.?info", r"account.?overview", r"balance.?sheet",
    ],
    "loan": [
        r"loan.?portfolio", r"active.?loan", r"loan.?pipeline",
        r"loan.?application", r"loan.?status", r"loan.?history",
        r"outstanding.?loan", r"delinquent.?loan",
        r"(show|list|get|pull|display).{0,20}loan",
        r"mortgage.?status", r"loan.?summary",
    ],
    "trust_score": [
        r"trust.?score", r"ai.?trust", r"trust.?rating", r"trust.?level",
        r"(show|list|get|pull).{0,20}trust.?score",
        r"trustscore", r"customer.?trust", r"trust.?metric",
    ],
    "trustnova_features": [
        r"trustnova.?feature", r"what.?can.?(trusnova|trustnova)",
        r"platform.?feature", r"what.?does.?(trusnova|trustnova)",
        r"system.?feature", r"ai.?capabilities",
        r"(what|how).{0,10}(is|does).{0,20}(trusnova|trustnova)",
        r"(trusnova|trustnova).{0,20}(offer|platform|overview|capabilities)",
        r"trusnova.{0,20}(do|work|help)", r"features.{0,20}available",
    ],
    "stats": [
        r"(total|how.?many|number.?of|count.?of|how.?much).{0,25}customer",
        r"customer.{0,20}(total|count|number|stat|summary|overview|breakdown)",
        r"(total|how.?many|number.?of|count.?of).{0,25}(client|account|loan|alert)",
        r"institution.{0,20}(summary|overview|dashboard|stat)",
        r"portfolio.{0,15}(summary|overview|stat)",
        r"(risk|fraud|aml).{0,15}(summary|overview|dashboard|stat)",
        r"overall.{0,20}(customer|risk|fraud|loan|portfolio)",
        r"(platform|bank|trusnova|trustnova).{0,20}(overview|summary|stat)",
        r"(get|show|pull|give).{0,30}(total|count|number|summary|breakdown).{0,20}customer",
    ],
}


def classify_intent(query: str) -> str:
    """
    Classify query into one of:
      risk | fraud | customer | transaction | account | loan |
      trust_score | trustnova_features | general

    Matching is ordered: more specific intents checked first.
    Falls back to 'general' when nothing matches.
    """
    q = query.lower().strip()
    for intent, patterns in _PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                return intent
    return "general"


def needs_db_data(intent: str) -> bool:
    """Return True if this intent requires live structured DB data."""
    return intent in {"risk", "fraud", "customer", "transaction", "account", "loan", "trust_score", "stats"}