"""
Query Router — builds a typed RetrievalManifest before any retrieval starts.

Wraps the existing intent_classifier to produce a structured manifest that
tells the parallel retriever exactly which sources, tables, and entities
to fetch. RBAC pre-filtering happens here so blocked sources are never
queried at all.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from src.rag.intent_classifier import classify_intents, needs_db_data

# ── Intent → SQL tables needed ────────────────────────────────────────────────

_INTENT_TABLES: dict[str, list[str]] = {
    "risk":             ["customers"],
    "fraud":            ["fraud_alerts", "enriched_transactions", "customers"],
    "customer":         ["customers", "accounts", "enriched_transactions", "loans"],
    "transaction":      ["enriched_transactions", "customers"],
    "account":          ["accounts", "customers"],
    "loan":             ["loans", "customers"],
    "trust_score":      ["trust_scores", "customers"],
    "stats":            [],  # portfolio summary — no customer-specific tables
    "trustnova_features": [],
    "general":          [],
}

# Intents that always need the risk engine output
_RISK_ENGINE_INTENTS  = {"risk", "customer", "trust_score"}
# Intents that always need fraud engine output
_FRAUD_ENGINE_INTENTS = {"fraud", "customer", "transaction"}
# Intents that always need vector DB (policy/docs)
_VECTOR_INTENTS       = {"trustnova_features", "general", "stats"}
# Codebase/feature reference
_CODE_INTENTS         = {"trustnova_features"}

# Permission required to access each source
_SOURCE_PERMISSIONS: dict[str, str] = {
    "fraud_engine": "fraud:read",
    "risk_engine":  "risk:read",
    "loans":        "loans:read",
    "aml":          "aml:read",
}


@dataclass
class RetrievalManifest:
    intents:             List[str]
    sql_tables:          List[str]
    use_risk_engine:     bool
    use_fraud_engine:    bool
    use_vector_db:       bool
    use_codebase_store:  bool
    entity_refs:         dict              # customer_id, days_back, amount_ref, etc.
    multi_source:        bool
    rbac_blocked_sources: List[str] = field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────────────────

def build_retrieval_manifest(
    query: str,
    customer_id: Optional[str],
    permissions: Set[str],
    conversation_history: list | None = None,
) -> RetrievalManifest:
    """
    Classify query → resolve sources → RBAC pre-filter → return manifest.
    Called once at the top of every chat request before retrieval starts.
    """
    intents = classify_intents(query, max_intents=3)

    # Union of all SQL tables needed
    sql_tables: list[str] = list({
        t
        for intent in intents
        if needs_db_data(intent)
        for t in _INTENT_TABLES.get(intent, [])
    })

    use_risk   = any(i in _RISK_ENGINE_INTENTS   for i in intents)
    use_fraud  = any(i in _FRAUD_ENGINE_INTENTS  for i in intents)
    use_vector = (
        any(i in _VECTOR_INTENTS for i in intents)
        or not sql_tables          # always fall back to vector when no SQL data
    )
    use_code   = any(i in _CODE_INTENTS for i in intents)

    # RBAC pre-filter — remove sources this role may not access
    blocked: list[str] = []

    if use_fraud and "fraud:read" not in permissions:
        use_fraud = False
        blocked.append("fraud_engine")

    if use_risk and "risk:read" not in permissions:
        use_risk = False
        blocked.append("risk_engine")

    if "loans" in sql_tables and "loans:read" not in permissions:
        sql_tables = [t for t in sql_tables if t != "loans"]
        blocked.append("loans_db")

    # Entity extraction
    entity_refs = _extract_entities(query, customer_id, conversation_history or [])

    multi_source = (
        (bool(sql_tables) and (use_vector or use_risk or use_fraud))
        or len(sql_tables) > 1
    )

    return RetrievalManifest(
        intents=intents,
        sql_tables=sql_tables,
        use_risk_engine=use_risk,
        use_fraud_engine=use_fraud,
        use_vector_db=use_vector,
        use_codebase_store=use_code,
        entity_refs=entity_refs,
        multi_source=multi_source,
        rbac_blocked_sources=blocked,
    )


# ── Entity extraction ─────────────────────────────────────────────────────────

_AMOUNT_RE   = re.compile(r"\$?([\d,]+\.?\d*)\s*(thousand|million|billion|k|m|b)?", re.IGNORECASE)
_DAYS_RE     = re.compile(r"last\s+(\d+)\s+days?", re.IGNORECASE)
_WEEKS_RE    = re.compile(r"last\s+(\d+)\s+weeks?", re.IGNORECASE)
_MONTHS_RE   = re.compile(r"last\s+(\d+)\s+months?", re.IGNORECASE)

_MULTIPLIERS = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "b": 1e9}


def _extract_entities(
    query: str,
    customer_id: Optional[str],
    history: list,
) -> dict:
    entities: dict = {"customer_id": customer_id, "original_query": query}

    # Amount reference
    m = _AMOUNT_RE.search(query)
    if m:
        raw = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").lower()
        entities["amount_ref"] = raw * _MULTIPLIERS.get(suffix, 1.0)

    # Date range: days
    m = _DAYS_RE.search(query)
    if m:
        entities["days_back"] = int(m.group(1))
    else:
        m = _WEEKS_RE.search(query)
        if m:
            entities["days_back"] = int(m.group(1)) * 7
        else:
            m = _MONTHS_RE.search(query)
            if m:
                entities["days_back"] = int(m.group(1)) * 30

    return entities
