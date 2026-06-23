"""
Query Rewriter — resolves vague, context-dependent queries into self-contained ones.

Mechanical analogy: a customer calls the workshop and says "check it again".
The service advisor rewrites this on the job card as:
  "Re-inspect 2021 Toyota Camry engine noise — Customer: Raj — Last visit: Mon"

Two-step process:
  Step 1 — Fast regex check: does this query NEED rewriting?
            If no pronouns / vague refs → return as-is (zero latency, no LLM call).
  Step 2 — LLM rewrite: expand vague references using session history + entity state.
            Uses the cheapest/fastest model to keep latency low.

Examples:
  "What are his loans?"           → "What are the loans for customer John Smith (ID: CID-001)?"
  "Is she still flagged?"         → "Is customer Maria Garcia (ID: CID-002) still flagged for fraud?"
  "Show me the latest balance"    → "Show me the current account balance for John Smith (ID: CID-001)"
  "What about the account?"       → "What are the account details for John Smith (ID: CID-001)?"
  "Tell me more about the risk"   → "Tell me more about the risk profile for John Smith (ID: CID-001)"
"""
from __future__ import annotations

import re
from typing import List, Optional

from src.rag.entity_memory import EntityState


# ── Vague reference patterns — if ANY match, rewrite is triggered ─────────────

_VAGUE_PATTERNS = [
    # Pronouns
    r"\b(he|she|his|her|him|they|their|them|it|its)\b",
    # Demonstratives
    r"\b(this|that|these|those)\s+(customer|client|account|loan|transaction|alert)\b",
    # Definite article implying prior context
    r"\bthe\s+(customer|client|account|loan|transaction|balance|risk|fraud|profile)\b",
    # Elliptical queries — no subject at all
    r"^(what about|tell me more|show me more|more details|any updates|what's the status)\b",
    # Continuation cues
    r"\b(also|additionally|furthermore|and what about)\b",
]

_VAGUE_RE = re.compile("|".join(_VAGUE_PATTERNS), re.IGNORECASE)


def needs_rewrite(query: str) -> bool:
    """
    Fast check — returns True only if query contains vague/pronoun references.
    No LLM call. Typically < 1ms.
    """
    return bool(_VAGUE_RE.search(query.strip()))


def rewrite_query(
    query: str,
    entity_state: EntityState,
    session_history: List[dict],
) -> str:
    """
    Rewrite a vague query into a self-contained one using entity state + history.

    Tries fast rule-based rewrite first.
    Falls back to LLM rewrite only for complex cases.
    Always returns a usable string — never raises.

    Args:
        query:           original user query
        entity_state:    active customer context from entity_memory
        session_history: last N conversation turns

    Returns:
        rewritten query string (or original if rewrite fails / not needed)
    """
    if not needs_rewrite(query):
        return query

    # ── Fast rule-based rewrite (no LLM) ────────────────────────────────────
    fast = _fast_rewrite(query, entity_state)
    if fast:
        return fast

    # ── LLM rewrite for complex cases ────────────────────────────────────────
    return _llm_rewrite(query, entity_state, session_history)


# ── Fast rule-based rewrite ───────────────────────────────────────────────────

def _fast_rewrite(query: str, state: EntityState) -> Optional[str]:
    """
    Replace pronouns with known customer reference if entity state is populated.
    Works for the majority of simple follow-up questions.
    """
    if not state.has_customer():
        return None

    ref = _customer_ref(state)

    # Replace possessive pronouns
    rewritten = re.sub(
        r"\b(his|her|their|its)\b",
        f"{ref}'s",
        query,
        flags=re.IGNORECASE,
    )
    # Replace subject pronouns
    rewritten = re.sub(
        r"\b(he|she|they|it)\b",
        ref,
        rewritten,
        flags=re.IGNORECASE,
    )
    # Replace object pronouns
    rewritten = re.sub(
        r"\b(him|them)\b",
        ref,
        rewritten,
        flags=re.IGNORECASE,
    )
    # Append customer reference to bare "the customer / the client" phrases
    rewritten = re.sub(
        r"\bthe\s+(customer|client)\b",
        ref,
        rewritten,
        flags=re.IGNORECASE,
    )

    # Only return if we actually changed something meaningful
    return rewritten if rewritten.lower() != query.lower() else None


def _customer_ref(state: EntityState) -> str:
    """Build a compact customer reference string."""
    if state.customer_name and state.customer_id:
        return f"{state.customer_name} (ID: {state.customer_id})"
    if state.customer_name:
        return state.customer_name
    if state.customer_id:
        return f"customer {state.customer_id}"
    return "the customer"


# ── LLM rewrite ───────────────────────────────────────────────────────────────

_REWRITE_SYSTEM = (
    "You are a query clarification assistant for a banking AI system. "
    "Your only job is to rewrite vague follow-up questions into self-contained, "
    "explicit questions using the conversation context provided. "
    "\n\nRules:"
    "\n- Replace ALL pronouns (he/she/his/her/it/they/them) with explicit customer names/IDs"
    "\n- Keep the rewritten question short and precise"
    "\n- Do NOT answer the question — only rewrite it"
    "\n- If the original question is already clear, return it unchanged"
    "\n- Output ONLY the rewritten question, nothing else"
)


def _llm_rewrite(
    query: str,
    entity_state: EntityState,
    session_history: List[dict],
) -> str:
    """
    Use a lightweight LLM call to rewrite complex vague queries.
    Uses the 'lookup' task type (cheapest/fastest model).
    Falls back to original query on any error — never raises.
    """
    try:
        from src.api.llm_router import route

        # Build context block
        context_lines: list[str] = []
        if entity_state.customer_id:
            context_lines.append(f"Active customer ID   : {entity_state.customer_id}")
        if entity_state.customer_name:
            context_lines.append(f"Active customer name : {entity_state.customer_name}")
        if entity_state.last_intent:
            context_lines.append(f"Last discussed topic : {entity_state.last_intent}")

        # Last 3 conversational turns (user + assistant only)
        recent = [
            m for m in session_history[-6:]
            if m.get("role") in ("user", "assistant")
        ]
        if recent:
            context_lines.append("\nRecent conversation:")
            for m in recent:
                role = "Banker" if m["role"] == "user" else "AI"
                context_lines.append(f"  {role}: {m.get('content', '')[:120]}")

        context_block = "\n".join(context_lines)

        prompt = (
            f"{_REWRITE_SYSTEM}\n\n"
            f"CONTEXT:\n{context_block}\n\n"
            f"VAGUE QUERY: {query}\n\n"
            f"REWRITTEN QUERY (output ONLY the rewritten question, nothing else):"
        )

        result    = route("lookup", prompt)
        rewritten = result.get("response", "").strip()

        # Sanity: non-empty and not excessively longer than the original
        if not rewritten or len(rewritten) > len(query) * 5:
            return query

        return rewritten

    except Exception:
        return query   # always safe fallback
