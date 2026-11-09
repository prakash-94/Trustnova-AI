"""The single-pass evaluation report agrees with computing each metric on its own."""

import pytest

pytest.importorskip("pyspark")

from trustnova_ml import metrics as mx
from trustnova_ml.jobs import ALL, report_from_counts


def row(variant, split, bin_, rule, pattern, pos, neg):
    return {"variant": variant, "split": split, "bin": bin_, "rule_score": rule, "pattern": pattern, "pos": pos, "neg": neg}


ROWS = [
    # validation: a high bin with mostly laundering, a low bin with mostly normal rows
    row("HIS", "valid", 0.9, 0.0, "FAN-OUT", 8, 0), row("HIS", "valid", 0.9, 0.0, None, 0, 2),
    row("HIS", "valid", 0.1, 0.0, "OTHER", 2, 0), row("HIS", "valid", 0.1, 0.0, None, 0, 500),
    row("LIS", "valid", 0.9, 1.0, "CYCLE", 1, 0), row("LIS", "valid", 0.1, 0.0, None, 0, 300),
    # test: the same score bin split across rule scores and patterns, as the one grouped query returns it
    row("HIS", "test", 0.9, 0.0, "FAN-OUT", 5, 0), row("HIS", "test", 0.9, 1.0, "FAN-OUT", 1, 0),
    row("HIS", "test", 0.9, 0.0, None, 0, 1), row("HIS", "test", 0.1, 0.0, "OTHER", 4, 0),
    row("HIS", "test", 0.1, 0.0, None, 0, 400), row("LIS", "test", 0.9, 1.0, "CYCLE", 2, 0),
    row("LIS", "test", 0.1, 1.0, None, 0, 7), row("LIS", "test", 0.1, 0.0, None, 0, 200),
]


def test_report_from_one_grouped_pass():
    report = report_from_counts(ROWS, ["HIS", "LIS"])
    assert report["threshold_raw"] == 0.9
    his = report["model"]["HIS"]
    assert (his["positives"], his["rows"]) == (10, 411)
    assert his["at_flagged"] == 7 and his["at_recall"] == pytest.approx(0.6)  # 6 of 10 laundering rows in the 0.9 bin
    everything = mx.Curve.from_counts([(r["bin"], r["pos"], r["neg"]) for r in ROWS if r["split"] == "test"])
    assert report["model"][ALL]["pr_auc"] == pytest.approx(mx.average_precision(everything))
    assert report["baseline"]["LIS"]["positives"] == 2

    by_pattern = report["recall_by_pattern"]
    assert by_pattern["FAN-OUT"] == {"test_rows": 6, "model_recall": 1.0, "baseline_recall": pytest.approx(1 / 6)}
    assert by_pattern["OTHER"]["model_recall"] == 0.0
    assert by_pattern["CYCLE"] == {"test_rows": 2, "model_recall": 1.0, "baseline_recall": 1.0}
    assert sum(b[1] for b in report["valid_bins"]) == 11  # every validation laundering row, for calibration
