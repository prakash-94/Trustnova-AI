"""
TrustNova RBAC Filter — node-level access control for the AI Copilot.

Two enforcement layers applied BEFORE data reaches the LLM:

  Layer A — Intent-level blocking
    Maps each structured-data intent to the permission string it requires.
    If the current user lacks that permission, DB retrieval is skipped and a
    role-aware "access restricted" message is returned instead.

  Layer B — Field-level redaction
    Within allowed responses, sensitive customer profile fields (AML risk,
    PEP flag, sanctions status, KYC status) are redacted to [RESTRICTED] for
    roles that lack the corresponding fine-grained permission.

  Layer C — Document type filtering
    ChromaDB queries are narrowed by a metadata `doc_type` filter so roles
    without loans:read never receive loan policy chunks, etc.

All permission checks mirror the logic in src/api/auth.py (exact match,
category prefix match, and wildcard "*" for admin).
"""
from __future__ import annotations

import re
from typing import List, Optional

# ── Intent → minimum required permission ─────────────────────────────────────
# "general" and "trustnova_features" are intentionally absent — open to all.
INTENT_PERMISSIONS: dict[str, str] = {
    "fraud":       "fraud:read",
    "loan":        "loans:read",
    "trust_score": "risk:read",
    "risk":        "risk:read",
    "transaction": "transactions:read",
    "account":     "accounts:read",
    "customer":    "customers:read",
    "stats":       "reports:read",
}

# Human-readable labels used in denied messages
_INTENT_LABELS: dict[str, str] = {
    "fraud":       "fraud alert / investigation",
    "loan":        "loan portfolio",
    "trust_score": "trust score",
    "risk":        "risk profile",
    "transaction": "transaction",
    "account":     "account",
    "customer":    "customer profile",
    "stats":       "institution statistics",
}

# ── Customer profile field redaction ─────────────────────────────────────────
# Each entry: (regex pattern to match the line, required permission, label)
_CUSTOMER_FIELD_RULES: list[tuple[str, str, str]] = [
    # covers both "AML Risk :" (360 view) and "AML Risk Rating :" (_build_customer_context)
    (r"(AML Risk(?:\s+Rating)?\s*[:\|])\s*.+",  "aml:read", "aml:read"),
    (r"(PEP\s*[:\|])\s*.+",                      "aml:read", "aml:read"),
    (r"(Sanctioned\s*[:\|])\s*.+",               "aml:read", "aml:read"),
    (r"(KYC Status\s*[:\|])\s*.+",               "kyc:read", "kyc:read"),
]

# ── Document type → required permission ──────────────────────────────────────
# Doc types NOT in this map are unrestricted (visible to all authenticated roles).
DOC_TYPE_PERMISSIONS: dict[str, str] = {
    "loan_policy": "loans:read",
    "mortgage":    "loans:read",
}

# All doc_types that exist in the ChromaDB collection
_ALL_DOC_TYPES = [
    "compliance", "compliance_aml_kyc", "faq", "loan_policy", "mortgage",
    "product_sheet", "digital_banking", "wire_transfer", "business_banking",
    "wealth_management", "fee_schedule", "risk_fraud_security",
    "savings_products", "credit_card", "general",
]


# ── Core permission check (mirrors auth.py logic) ─────────────────────────────

def has_permission(user_permissions: List[str], required: str) -> bool:
    """
    Return True if `user_permissions` satisfies `required`.

    Matching rules (same as src/api/auth.py):
      1. Wildcard "*"  → admin, grants everything
      2. Exact match   → "loans:read" satisfies "loans:read"
      3. Category prefix → "loans:write" also satisfies "loans:read"
         because both share the "loans" category
    """
    required_category = required.split(":")[0]
    for p in user_permissions:
        if p == "*":
            return True
        if p == required:
            return True
        if p.startswith(required_category + ":"):
            return True
    return False


# ── Layer A — Intent-level blocking ──────────────────────────────────────────

def can_access_intent(intent: str, user_permissions: List[str]) -> bool:
    """Return True if the user is allowed to retrieve data for this intent."""
    required = INTENT_PERMISSIONS.get(intent)
    if required is None:
        return True  # general / trustnova_features — open to all
    return has_permission(user_permissions, required)


def build_denied_message(intent: str, role: str, role_label: str) -> str:
    """
    Build a role-aware, actionable permission-denied context block.
    This string is injected as the structured_context so the LLM can
    relay a helpful message to the user.
    """
    required   = INTENT_PERMISSIONS.get(intent, "unknown")
    entity     = _INTENT_LABELS.get(intent, intent)
    return (
        f"[ACCESS RESTRICTED]\n"
        f"Your role ({role_label}) does not have permission to view {entity} data.\n\n"
        f"Required permission : {required}\n"
        f"Your current role   : {role} ({role_label})\n\n"
        f"To access this information:\n"
        f"  • Submit a temporary access request via the Access Request portal\n"
        f"  • Contact your branch manager to escalate this case\n"
    )


# ── Layer B — Field-level redaction ──────────────────────────────────────────

def redact_customer_fields(text: str, user_permissions: List[str]) -> str:
    """
    Redact restricted customer profile fields in a formatted text block.

    Applied to the customer 360 / graph context output.  Roles that lack
    aml:read will see [RESTRICTED] instead of AML risk, PEP, and sanctions
    data; roles without kyc:read will not see KYC status.
    """
    for pattern, required_perm, perm_label in _CUSTOMER_FIELD_RULES:
        if not has_permission(user_permissions, required_perm):
            replacement = rf"\1 [RESTRICTED — requires {perm_label}]"
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ── Layer C — Document type filtering ────────────────────────────────────────

def get_doc_type_filter(user_permissions: List[str]) -> Optional[dict]:
    """
    Return a ChromaDB metadata `where` filter that restricts results to
    doc_types the user is permitted to see.

    Returns None when no restriction is needed (avoids unnecessary filtering).

    ChromaDB filter format: {"doc_type": {"$in": [...]}}
    """
    allowed: list[str] = []
    restricted: list[str] = []

    for doc_type in _ALL_DOC_TYPES:
        required = DOC_TYPE_PERMISSIONS.get(doc_type)
        if required is None or has_permission(user_permissions, required):
            allowed.append(doc_type)
        else:
            restricted.append(doc_type)

    if not restricted:
        return None  # nothing to restrict

    return {"doc_type": {"$in": allowed}}


# ── Convenience wrapper used by chat.py ──────────────────────────────────────

def apply_rbac(
    intent: str,
    structured_ctx: str,
    user_permissions: List[str],
    role: str,
    role_label: str,
) -> str:
    """
    Single entry point called after data retrieval.

    - If the user cannot access this intent: returns a denied message.
    - Otherwise: applies field-level redaction and returns cleaned context.

    Note: intent-level blocking should ideally prevent retrieval entirely
    (called BEFORE retrieve_structured_data), but this acts as a safety net.
    """
    if not can_access_intent(intent, user_permissions):
        return build_denied_message(intent, role, role_label)

    if intent in ("customer", "stats"):
        structured_ctx = redact_customer_fields(structured_ctx, user_permissions)

    return structured_ctx