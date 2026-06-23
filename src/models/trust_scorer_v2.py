"""
3-Layer Trust Score System — TrustNova AI v2.

Replaces the single unstable score with three distinct, explainable layers:

  Layer 1 — Risk Score  (0–100)   raw data truth — used internally by risk officers
  Layer 2 — Trust Score (85–99)   user-facing — derived deterministically from Risk Score
  Layer 3 — Confidence  (0–100)   AI model certainty — based on retrieval + verification quality

Formula:
  risk_score   = 100 − weighted_trust_components   (inverts existing trust_scorer.py)
  trust_score  = 99 − (risk_score / 100) × 14      (range: 85–99)
  confidence   = weighted average of 5 retrieval/verification signals

Backward compatible: wraps TrustScoreCalculator so existing trust_scores table
entries remain valid. New fields are additive.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


# ── Constants ─────────────────────────────────────────────────────────────────

TRUST_MIN   = 85.0   # minimum user-facing trust (worst customer still gets baseline)
TRUST_MAX   = 99.0   # maximum user-facing trust
TRUST_RANGE = TRUST_MAX - TRUST_MIN   # 14-point spread

CONFIDENCE_WEIGHTS = {
    "source_coverage":    0.25,   # fraction of requested sources that returned data
    "retrieval_quality":  0.25,   # avg relevance score of retrieved chunks
    "verification":       0.30,   # did post-generation verification pass?
    "citation_density":   0.10,   # [SQL] / [Fraud Engine] / [Policy Doc] tags in response
    "freshness_avg":      0.10,   # avg freshness across sources
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class TrustScoreV2:
    # Layer 1
    risk_score:       float          # 0–100 (0 = safe, 100 = extreme risk)
    risk_tier:        str            # "low" | "moderate" | "high" | "critical"
    # Layer 2
    trust_score:      float          # 85–99 (user-facing)
    trust_tier:       str            # "standard" | "preferred" | "premium"
    # Layer 3
    confidence_score: float          # 0–100 (AI model certainty)
    # Audit trail
    explainability:   Dict           # component breakdown for compliance/audit


# ── Layer 1 — Risk Score ──────────────────────────────────────────────────────

def compute_risk_score(trust_components: Dict[str, float]) -> tuple[float, str]:
    """
    Derive a Risk Score by inverting the existing trust score components.

    The existing TrustScoreCalculator produces component scores where HIGH = GOOD.
    Risk Score inverts this: high component → low risk, low component → high risk.

    Args:
        trust_components: dict of {component_name: score_0_to_100}
                          as returned by TrustScoreCalculator.calculate()["components"]

    Returns:
        (risk_score: 0–100, tier: str)
    """
    from src.models.trust_scorer import WEIGHTS

    # Weighted average of INVERTED component scores
    risk = sum(
        (100.0 - trust_components.get(k, 50.0)) * w
        for k, w in WEIGHTS.items()
    )
    risk = round(max(0.0, min(100.0, risk)), 1)
    return risk, _risk_tier(risk)


def _risk_tier(risk_score: float) -> str:
    if risk_score <= 25:  return "low"
    if risk_score <= 50:  return "moderate"
    if risk_score <= 75:  return "high"
    return "critical"


# ── Layer 2 — Trust Score ─────────────────────────────────────────────────────

def compute_trust_score(risk_score: float) -> tuple[float, str]:
    """
    Derive user-facing Trust Score from Risk Score.

    Formula: trust = 99 − (risk / 100) × 14

    Guarantees:
      risk = 0   → trust = 99.0  (maximum — perfectly safe customer)
      risk = 100 → trust = 85.0  (minimum — still a customer, not zero trust)
      Always in [85, 99]. Deterministic. Never manually assigned.

    Returns:
        (trust_score: 85–99, tier: str)
    """
    trust = round(TRUST_MAX - (risk_score / 100.0) * TRUST_RANGE, 1)
    trust = max(TRUST_MIN, min(TRUST_MAX, trust))
    return trust, _trust_tier(trust)


def _trust_tier(trust_score: float) -> str:
    if trust_score >= 97:   return "premium"
    if trust_score >= 92:   return "preferred"
    return "standard"


# ── Layer 3 — Confidence Score ────────────────────────────────────────────────

def compute_confidence_score(
    sources_succeeded:    int,
    sources_attempted:    int,
    avg_retrieval_score:  float,      # 0–1 from reranker / similarity scores
    verification_conf:    float,      # 0–1 from verification.VerificationResult.confidence
    citation_count:       int,        # number of [SQL]/[Policy Doc] tags in LLM answer
    avg_freshness:        float,      # 0–1 average freshness across SourceResults
) -> float:
    """
    Compute AI model certainty score (0–100).

    This measures the QUALITY of the AI's answer, not the customer's riskiness.
    """
    source_coverage = sources_succeeded / max(sources_attempted, 1)

    components = {
        "source_coverage":   min(source_coverage, 1.0) * 100,
        "retrieval_quality": min(avg_retrieval_score, 1.0) * 100,
        "verification":      verification_conf * 100,
        "citation_density":  min(citation_count / 3.0, 1.0) * 100,
        "freshness_avg":     avg_freshness * 100,
    }

    score = round(
        sum(components[k] * CONFIDENCE_WEIGHTS[k] for k in CONFIDENCE_WEIGHTS), 1
    )
    return max(0.0, min(100.0, score))


# ── Master scorer ─────────────────────────────────────────────────────────────

def compute_all_scores(
    customer_id: str,
    retrieval_meta: Dict,
    verification_conf: float = 1.0,
) -> Optional[TrustScoreV2]:
    """
    Compute all 3 layers for a customer.

    Args:
        customer_id:      customer to score
        retrieval_meta:   dict with keys:
                            sources_succeeded, sources_attempted,
                            avg_retrieval_score, citation_count, avg_freshness
        verification_conf: confidence from VerificationResult (0–1)

    Returns:
        TrustScoreV2 or None if customer not found
    """
    try:
        from src.models.trust_scorer import TrustScoreCalculator

        calc   = TrustScoreCalculator()
        result = calc.calculate(customer_id)

        if "error" in result:
            return None

        components = result.get("components", {})

        # Layer 1
        risk_score, risk_tier = compute_risk_score(components)

        # Layer 2
        trust_score, trust_tier = compute_trust_score(risk_score)

        # Layer 3
        confidence = compute_confidence_score(
            sources_succeeded   = retrieval_meta.get("sources_succeeded", 1),
            sources_attempted   = retrieval_meta.get("sources_attempted", 1),
            avg_retrieval_score = retrieval_meta.get("avg_retrieval_score", 0.6),
            verification_conf   = verification_conf,
            citation_count      = retrieval_meta.get("citation_count", 0),
            avg_freshness       = retrieval_meta.get("avg_freshness", 0.9),
        )

        return TrustScoreV2(
            risk_score=risk_score,
            risk_tier=risk_tier,
            trust_score=trust_score,
            trust_tier=trust_tier,
            confidence_score=round(confidence, 1),
            explainability={
                "trust_components":  {k: round(v, 1) for k, v in components.items()},
                "risk_formula":      f"100 − weighted_trust_components = {risk_score}",
                "trust_formula":     f"99 − ({risk_score}/100 × 14) = {trust_score}",
                "confidence_inputs": retrieval_meta,
                "base_trust_score":  result.get("score"),   # legacy score for comparison
                "base_tier":         result.get("tier"),
            },
        )

    except Exception:
        return None


# ── Formatting helper ─────────────────────────────────────────────────────────

def format_scores(scores: TrustScoreV2) -> str:
    """Human-readable summary for logs and debug output."""
    bar = lambda v, w=20: "█" * int(v / 100 * w) + "░" * (w - int(v / 100 * w))
    return (
        f"\nRisk Score  : {scores.risk_score:5.1f}/100  {bar(scores.risk_score)}  [{scores.risk_tier}]\n"
        f"Trust Score : {scores.trust_score:5.1f}/100  {bar(scores.trust_score)}  [{scores.trust_tier}]\n"
        f"Confidence  : {scores.confidence_score:5.1f}/100  {bar(scores.confidence_score)}\n"
        f"Formula     : {scores.explainability['trust_formula']}\n"
    )
