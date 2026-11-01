"""Metrics from binned counts must agree with the row-level definitions."""

import numpy as np
import pytest
from sklearn.metrics import average_precision_score

from trustnova_ml import metrics as mx


def curve_from_rows(scores, labels):
    rows = {}
    for s, y in zip(scores, labels, strict=True):
        p, n = rows.get(s, (0, 0))
        rows[s] = (p + y, n + (1 - y))
    return mx.Curve.from_counts((s, p, n) for s, (p, n) in rows.items())


def test_average_precision_matches_sklearn():
    rng = np.random.default_rng(3)
    y = rng.random(5000) < 0.02
    s = np.round(np.clip(rng.normal(0.2 + 0.5 * y, 0.15), 0, 1), 3)  # rounding creates ties, like bins do
    c = curve_from_rows(s.tolist(), y.astype(int).tolist())
    assert mx.average_precision(c) == pytest.approx(average_precision_score(y, s), abs=1e-9)


def test_threshold_metrics():
    c = mx.Curve.from_counts([(0.9, 8, 2), (0.5, 2, 18), (0.1, 0, 970)])
    at = mx.at_threshold(c, 0.5)
    assert (at.precision, at.recall, at.flagged) == (10 / 30, 1.0, 30)
    assert mx.best_f1_threshold(c) == 0.9  # F1 0.8 beats 0.5 at the lower threshold
    assert mx.at_threshold(c, 0.95).recall == 0.0


def test_recall_within_an_alert_budget():
    c = mx.Curve.from_counts([(0.9, 8, 2), (0.5, 2, 18), (0.1, 0, 970)])
    assert mx.recall_at_fraction(c, 0.01) == pytest.approx(0.8)          # top 10 rows = the first bin
    assert mx.recall_at_fraction(c, 0.02) == pytest.approx(0.8 + 0.2 * 10 / 20)  # half of the second bin
    assert mx.recall_at_fraction(mx.Curve.from_counts([(0.5, 0, 10)]), 0.5) == 0.0


def test_counts_for_the_same_score_are_merged():
    c = mx.Curve.from_counts([(0.5, 1, 2), (0.7, 1, 0), (0.5, 3, 4)])
    assert list(c.upper) == [0.7, 0.5] and list(c.pos) == [1, 4] and list(c.neg) == [0, 6]
    s = mx.summary(c, 0.5)
    assert s["positives"] == 5 and s["rows"] == 11 and "recall_at_top_0.5pct" in s
