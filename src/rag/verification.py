"""
Verification Layer — validates LLM responses against the SQL snapshot
captured during retrieval to catch hallucinated financial values.

Two-stage check:
  Stage 1 — Numeric consistency: extract dollar amounts / numbers from the
             response and confirm each appears in the SQL context (±1 % tolerance).
  Stage 2 — Semantic grounding: embed the response and source chunks, check
             cosine similarity.  Falls back gracefully if embeddings are
             unavailable.

Usage:
    result = verify_response(answer, sql_text_snapshot, source_chunks)
    if not result.passed:
        new_prompt = build_correction_prompt(query, answer, result.violations, context)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    passed:     bool
    confidence: float          # 0.0 – 1.0 (deducted per violation)
    violations: List[str] = field(default_factory=list)


# ── Regex patterns ────────────────────────────────────────────────────────────

# Matches: $1,234.56 | $12k | 45,000 | 99.5%
_DOLLAR_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(thousand|million|billion|k|m|b)?",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\b([\d,]{4,}(?:\.\d+)?)\b")  # bare numbers ≥ 4 digits

_MULTIPLIERS = {
    "thousand": 1_000, "k": 1_000,
    "million":  1_000_000, "m": 1_000_000,
    "billion":  1_000_000_000, "b": 1_000_000_000,
}

# Semantic similarity threshold: response must be at least this similar to sources
_SEMANTIC_THRESHOLD = 0.55
# Confidence deduction per numeric violation
_NUMERIC_PENALTY = 0.15
# Confidence deduction for failing semantic check
_SEMANTIC_PENALTY = 0.20


# ── Public API ────────────────────────────────────────────────────────────────

def verify_response(
    response: str,
    sql_text_snapshot: str,
    source_chunks: List[str],
    *,
    semantic_threshold: float = _SEMANTIC_THRESHOLD,
) -> VerificationResult:
    """
    Run both verification stages and return a VerificationResult.

    Args:
        response:          the LLM-generated answer
        sql_text_snapshot: raw SQL context captured during retrieval
        source_chunks:     vector doc chunks used as context
        semantic_threshold: minimum cosine similarity to pass stage 2
    """
    violations: list[str] = []
    confidence = 1.0

    # ── Stage 1: numeric consistency ─────────────────────────────────────────
    if sql_text_snapshot:
        known_values = _extract_all_numbers(sql_text_snapshot)
        response_values = _extract_dollar_amounts(response)

        for display_text, value in response_values.items():
            if value <= 1.0:       # ignore trivially small numbers (ratios, counts)
                continue
            is_known = any(
                abs(value - k) / (k + 1e-6) < 0.001   # 0.1 % tolerance (≈ $100 on $100k)
                for k in known_values
            )
            if not is_known:
                # Secondary check: does the raw string appear literally in the snapshot?
                raw_digits = re.sub(r"[^\d]", "", display_text)
                if raw_digits and raw_digits not in re.sub(r"[^\d]", "", sql_text_snapshot):
                    violations.append(
                        f"Unverifiable value '{display_text}' "
                        f"(≈{value:,.0f}) not found in SQL snapshot"
                    )
                    confidence -= _NUMERIC_PENALTY

    # ── Stage 2: semantic grounding (optional — graceful fallback) ───────────
    all_source_text = (sql_text_snapshot + " " + " ".join(source_chunks)).strip()
    if all_source_text:
        sim = _semantic_similarity(response, all_source_text)
        if sim is not None and sim < semantic_threshold:
            violations.append(
                f"Response semantic similarity to sources: {sim:.2f} "
                f"(threshold {semantic_threshold:.2f}) — possible hallucination"
            )
            confidence -= _SEMANTIC_PENALTY

    confidence = round(max(0.0, min(1.0, confidence)), 3)
    passed = len(violations) == 0 and confidence >= 0.70

    return VerificationResult(passed=passed, confidence=confidence, violations=violations)


def build_correction_prompt(
    original_query: str,
    failed_response: str,
    violations: List[str],
    fused_context: str,
) -> str:
    """Build a re-generation prompt that tells the LLM exactly what was wrong."""
    violation_text = "\n".join(f"  • {v}" for v in violations)
    return (
        f"Your previous response contained the following errors:\n{violation_text}\n\n"
        f"ORIGINAL QUESTION: {original_query}\n\n"
        f"AUTHORITATIVE CONTEXT (use ONLY this):\n{fused_context}\n\n"
        f"PREVIOUS (INCORRECT) RESPONSE — do NOT repeat this:\n{failed_response}\n\n"
        "Generate a corrected response that strictly uses only the context above. "
        "If a specific value is not present in the context, "
        "say 'Data not available in current context.' — never invent it."
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_dollar_amounts(text: str) -> dict[str, float]:
    """Return {display_string: numeric_value} for all dollar amounts in text."""
    results: dict[str, float] = {}
    for m in _DOLLAR_RE.finditer(text):
        raw   = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").lower()
        value  = raw * _MULTIPLIERS.get(suffix, 1.0)
        results[m.group(0).strip()] = value
    return results


def _extract_all_numbers(text: str) -> list[float]:
    """Extract all numeric values from text (dollar + bare numbers)."""
    values: list[float] = []

    for m in _DOLLAR_RE.finditer(text):
        raw  = float(m.group(1).replace(",", ""))
        suf  = (m.group(2) or "").lower()
        values.append(raw * _MULTIPLIERS.get(suf, 1.0))

    for m in _NUMBER_RE.finditer(text):
        try:
            values.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass

    return values


def _semantic_similarity(text_a: str, text_b: str) -> Optional[float]:
    """
    Compute cosine similarity between two texts using the project's embeddings.
    Returns None if embeddings are unavailable (graceful fallback).
    Uses get_embeddings() with local_files_only=True to avoid slow downloads on
    the hot response path.
    """
    try:
        import numpy as np
        from src.rag.embeddings import get_embeddings

        embedder = get_embeddings(local_files_only=True)
        emb_a = embedder.embed_query(text_a[:2000])
        emb_b = embedder.embed_query(text_b[:2000])

        a = np.array(emb_a, dtype=float)
        b = np.array(emb_b, dtype=float)
        dot   = float(np.dot(a, b))
        norms = float(np.linalg.norm(a) * np.linalg.norm(b))
        return dot / norms if norms > 0 else 0.0

    except Exception:
        return None
