"""
Context Fusion — merges parallel retrieval results into a single structured
prompt context block.

Source priority:
  SQL (primary truth) → Fraud Engine → Vector (policy docs) → Codebase

Each section is clearly labelled with its authority level so the LLM knows
structured DB values always override document evidence.
"""
from __future__ import annotations

from typing import List, Optional

from src.rag.parallel_retriever import SourceResult

# Order in which sections appear in the fused prompt
_SECTION_ORDER = ["sql", "fraud_engine", "vector", "codebase"]

_AUTHORITY = {
    "sql":          "PRIMARY TRUTH — structured database",
    "fraud_engine": "SUPPORTING — computed from live DB",
    "vector":       "SUPPORTING — policy / document evidence (explanatory only)",
    "codebase":     "REFERENCE — feature definitions",
}

_FRESHNESS_WARN_THRESHOLD = 0.5

_SYSTEM_FOOTER = (
    "\n── REASONING RULES ──────────────────────────────────────────\n"
    "1. SOURCE: SQL values are authoritative. Never contradict them.\n"
    "2. SOURCE: VECTOR provides policy context only — not numerical truth.\n"
    "3. If a value is absent from the context above, say "
    "'Data not available in current context.' Do NOT invent it.\n"
    "4. Cite your source in every factual claim: [SQL], [Fraud Engine], [Policy Doc].\n"
    "5. RBAC HARD RULE: For sources marked ⚠ SOURCES BLOCKED BY ROLE PERMISSIONS —\n"
    "   do NOT speculate, infer, or reason about the blocked data from any other field.\n"
    "   Specifically: do NOT use a customer's AML risk rating, credit score, or any\n"
    "   unblocked field to deduce what a blocked source (e.g., fraud_engine) would say.\n"
    "   If asked about blocked data, respond: 'This information is not accessible with\n"
    "   your current role permissions. Please contact your compliance officer.'\n"
    "6. SCOPE RULE: Only answer questions within banking/financial services scope.\n"
    "   If the question is unrelated to banking, say so and decline to speculate.\n"
    "─────────────────────────────────────────────────────────────\n"
)


def fuse_context(
    results: List[SourceResult],
    blocked_sources: List[str],
    customer_id: Optional[str] = None,
) -> str:
    """
    Build the structured context string that gets injected into the LLM prompt.

    Args:
        results:         successful SourceResult objects from parallel_retrieve()
        blocked_sources: RBAC-blocked source names (shown as warnings)
        customer_id:     optional — shown in header for clarity
    """
    sections: list[str] = []

    # Header
    if customer_id:
        sections.append(f"═══ RETRIEVED CONTEXT — Customer: {customer_id} ═══\n")
    else:
        sections.append("═══ RETRIEVED CONTEXT ═══\n")

    # RBAC warnings
    if blocked_sources:
        sections.append(
            "⚠ SOURCES BLOCKED BY ROLE PERMISSIONS:\n"
            + "\n".join(f"  • {s}" for s in blocked_sources)
            + "\n"
        )

    # Index results by source_type for ordered emission
    result_map = {r.source_type: r for r in results}

    any_content = False
    for src_type in _SECTION_ORDER:
        result = result_map.get(src_type)
        if not result or not result.content.strip():
            continue

        any_content = True
        authority = _AUTHORITY.get(src_type, "SUPPORTING")
        freshness_note = ""
        if result.freshness_score < _FRESHNESS_WARN_THRESHOLD:
            freshness_note = (
                f"  ⚠ DATA MAY BE STALE "
                f"(freshness: {result.freshness_score:.0%})\n"
            )

        sections.append("─" * 64)
        sections.append(f"SOURCE: {src_type.upper()}")
        sections.append(f"AUTHORITY: {authority}")
        if freshness_note:
            sections.append(freshness_note)
        sections.append(result.content)
        sections.append("")

    if not any_content:
        sections.append(
            "No structured data retrieved. "
            "Answer from general banking knowledge only and flag any uncertainty.\n"
        )

    sections.append(_SYSTEM_FOOTER)
    return "\n".join(sections)


def build_system_prompt(role: str = "personal_banker") -> str:
    """Return the LLM system instruction that enforces grounding rules."""
    return (
        "You are TrustNova AI, an enterprise banking intelligence assistant. "
        "Your answers must be grounded strictly in the RETRIEVED CONTEXT provided. "
        "\n\nCORE RULES:"
        "\n• NEVER invent customer names, balances, amounts, IDs, or dates."
        "\n• Structured database values (SOURCE: SQL) always override document evidence."
        "\n• When a fact is missing from context, say 'Data not available.' — never guess."
        "\n• Always cite source: [SQL], [Fraud Engine], [Policy Doc], [Feature Ref]."
        "\n• For fields marked ⚠ ACCESS RESTRICTED: acknowledge restriction, do not speculate."
        f"\n\nYour role: {role}"
    )
