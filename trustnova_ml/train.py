"""LightGBM models, calibration, reason codes and the promotion gate. Plain pandas / LightGBM: no Spark here.

M1 (transaction risk) trains on every laundering transaction plus a sample of normal ones (about 50 per laundering
transaction), so its raw scores overstate risk. Isotonic calibration on the untouched validation split maps them
back to real probabilities. M3 (pattern type) trains on laundering transactions only.
"""

from collections.abc import Mapping, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from trustnova_lake.ibm import PATTERN_TYPES
from trustnova_ml.features import BANNED, CATEGORICAL, FEATURES

PATTERN_CLASSES = (*PATTERN_TYPES, "OTHER")
NEGATIVES_PER_POSITIVE = 50
GATE_BUDGET = "recall_at_top_0.5pct"
STAGE1_FOLDS = 3  # out-of-fold stage-1 scores for the training sample (see memory.py)

M1_PARAMS = {
    "objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 40,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "verbose": -1, "seed": 7, "deterministic": True, "num_threads": 4,
}
M3_PARAMS = {
    "objective": "multiclass", "num_class": len(PATTERN_CLASSES), "learning_rate": 0.05, "num_leaves": 31,
    "min_data_in_leaf": 10, "feature_fraction": 0.8, "lambda_l2": 1.0, "verbose": -1, "seed": 7,
    "deterministic": True, "num_threads": 4,
}


def check_features(features: Sequence[str] = FEATURES) -> None:
    """Fails if a label, pattern id, `variant` or a synthetic profile field is about to become a model input."""
    leaked = sorted(set(features) & set(BANNED))
    if leaked:
        raise ValueError(f"banned columns in the feature list: {leaked}")


def _dataset(df: pd.DataFrame, label: str, reference: lgb.Dataset | None = None,
             features: Sequence[str] = FEATURES) -> lgb.Dataset:
    return lgb.Dataset(df[list(features)], label=df[label], categorical_feature=[c for c in CATEGORICAL if c in features],
                       reference=reference, free_raw_data=False)


def train_m1(train: pd.DataFrame, valid: pd.DataFrame, rounds: int = 2000, patience: int = 100,
             features: Sequence[str] = FEATURES) -> lgb.Booster:
    check_features(features)
    dtrain = _dataset(train, "label", features=features)
    dvalid = _dataset(valid, "label", dtrain, features=features)
    return lgb.train(M1_PARAMS, dtrain, rounds, valid_sets=[dvalid],
                     callbacks=[lgb.early_stopping(patience, verbose=False)])


def fold_of(keys: pd.Series, folds: int) -> np.ndarray:
    """A stable fold number per row from a grouping key (the laundering attempt, or the transaction itself), so all
    payments of one attempt land in the same fold and re-runs agree."""
    return (pd.util.hash_pandas_object(keys.astype(str), index=False).to_numpy() % folds).astype(int)


def out_of_fold(train: pd.DataFrame, keys: pd.Series, rounds: int, folds: int = STAGE1_FOLDS,
                features: Sequence[str] = FEATURES) -> np.ndarray:
    """Stage-1 scores for the training rows from models that never saw them (or any payment of the same attempt).

    A model's scores on its own training rows are too confident; stage 2 must learn from scores that look like the
    ones it will meet on new data. Each fold is scored by a model trained on the other folds for `rounds` trees
    (the full model's best iteration, so no early-stopping data is needed)."""
    check_features(features)
    fold = fold_of(keys, folds)
    out = np.zeros(len(train))
    for k in range(folds):
        fit, held = fold != k, fold == k
        if not held.any():
            continue
        booster = lgb.train(M1_PARAMS, _dataset(train[fit], "label", features=features), max(1, rounds))
        out[held] = booster.predict(train.loc[held, list(features)])
    return out


def fit_calibration(rows: Sequence[tuple[float, int, int]], bin_width: float) -> dict:
    """Isotonic map from raw score to probability, fitted on validation counts per raw-score bin."""
    x = np.array([r[0] + bin_width / 2 for r in rows], dtype=float)
    pos = np.array([r[1] for r in rows], dtype=float)
    neg = np.array([r[2] for r in rows], dtype=float)
    n = pos + neg
    keep = n > 0
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(x[keep], (pos[keep] / n[keep]), sample_weight=n[keep])
    return {"x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_]}


def calibrate(raw: np.ndarray, calibration: Mapping) -> np.ndarray:
    return np.interp(np.asarray(raw, dtype=float), calibration["x"], calibration["y"])


def top_reasons(booster: lgb.Booster, features: pd.DataFrame, k: int = 5) -> list[list[dict]]:
    """The k features pushing each row's score up the most (LightGBM's own per-feature contributions)."""
    names = booster.feature_name()  # the model's own inputs, which may predate the current FEATURES
    x = features[names]
    contrib = np.asarray(booster.predict(x, pred_contrib=True))[:, :-1]  # the last column is the bias term
    values = x.to_numpy(dtype=float)
    out = []
    for r, row in enumerate(contrib):
        order = np.argsort(-row)[:k]
        out.append([{"feature": names[i], "contribution": round(float(row[i]), 4), "value": float(values[r, i])}
                    for i in order if row[i] > 0])
    return out


def gate(model: Mapping[str, Mapping], baseline: Mapping[str, Mapping], groups: Sequence[str]) -> tuple[bool, list[str]]:
    """The model may become a candidate only if it beats the rule baseline on test data, overall and in every
    simulation, on both PR-AUC and recall within the alert budget."""
    reasons = []
    for g in groups:
        m, b = model.get(g), baseline.get(g)
        if not m or not b:
            reasons.append(f"{g}: missing metrics")
            continue
        if m["positives"] == 0:
            reasons.append(f"{g}: no laundering in the test split")
            continue
        if not m["pr_auc"] > b["pr_auc"]:
            reasons.append(f"{g}: PR-AUC {m['pr_auc']:.4f} does not beat the baseline {b['pr_auc']:.4f}")
        if not m[GATE_BUDGET] >= b[GATE_BUDGET]:
            reasons.append(f"{g}: {GATE_BUDGET} {m[GATE_BUDGET]:.4f} is below the baseline {b[GATE_BUDGET]:.4f}")
    return not reasons, reasons


def train_m3(train_pos: pd.DataFrame, valid_pos: pd.DataFrame, rounds: int = 500, patience: int = 50,
             features: Sequence[str] = FEATURES) -> lgb.Booster:
    """Pattern classifier on laundering transactions; `pattern` is one of PATTERN_CLASSES."""
    check_features(features)
    code = {c: i for i, c in enumerate(PATTERN_CLASSES)}
    tr, va = train_pos.assign(_y=train_pos["pattern"].map(code)), valid_pos.assign(_y=valid_pos["pattern"].map(code))
    dtrain = _dataset(tr, "_y", features=features)
    dvalid = _dataset(va, "_y", dtrain, features=features)
    return lgb.train(M3_PARAMS, dtrain, rounds, valid_sets=[dvalid],
                     callbacks=[lgb.early_stopping(patience, verbose=False)])


def evaluate_m3(booster: lgb.Booster, test_pos: pd.DataFrame) -> dict:
    """Per-pattern precision/recall and macro F1, next to always guessing the most common pattern."""
    probs = booster.predict(test_pos[booster.feature_name()])
    pred = np.array(PATTERN_CLASSES)[np.argmax(probs, axis=1)]
    truth = test_pos["pattern"].to_numpy()
    per = {}
    for c in PATTERN_CLASSES:
        tp = int(((pred == c) & (truth == c)).sum())
        p_n, t_n = int((pred == c).sum()), int((truth == c).sum())
        prec = tp / p_n if p_n else 0.0
        rec = tp / t_n if t_n else 0.0
        per[c] = {"support": t_n, "precision": prec, "recall": rec,
                  "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0}
    present = [c for c in PATTERN_CLASSES if per[c]["support"]]
    macro = float(np.mean([per[c]["f1"] for c in present])) if present else 0.0
    majority = max(present, key=lambda c: per[c]["support"]) if present else None
    maj_f1 = (2 * (per[majority]["support"] / len(truth)) / (1 + per[majority]["support"] / len(truth)) / len(present)
              if majority else 0.0)
    return {"macro_f1": macro, "majority_class_macro_f1": maj_f1, "accuracy": float((pred == truth).mean()) if len(truth) else 0.0,
            "per_pattern": per, "test_rows": len(truth)}
