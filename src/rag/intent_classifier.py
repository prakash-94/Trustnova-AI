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
        # Name-first queries: "Raj J profile history", "John Doe profile"
        r"\bprofile.{0,10}history\b",
        r"\bprofile\b",
        r"\b360\b",
        r"(history|detail|overview)\s+(of|for)\s+\w",
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
        r"outstanding.?loan", r"delinquent.?loan", r"pending.?loan",
        r"loan.{0,15}pending", r"how.?many.?loan",
        r"loan.?amount", r"loan.?balance", r"loan.?value",
        r"(highest|largest|biggest|maximum|max|top|lowest|smallest|minimum|min).{0,25}loan",
        r"loan.{0,25}(highest|largest|biggest|maximum|max|top|lowest|smallest|minimum|min)",
        r"customer.{0,25}(loan|borrow)",
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
    "kyc": [
        r"kyc.?status", r"kyc.?document", r"kyc.?complete", r"identity.?verif",
        r"customer.?due.?diligence", r"cdd.?level", r"enhanced.?due.?diligence",
        r"know.?your.?customer", r"(show|check|get).{0,20}kyc",
    ],
    "aml": [
        r"aml.?alert", r"suspicious.?activity.?report", r"\bsar\b", r"\bctr\b",
        r"cash.?transaction.?report", r"structuring", r"aml.?watchlist",
        r"currency.?transaction", r"anti.?money.?laundering", r"aml.?flag",
    ],
    "policy": [
        r"what.?is.?the.?policy", r"compliance.?rule", r"regulatory.?requirement",
        r"policy.?for.{0,20}(wire|transfer|aml|kyc|loan|account)",
        r"threshold.?for.{0,20}(flagging|alert|report)",
        r"(bsa|aml|kyc).{0,20}(policy|rule|compliance|regulation)",
        r"what.?triggers.{0,20}(sar|ctr|alert|flag)",
        r"documentation.?required.{0,20}policy",
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
      trust_score | kyc | aml | policy | trustnova_features | general

    Matching is ordered: more specific intents checked first.
    Falls back to 'general' when nothing matches.
    """
    return classify_intents(query)[0]


def classify_intents(query: str, max_intents: int = 3) -> list[str]:
    """Return all relevant intents for compound questions in priority order."""
    q = query.lower().strip()
    matches = [
        intent
        for intent, patterns in _PATTERNS.items()
        if any(re.search(pattern, q) for pattern in patterns)
    ]
    if not matches:
        return ["general"]
    # A concrete entity intent is more useful than the broad stats fallback.
    if len(matches) > 1 and "stats" in matches:
        matches.remove("stats")
    return matches[:max_intents]


def needs_graph_context(query: str, customer_id: str | None = None) -> bool:
    """Detect multi-hop customer questions best served by Customer 360 traversal."""
    q = query.lower()
    relationship_cues = (
        "why", "explain", "relationship", "connected", "linked", "across",
        "customer 360", "full picture", "risk factors", "activity",
    )
    entity_cues = ("customer", "account", "transaction", "loan", "fraud", "risk")
    return bool(customer_id or "customer" in q) and (
        any(cue in q for cue in relationship_cues)
        and sum(cue in q for cue in entity_cues) >= 2
    )


def plan_intents(query: str, customer_id: str | None = None) -> list[str]:
    """Build a bounded structured-retrieval plan, adding graph traversal when useful."""
    intents = classify_intents(query)
    if needs_graph_context(query, customer_id) and "customer" not in intents:
        intents.insert(0, "customer")
    return intents[:3]


def needs_db_data(intent: str) -> bool:
    """Return True if this intent requires live structured DB data."""
    return intent in {
        "risk", "fraud", "customer", "transaction", "account",
        "loan", "trust_score", "stats", "kyc", "aml",
    }
