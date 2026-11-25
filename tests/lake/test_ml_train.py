"""LightGBM training, calibration, reasons and the gate on synthetic data (no Spark)."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from trustnova_ml import train as tr
from trustnova_ml.features import FEATURES


def synthetic(n: int, seed: int) -> pd.DataFrame:
    """Laundering is driven by fan-out and the structuring band; everything else is noise."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({f: rng.random(n) for f in FEATURES})
    df["payment_format_code"] = rng.integers(0, 7, n).astype(float)
    df["s_entity_type_code"] = rng.integers(0, 4, n).astype(float)
    df["r_entity_type_code"] = rng.integers(0, 4, n).astype(float)
    df["s_p1_cp_out"] = rng.poisson(1.0, n).astype(float)
    df["in_band"] = (rng.random(n) < 0.05).astype(float)
    logit = -6 + 1.2 * df["s_p1_cp_out"] + 3.0 * df["in_band"]
    df["label"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    patterns = np.where(df["s_p1_cp_out"] > 2, "FAN-OUT", np.where(df["in_band"] == 1, "STACK", "OTHER"))
    df["pattern"] = np.where(df["label"] == 1, patterns, None)
    return df


@pytest.fixture(scope="module")
def data():
    return synthetic(40000, 1), synthetic(8000, 2), synthetic(8000, 3)


@pytest.fixture(scope="module")
def m1(data):
    train, valid, _ = data
    return tr.train_m1(train, valid, rounds=300, patience=30)


def test_m1_learns_the_signal(m1, data):
    from sklearn.metrics import roc_auc_score

    test = data[2]
    auc = roc_auc_score(test["label"], m1.predict(test[list(FEATURES)]))
    assert auc > 0.85
    importance = dict(zip(m1.feature_name(), m1.feature_importance("gain"), strict=True))
    assert max(importance, key=importance.get) in ("s_p1_cp_out", "in_band")


def test_calibration_is_monotone_and_bounded():
    rows = [(0.1, 1, 99), (0.3, 5, 95), (0.5, 4, 96), (0.8, 40, 60)]  # a dip at 0.5 must be smoothed out
    cal = tr.fit_calibration(rows, 0.1)
    out = tr.calibrate(np.array([0.0, 0.15, 0.35, 0.55, 0.85, 1.0]), cal)
    assert all(np.diff(out) >= 0) and out.min() >= 0 and out.max() <= 1
    assert out[-1] == pytest.approx(0.4)


def test_reasons_name_the_features_that_raised_the_score(m1, data):
    test = data[2]
    risky = test.assign(s_p1_cp_out=6.0, in_band=1.0).head(3)
    reasons = tr.top_reasons(m1, risky)
    assert len(reasons) == 3 and all(len(r) <= 5 for r in reasons)
    assert {"s_p1_cp_out", "in_band"} & {x["feature"] for x in reasons[0]}
    assert all(x["contribution"] > 0 for r in reasons for x in r)


def test_a_model_trained_on_an_older_feature_list_still_scores_and_explains(data):
    """Production scoring must keep working with the champion after FEATURES grows: models read their own inputs."""
    import lightgbm as lgb

    pytest.importorskip("pyspark")
    from trustnova_ml.jobs import _scorer

    train, _, test = data
    old = [f for f in FEATURES if not f.endswith(("ach_new_in", "entity_type_code"))]
    booster = lgb.train({"objective": "binary", "verbose": -1, "num_leaves": 7}, lgb.Dataset(train[old], train["label"]), 20)
    rows = test.assign(variant="HIS", split="test", rule_score=0.0).head(50)
    scored = next(_scorer(booster.model_to_string())(iter([rows.copy()])))
    assert scored["raw"].to_numpy() == pytest.approx(booster.predict(rows[old]))
    assert len(tr.top_reasons(booster, rows.head(3))) == 3


def test_gate_requires_beating_the_baseline_everywhere():
    good = {"pr_auc": 0.4, "recall_at_top_0.5pct": 0.5, "positives": 10}
    base = {"pr_auc": 0.1, "recall_at_top_0.5pct": 0.2, "positives": 10}
    ok, reasons = tr.gate({"ALL": good, "HIS": good}, {"ALL": base, "HIS": base}, ["ALL", "HIS"])
    assert ok and reasons == []
    ok, reasons = tr.gate({"ALL": good, "HIS": {**good, "pr_auc": 0.05}}, {"ALL": base, "HIS": base}, ["ALL", "HIS"])
    assert not ok and "HIS: PR-AUC" in reasons[0]
    ok, reasons = tr.gate({"ALL": good}, {"ALL": base}, ["ALL", "LIS"])
    assert not ok and "LIS: missing metrics" in reasons


def test_banned_columns_can_never_become_features(monkeypatch):
    tr.check_features()
    with pytest.raises(ValueError, match="variant"):
        tr.check_features((*FEATURES, "variant"))
    with pytest.raises(ValueError, match="is_laundering"):
        tr.check_features(("is_laundering",))


def test_m3_learns_patterns_and_beats_guessing(data):
    train, valid, test = data
    pos = [d[d.label == 1] for d in (train, valid, test)]
    m3 = tr.train_m3(pos[0], pos[1], rounds=200, patience=20)
    report = tr.evaluate_m3(m3, pos[2])
    assert report["macro_f1"] > report["majority_class_macro_f1"]
    assert report["per_pattern"]["FAN-OUT"]["recall"] > 0.5


# ---------------------------------------------------------------- stage 1 out-of-fold scores (risk memory)
def test_folds_keep_an_attempt_together_and_are_stable():
    keys = pd.Series(["HIS-P1", "HIS-P1", "HIS-P2", "t9", "HIS-P1"])
    f = tr.fold_of(keys, 3)
    assert f[0] == f[1] == f[4]
    assert (tr.fold_of(keys, 3) == f).all() and set(f) <= {0, 1, 2}


def test_out_of_fold_scores_are_honest_where_in_sample_scores_are_not():
    """Labels are pure noise. A model scoring its own training rows still looks good (it memorised them);
    out-of-fold scores must not, because stage 2 has to learn from scores like the ones it will see live."""
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(5)
    df = synthetic(6000, 4)
    df["label"] = (rng.random(len(df)) < 0.2).astype(int)
    keys = pd.Series([f"t{i}" for i in range(len(df))])
    oof = tr.out_of_fold(df, keys, rounds=200)
    assert len(oof) == len(df)
    in_sample = tr.lgb.train(tr.M1_PARAMS, tr._dataset(df, "label"), 200).predict(df[list(FEATURES)])
    assert roc_auc_score(df["label"], in_sample) > 0.9
    assert roc_auc_score(df["label"], oof) < 0.6


def test_a_two_stage_feature_list_trains_and_is_checked():
    from trustnova_ml.memory import MEMORY_FEATURES

    train, valid = synthetic(4000, 6), synthetic(1000, 7)
    for d in (train, valid):
        for c in MEMORY_FEATURES:
            d[c] = 0.0
    feats = (*FEATURES, *MEMORY_FEATURES)
    booster = tr.train_m1(train, valid, rounds=20, patience=5, features=feats)
    assert booster.feature_name() == list(feats)
    with pytest.raises(ValueError):
        tr.train_m1(train, valid, rounds=5, features=(*feats, "attempt_id"))
