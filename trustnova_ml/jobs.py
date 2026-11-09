"""Entry points for the ML job tasks (`databricks/lakehouse/jobs/ml_*.py` are two-line wrappers around these).

    features  silver + gold -> ml.txn_features (point-in-time features and the temporal split; no labels)
    train     M1 + M3 with LightGBM, evaluated against the rule baseline; logged and registered in MLflow; a model
              that passes the gate gets the alias `candidate`
    promote   a person moves `candidate` to `champion` after reading the evaluation (the manual approval)
    score     `champion` scores every transaction -> account-day scores -> daily alerts with reason codes

Scoring reads only ml.txn_features, never the restricted ground truth.
"""

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from trustnova_lake.ibm import parse_variants
from trustnova_lake.jobs import _in, _spark, replace_variants, tables
from trustnova_ml import metrics as mx
from trustnova_ml.baseline import rule_score
from trustnova_ml.features import FEATURES, assign_split, transaction_features

M1, M3 = "m1_transaction_risk", "m3_pattern_type"
ALL = "ALL"


def ml_tables(catalog: str) -> dict[str, str]:
    c = catalog
    return {
        "features": f"{c}.ml.txn_features", "evaluations": f"{c}.ml.model_evaluations",
        "scores": f"{c}.ml.txn_scores", "account_day": f"{c}.ml.account_day_scores", "alerts": f"{c}.ml.ml_alerts",
        "m1": f"{c}.ml.{M1}", "m3": f"{c}.ml.{M3}",
    }


def _args(argv: Sequence[str], prog: str, extra=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog=prog)
    p.add_argument("--catalog", required=True)
    p.add_argument("--variants", required=True)
    if extra:
        extra(p)
    a = p.parse_args(list(argv))
    a.variant_list = parse_variants(a.variants)
    return a


# ------------------------------------------------------------------------------------------------ features
def features_main(argv: Sequence[str], spark: Any = None) -> int:
    a = _args(argv, "ml-features")
    spark = _spark(spark)
    t, m, vs = tables(a.catalog), ml_tables(a.catalog), a.variant_list
    feats = assign_split(transaction_features(_in(spark.table(t["transactions"]), vs), _in(spark.table(t["edges"]), vs),
                                              _in(spark.table(t["accounts"]), vs)))
    replace_variants(spark, feats, m["features"], vs, ("variant", "split"))
    print(f"features written for {vs}", flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ train
def labelled(spark: Any, catalog: str, variants: Sequence[str]) -> DataFrame:
    """Features joined to the restricted ground truth (training and evaluation only)."""
    t, m = tables(catalog), ml_tables(catalog)
    labels = spark.table(t["labels"]).select("txn_id", F.col("is_laundering").alias("label"))
    pats = spark.table(t["patterns"]).groupBy("txn_id").agg(F.first("pattern_type").alias("_pattern"))
    return (_in(spark.table(m["features"]), variants).join(labels, "txn_id").join(pats, "txn_id", "left")
            .withColumn("pattern", F.when(F.col("label") == 1, F.coalesce("_pattern", F.lit("OTHER"))))
            .drop("_pattern").withColumn("rule_score", rule_score()))


def negative_fractions(data: DataFrame, ratio: int) -> dict[str, float]:
    rows = (data.where(F.col("split") == "train").groupBy("variant")
            .agg(F.sum("label").alias("pos"), (F.count("*") - F.sum("label")).alias("neg")).collect())
    return {r.variant: (min(1.0, ratio * r.pos / r.neg) if r.neg else 1.0) for r in rows}


def sampled(data: DataFrame, fractions: dict[str, float]) -> DataFrame:
    """All laundering rows plus a deterministic sample of normal rows (hash of txn_id, so re-runs agree)."""
    frac = F.element_at(F.create_map(*[F.lit(x) for kv in fractions.items() for x in kv]), F.col("variant"))
    keep = (F.pmod(F.xxhash64("txn_id"), F.lit(1_000_000)) < frac * 1_000_000)
    return data.where((F.col("label") == 1) | keep)


SCORED_SCHEMA = T.StructType([
    T.StructField("variant", T.StringType()), T.StructField("split", T.StringType()),
    T.StructField("label", T.IntegerType()), T.StructField("pattern", T.StringType()),
    T.StructField("rule_score", T.DoubleType()), T.StructField("raw", T.DoubleType()),
])


def _scorer(model_str: str):
    def score(batches):
        import lightgbm as lgb

        booster = lgb.Booster(model_str=model_str)
        names = booster.feature_name()
        for pdf in batches:
            pdf["raw"] = booster.predict(pdf[names])
            yield pdf[["variant", "split", "label", "pattern", "rule_score", "raw"]]
    return score


def _curves(rows, key_cols: Sequence[str], score_col: str) -> dict[tuple, mx.Curve]:
    groups: dict[tuple, list] = {}
    for r in rows:
        k = tuple(r[c] for c in key_cols)
        groups.setdefault(k, []).append((r[score_col], r["pos"], r["neg"]))
        groups.setdefault((ALL, *k[1:]), []).append((r[score_col], r["pos"], r["neg"]))
    return {k: mx.Curve.from_counts(v) for k, v in groups.items()}


def evaluate(scored: DataFrame, variants: Sequence[str]) -> dict:
    """Model vs rule baseline, per simulation and per pattern, from ONE pass over the scored rows: counts per
    (simulation, split, model score bin, rule score, pattern). Serverless Spark can't cache, so every further query
    would score all valid and test rows again (80-90 minutes each on the full dataset)."""
    counts = (scored.withColumn("bin", F.floor(F.col("raw") * mx.BINS) / mx.BINS)
              .groupBy("variant", "split", "bin", "rule_score", "pattern")
              .agg(F.sum("label").alias("pos"), (F.count("*") - F.sum("label")).alias("neg")).collect())
    return report_from_counts([r.asDict() for r in counts], variants)


def report_from_counts(rows: Sequence[dict], variants: Sequence[str]) -> dict:
    """The evaluation report from (variant, split, bin, rule_score, pattern, pos, neg) counts. `pattern` is set only
    on laundering rows."""
    model = _curves(rows, ("variant", "split"), "bin")
    rule = _curves(rows, ("variant", "split"), "rule_score")
    m_thr = mx.best_f1_threshold(model[(ALL, "valid")])
    r_thr = mx.best_f1_threshold(rule[(ALL, "valid")])
    groups = [ALL, *variants]
    report = {
        "threshold_raw": m_thr, "baseline_threshold": r_thr,
        "model": {g: mx.summary(model[(g, "test")], m_thr) for g in groups if (g, "test") in model},
        "baseline": {g: mx.summary(rule[(g, "test")], r_thr) for g in groups if (g, "test") in rule},
    }
    pat: dict[str, list[int]] = {}
    for r in rows:
        if r["split"] == "test" and r["pattern"] is not None and r["pos"]:
            p = pat.setdefault(r["pattern"], [0, 0, 0])
            p[0] += r["pos"]
            p[1] += r["pos"] if r["bin"] >= m_thr else 0  # the curves' rule: flagged when the bin is at or above it
            p[2] += r["pos"] if r["rule_score"] >= r_thr else 0
    report["recall_by_pattern"] = {k: {"test_rows": n, "model_recall": c / n, "baseline_recall": b / n}
                                   for k, (n, c, b) in pat.items()}
    report["valid_bins"] = [(float(s), int(p), int(n)) for s, p, n in
                            zip(model[(ALL, "valid")].upper, model[(ALL, "valid")].pos, model[(ALL, "valid")].neg, strict=True)]
    return report


def _flat(prefix: str, d: dict) -> dict[str, float]:
    return {f"{prefix}.{k}": float(v) for k, v in d.items() if isinstance(v, (int, float))}


EVAL_SCHEMA = T.StructType([
    T.StructField("model", T.StringType()), T.StructField("version", T.StringType()), T.StructField("run_id", T.StringType()),
    T.StructField("variants", T.StringType()), T.StructField("grp", T.StringType()), T.StructField("metric", T.StringType()),
    T.StructField("value", T.DoubleType()), T.StructField("gate_passed", T.BooleanType()),
    T.StructField("evaluated_at", T.TimestampType()),
])


def train_main(argv: Sequence[str], spark: Any = None) -> int:
    import mlflow
    from mlflow import MlflowClient
    from mlflow.models import infer_signature

    from trustnova_ml import train as tr

    a = _args(argv, "ml-train", lambda p: (p.add_argument("--experiment", default=""),
                                           p.add_argument("--ratio", type=int, default=tr.NEGATIVES_PER_POSITIVE)))
    spark = _spark(spark)
    m, vs = ml_tables(a.catalog), a.variant_list
    data = labelled(spark, a.catalog, vs)

    fractions = negative_fractions(data, a.ratio)
    # float32 halves the driver memory for the production sample (all laundering + `ratio` normal rows each)
    f32 = [F.col(c).cast("float").alias(c) for c in FEATURES]
    pdf = (sampled(data.where(F.col("split").isin("train", "valid")), fractions)
           .select(*f32, "label", "pattern", "split", "variant").toPandas())
    train_pd, valid_pd = pdf[pdf.split == "train"], pdf[pdf.split == "valid"]
    print(f"M1 training rows: {len(train_pd):,} ({int(train_pd.label.sum()):,} laundering); "
          f"early-stopping rows: {len(valid_pd):,}; negative sample fractions {fractions}", flush=True)
    m1 = tr.train_m1(train_pd, valid_pd)

    scored = (data.where(F.col("split").isin("valid", "test"))
              .select("variant", "split", "label", "pattern", "rule_score", *FEATURES)
              .mapInPandas(_scorer(m1.model_to_string()), SCORED_SCHEMA))
    report = evaluate(scored, vs)
    calibration = tr.fit_calibration(report.pop("valid_bins"), 1 / mx.BINS)
    passed, reasons = tr.gate(report["model"], report["baseline"], [ALL, *vs])
    report["gate"] = {"passed": passed, "reasons": reasons}

    pos = data.where(F.col("label") == 1).select(*f32, "pattern", "split").toPandas()
    m3 = tr.train_m3(pos[pos.split == "train"], pos[pos.split == "valid"])
    m3_report = tr.evaluate_m3(m3, pos[pos.split == "test"])
    m3_ok = m3_report["macro_f1"] > m3_report["majority_class_macro_f1"]

    mlflow.set_registry_uri("databricks-uc")
    user = spark.sql("SELECT current_user() AS u").first().u
    mlflow.set_experiment(a.experiment or f"/Users/{user}/trustnova-aml-detection")
    client = MlflowClient()
    example = train_pd[list(FEATURES)].head(20)
    with mlflow.start_run(run_name=f"{a.catalog} {','.join(vs)}") as run:
        mlflow.log_params({"catalog": a.catalog, "variants": ",".join(vs), "negatives_per_positive": a.ratio,
                           "m1_best_iteration": m1.best_iteration, "m3_best_iteration": m3.best_iteration,
                           "features": len(FEATURES), **{f"m1.{k}": v for k, v in tr.M1_PARAMS.items()}})
        for g, d in report["model"].items():
            mlflow.log_metrics(_flat(f"test.{g}", d))
        for g, d in report["baseline"].items():
            mlflow.log_metrics(_flat(f"baseline.test.{g}", d))
        mlflow.log_metrics({"m3.macro_f1": m3_report["macro_f1"], "m3.majority_macro_f1": m3_report["majority_class_macro_f1"]})
        mlflow.log_dict(calibration, "calibration.json")
        mlflow.log_dict(report, "evaluation.json")
        mlflow.log_dict(m3_report, "m3_evaluation.json")
        mlflow.log_dict({"features": list(FEATURES)}, "features.json")
        mlflow.lightgbm.log_model(m1, name="m1", registered_model_name=m["m1"], input_example=example,
                                  signature=infer_signature(example, m1.predict(example)))
        mlflow.lightgbm.log_model(m3, name="m3", registered_model_name=m["m3"], input_example=example,
                                  signature=infer_signature(example, m3.predict(example)))
        run_id = run.info.run_id

    def version_of(name: str) -> str:
        return max((v for v in client.search_model_versions(f"name='{name}'") if v.run_id == run_id),
                   key=lambda v: int(v.version)).version

    v1, v3 = version_of(m["m1"]), version_of(m["m3"])
    if passed:
        client.set_registered_model_alias(m["m1"], "candidate", v1)
    if m3_ok:
        client.set_registered_model_alias(m["m3"], "candidate", v3)

    now = datetime.now(UTC).replace(tzinfo=None)
    rows = [{"model": M1, "version": v1, "run_id": run_id, "variants": ",".join(vs), "grp": f"{kind}:{g}", "metric": k,
             "value": float(val), "gate_passed": passed, "evaluated_at": now}
            for kind in ("model", "baseline") for g, d in report[kind].items() for k, val in d.items()
            if isinstance(val, (int, float))]
    rows += [{"model": M3, "version": v3, "run_id": run_id, "variants": ",".join(vs), "grp": "test", "metric": k,
              "value": float(m3_report[k]), "gate_passed": m3_ok, "evaluated_at": now}
             for k in ("macro_f1", "majority_class_macro_f1", "accuracy")]
    ev = spark.createDataFrame(rows, EVAL_SCHEMA)
    if spark.catalog.tableExists(m["evaluations"]):
        ev.writeTo(m["evaluations"]).append()
    else:
        ev.writeTo(m["evaluations"]).using("delta").create()

    print(json.dumps({"m1_version": v1, "m3_version": v3, "gate": report["gate"], "test": report["model"],
                      "baseline": report["baseline"], "recall_by_pattern": report["recall_by_pattern"],
                      "m3": {k: m3_report[k] for k in ("macro_f1", "majority_class_macro_f1", "accuracy")}},
                     indent=1, default=float), flush=True)
    print(("GATE PASSED: " if passed else "GATE FAILED: ") + (f"{m['m1']} v{v1} is now @candidate" if passed else "; ".join(reasons)),
          flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ promote
def promote_main(argv: Sequence[str], spark: Any = None) -> int:
    """The manual approval: `@candidate` -> `@champion` for one model. Run by a person after reading the evaluation."""
    import mlflow
    from mlflow import MlflowClient

    p = argparse.ArgumentParser(prog="ml-promote")
    p.add_argument("--catalog", required=True)
    p.add_argument("--model", choices=("m1", "m3"), required=True)
    a = p.parse_args(list(argv))
    mlflow.set_registry_uri("databricks-uc")
    name = ml_tables(a.catalog)[a.model]
    client = MlflowClient()
    v = client.get_model_version_by_alias(name, "candidate").version
    client.set_registered_model_alias(name, "champion", v)
    print(f"{name} v{v} is now @champion", flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ score
SCORE_SCHEMA = T.StructType([
    T.StructField("txn_id", T.StringType()), T.StructField("variant", T.StringType()),
    T.StructField("ts", T.TimestampNTZType()), T.StructField("day", T.IntegerType()),
    T.StructField("from_account", T.StringType()), T.StructField("to_account", T.StringType()),
    T.StructField("raw", T.DoubleType()), T.StructField("score", T.DoubleType()),
])


def _calibrated_scorer(model_str: str, calibration: dict):
    def score(batches):
        import lightgbm as lgb
        import numpy as np

        booster = lgb.Booster(model_str=model_str)
        names = booster.feature_name()
        for pdf in batches:
            raw = booster.predict(pdf[names])
            pdf["raw"] = raw
            pdf["score"] = np.interp(raw, calibration["x"], calibration["y"])
            yield pdf[["txn_id", "variant", "ts", "day", "from_account", "to_account", "raw", "score"]]
    return score


ALERT_SCHEMA = T.StructType([
    T.StructField("alert_id", T.StringType()), T.StructField("variant", T.StringType()),
    T.StructField("account_id", T.StringType()), T.StructField("day", T.IntegerType()),
    T.StructField("score", T.DoubleType()), T.StructField("rank_in_day", T.IntegerType()),
    T.StructField("top_txn_id", T.StringType()), T.StructField("n_txn", T.LongType()),
    T.StructField("reasons", T.StringType()), T.StructField("predicted_pattern", T.StringType()),
    T.StructField("pattern_probability", T.DoubleType()), T.StructField("m1_version", T.StringType()),
    T.StructField("m3_version", T.StringType()), T.StructField("created_at", T.TimestampType()),
])


def score_main(argv: Sequence[str], spark: Any = None) -> int:
    import mlflow
    import numpy as np
    from mlflow import MlflowClient

    from trustnova_ml.train import PATTERN_CLASSES, top_reasons

    a = _args(argv, "ml-score", lambda p: (p.add_argument("--alias", default="champion"),
                                           p.add_argument("--budget", type=int, default=25,
                                                          help="alerts per simulation per day"),
                                           p.add_argument("--min-score", type=float, default=0.05)))
    spark = _spark(spark)
    m, vs = ml_tables(a.catalog), a.variant_list
    mlflow.set_registry_uri("databricks-uc")
    client = MlflowClient()
    mv1 = client.get_model_version_by_alias(m["m1"], a.alias)
    m1 = mlflow.lightgbm.load_model(f"models:/{m['m1']}@{a.alias}")
    calibration = mlflow.artifacts.load_dict(f"runs:/{mv1.run_id}/calibration.json")
    try:
        mv3 = client.get_model_version_by_alias(m["m3"], a.alias)
        m3 = mlflow.lightgbm.load_model(f"models:/{m['m3']}@{a.alias}")
    except Exception:  # noqa: BLE001 - no M3 at this alias: alerts go out without a predicted pattern
        mv3, m3 = None, None

    # each model reads its own feature list, so a champion trained before the feature set grew keeps working
    m1_features = m1.feature_name()
    feats = _in(spark.table(m["features"]), vs)
    scores = (feats.select("txn_id", "variant", "ts", "day", "from_account", "to_account", *m1_features)
              .mapInPandas(_calibrated_scorer(m1.model_to_string(), calibration), SCORE_SCHEMA)
              .withColumn("m1_version", F.lit(mv1.version)))
    replace_variants(spark, scores, m["scores"], vs, ("variant", "day"))

    s = _in(spark.table(m["scores"]), vs)
    sides = (s.select("variant", F.col("from_account").alias("account_id"), "day", "txn_id", "score")
             .unionByName(s.select("variant", F.col("to_account").alias("account_id"), "day", "txn_id", "score")))
    account_day = sides.groupBy("variant", "account_id", "day").agg(
        F.max("score").alias("score"), F.max_by("txn_id", "score").alias("top_txn_id"),
        F.countDistinct("txn_id").alias("n_txn"))
    replace_variants(spark, account_day, m["account_day"], vs, ("variant", "day"))

    rank = F.row_number().over(Window.partitionBy("variant", "day").orderBy(F.desc("score"), "account_id"))
    top = (_in(spark.table(m["account_day"]), vs).withColumn("rank_in_day", rank)
           .where((F.col("rank_in_day") <= a.budget) & (F.col("score") >= a.min_score)))
    needed = sorted(set(m1_features) | set(m3.feature_name() if m3 is not None else ()))
    alert_feats = top.join(feats.select(F.col("txn_id").alias("top_txn_id"), *needed), "top_txn_id").toPandas()
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = []
    if len(alert_feats):
        reasons = top_reasons(m1, alert_feats)
        probs = m3.predict(alert_feats[m3.feature_name()]) if m3 is not None else None
        for i, r in alert_feats.iterrows():
            pattern, p_pattern = (None, None)
            if probs is not None:
                j = int(np.argmax(probs[i]))
                pattern, p_pattern = PATTERN_CLASSES[j], float(probs[i][j])
            rows.append({
                "alert_id": f"{r.variant}-{r.day}-{r.account_id}", "variant": r.variant, "account_id": r.account_id,
                "day": int(r.day), "score": float(r.score), "rank_in_day": int(r.rank_in_day),
                "top_txn_id": r.top_txn_id, "n_txn": int(r.n_txn), "reasons": json.dumps(reasons[i]),
                "predicted_pattern": pattern, "pattern_probability": p_pattern, "m1_version": mv1.version,
                "m3_version": mv3.version if mv3 else None, "created_at": now})
    replace_variants(spark, spark.createDataFrame(rows, ALERT_SCHEMA), m["alerts"], vs, ("variant", "day"))
    print(f"scored {vs} with {m['m1']} v{mv1.version}; {len(rows):,} alerts (budget {a.budget}/simulation/day)", flush=True)
    return 0
