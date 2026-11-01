"""Detection metrics from binned score counts.

Spark reduces every scored row to counts per (group, score bin): positives and negatives. These functions turn those
counts into precision/recall metrics, so the same code evaluates 12M staging rows or 172M production test rows
without collecting them. Ties within a bin are treated as one threshold, as average-precision libraries do.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass

import numpy as np

BINS = 10000  # scores in [0, 1] are cut into 1e-4-wide bins


@dataclass(frozen=True)
class Curve:
    """Counts per score bin, ordered from the highest score to the lowest."""
    upper: np.ndarray  # the bin's score (its lower edge), descending
    pos: np.ndarray
    neg: np.ndarray

    @classmethod
    def from_counts(cls, rows: Iterable[tuple[float, int, int]]) -> "Curve":
        """rows: (bin score, positives, negatives); several rows for the same score are added together."""
        acc: dict[float, list[int]] = {}
        for s, p, n in rows:
            a = acc.setdefault(float(s), [0, 0])
            a[0] += int(p)
            a[1] += int(n)
        keys = sorted(acc, reverse=True)
        return cls(np.array(keys, dtype=float), np.array([acc[k][0] for k in keys]), np.array([acc[k][1] for k in keys]))

    @property
    def positives(self) -> int:
        return int(self.pos.sum())

    @property
    def total(self) -> int:
        return int(self.pos.sum() + self.neg.sum())


def average_precision(c: Curve) -> float:
    """Area under the precision-recall curve, as sum over thresholds of (recall gain x precision)."""
    if c.positives == 0:
        return 0.0
    tp, fp = np.cumsum(c.pos), np.cumsum(c.neg)
    precision = tp / np.maximum(tp + fp, 1)
    recall_gain = c.pos / c.positives
    return float(np.sum(recall_gain * precision))


@dataclass(frozen=True)
class AtThreshold:
    threshold: float
    precision: float
    recall: float
    f1: float
    flagged: int


def at_threshold(c: Curve, threshold: float) -> AtThreshold:
    """Flag everything scoring at or above `threshold`."""
    keep = c.upper >= threshold
    tp, fp = int(c.pos[keep].sum()), int(c.neg[keep].sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / c.positives if c.positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return AtThreshold(float(threshold), precision, recall, f1, tp + fp)


def best_f1_threshold(c: Curve) -> float:
    """The threshold with the highest F1 (chosen on validation data, then applied unchanged to test data)."""
    best, best_f1 = float(c.upper[0]) if len(c.upper) else 1.0, -1.0
    tp, fp = np.cumsum(c.pos), np.cumsum(c.neg)
    for i, s in enumerate(c.upper):
        p = tp[i] / (tp[i] + fp[i]) if tp[i] + fp[i] else 0.0
        r = tp[i] / c.positives if c.positives else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        if f1 > best_f1:
            best, best_f1 = float(s), f1
    return best


def recall_at_fraction(c: Curve, fraction: float) -> float:
    """Share of positives caught if the top `fraction` of rows were flagged (an alert budget). A bin cut by the budget
    contributes pro rata, so the result doesn't depend on how ties fall."""
    if c.positives == 0:
        return 0.0
    budget = fraction * c.total
    caught, used = 0.0, 0.0
    for p, n in zip(c.pos, c.neg, strict=True):
        size = p + n
        if used + size <= budget:
            caught += p
            used += size
        else:
            if size:
                caught += p * (budget - used) / size
            break
    return float(caught / c.positives)


BUDGETS = (0.001, 0.005)


def summary(c: Curve, threshold: float) -> dict:
    """Everything reported for one group on one split."""
    at = at_threshold(c, threshold)
    out = {"rows": c.total, "positives": c.positives, "pr_auc": average_precision(c), **{f"at_{k}": v for k, v in asdict(at).items()}}
    for b in BUDGETS:
        out[f"recall_at_top_{b * 100:g}pct"] = recall_at_fraction(c, b)
    return out
