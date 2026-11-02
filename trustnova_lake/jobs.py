"""Entry points for the lakehouse job tasks (`databricks/lakehouse/jobs/*.py` are two-line wrappers around these).

Every task takes `--catalog` and `--variants` (e.g. "HIS,LIS") and replaces only those simulations' rows, so a load
can be re-run, or the full dataset loaded one simulation at a time, without touching the others.
`spark` comes from the Databricks runtime; tests pass a local session instead.
"""

import argparse
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from trustnova_lake import transforms as tf
from trustnova_lake.ibm import (
    PATTERN_ROW_COLUMNS,
    RAW_TRANSACTION_COLUMNS,
    file_prefix,
    parse_variants,
    pattern_rows,
)
from trustnova_lake.quality import as_rows, failures, run_checks


def tables(catalog: str) -> dict[str, str]:
    c = catalog
    return {
        "bronze_tx": f"{c}.bronze.ibm_transactions",
        "bronze_accounts": f"{c}.bronze.ibm_accounts",
        "bronze_patterns": f"{c}.bronze.ibm_pattern_lines",
        "transactions": f"{c}.silver.transactions",
        "accounts": f"{c}.silver.accounts",
        "fx_rates": f"{c}.silver.fx_rates",
        "labels": f"{c}.restricted.aml_labels",
        "patterns": f"{c}.restricted.aml_patterns",
        "pattern_matches": f"{c}.restricted.pattern_line_matches",
        "edges": f"{c}.gold.account_txn_edges",
        "account_summary": f"{c}.gold.account_summary",
        "entity_summary": f"{c}.gold.entity_summary",
        "quality_runs": f"{c}.gold.quality_runs",
    }


CLUSTERING = {
    "bronze_tx": ("variant",),
    "transactions": ("variant", "ts"),
    "labels": ("variant",),
    "edges": ("account_id", "ts"),
    "account_summary": ("variant", "account_id"),
    "entity_summary": ("variant", "entity_id"),
}


def _spark(spark: Any) -> Any:
    if spark is None:
        from databricks.sdk.runtime import spark as runtime_spark

        return runtime_spark
    return spark


def _args(argv: Sequence[str], prog: str) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog=prog)
    p.add_argument("--catalog", required=True, help="Unity Catalog catalog, e.g. trustnova_staging")
    p.add_argument("--variants", required=True, help='comma-separated simulations, e.g. "HIS,LIS"')
    p.add_argument("--source", default="", help="folder with the raw files (default /Volumes/<catalog>/raw/ibm_aml)")
    a = p.parse_args(list(argv))
    a.variant_list = parse_variants(a.variants)
    a.source = a.source or f"/Volumes/{a.catalog}/raw/ibm_aml"
    return a


def schema_change_action(table_schema: Sequence[tuple[str, str]], new_schema: Sequence[tuple[str, str]],
                         table_variants: Sequence[str], variants: Sequence[str]) -> str:
    """What a write must do: "overwrite" the given simulations, "recreate" the table because its columns changed
    (allowed only when this write replaces every simulation already in it), or refuse."""
    if list(table_schema) == list(new_schema):
        return "overwrite"
    others = sorted(set(table_variants) - set(variants))
    if others:
        raise ValueError(
            f"the columns changed, but the table also holds {others}, which this run doesn't rewrite; run it for "
            f"{sorted(set(table_variants) | set(variants))} so no simulation is left with the old columns")
    return "recreate"


def _create(spark: Any, df: DataFrame, table: str, cluster_by: Sequence[str], replace: bool) -> None:
    w = df.limit(0).writeTo(table).using("delta")
    w.createOrReplace() if replace else w.create()
    if cluster_by:
        spark.sql(f"ALTER TABLE {table} CLUSTER BY ({', '.join(cluster_by)})")


def replace_variants(spark: Any, df: DataFrame, table: str, variants: Sequence[str], cluster_by: Sequence[str] = ()) -> None:
    """Create the table on first use, otherwise overwrite only the rows of `variants`. If the columns changed (a new
    feature set, say) the table is recreated, which is only allowed when this write covers all its simulations."""
    if not spark.catalog.tableExists(table):
        _create(spark, df, table, cluster_by, replace=False)
    else:
        existing = spark.table(table)
        as_pairs = lambda schema: [(f.name, f.dataType.simpleString()) for f in schema.fields]
        held = [r[0] for r in existing.select("variant").distinct().collect()]
        if schema_change_action(as_pairs(existing.schema), as_pairs(df.schema), held, variants) == "recreate":
            print(f"{table}: columns changed; recreating it for {sorted(variants)}", flush=True)
            _create(spark, df, table, cluster_by, replace=True)
    df.writeTo(table).overwrite(F.col("variant").isin(list(variants)))


def _in(df: DataFrame, variants: Sequence[str]) -> DataFrame:
    return df.where(F.col("variant").isin(list(variants)))


# ------------------------------------------------------------------------------------------------ bronze
def read_raw_transactions(spark: Any, source: str, variants: Sequence[str]) -> DataFrame:
    frames = []
    for v in variants:
        path = f"{source}/{file_prefix(v)}_Trans*.csv"  # also matches the .part-NNN.csv pieces of the Large files
        df = spark.read.csv(path, schema=tf.RAW_TRANSACTION_SCHEMA, header=True, mode="FAILFAST")
        frames.append(df.withColumn("source_file", F.col("_metadata.file_name"))
                      .withColumn("variant", tf.variant_from_file(F.col("_metadata.file_name"))))
    out = frames[0]
    for f in frames[1:]:
        out = out.unionByName(f)
    return out.withColumn("ingested_at", F.current_timestamp())


def read_raw_accounts(spark: Any, source: str, variants: Sequence[str]) -> DataFrame:
    frames = [spark.read.csv(f"{source}/{file_prefix(v)}_accounts.csv", schema=tf.RAW_ACCOUNT_SCHEMA, header=True,
                             mode="FAILFAST").withColumn("variant", F.lit(v)) for v in variants]
    out = frames[0]
    for f in frames[1:]:
        out = out.unionByName(f)
    return out


PATTERN_SCHEMA = T.StructType([T.StructField(c, T.StringType(), False) for c in PATTERN_ROW_COLUMNS])


def read_raw_patterns(spark: Any, source: str, variants: Sequence[str]) -> DataFrame:
    """Pattern files are small (13 MB at most), so they are parsed on the driver with the tested plain-Python parser."""
    rows = []
    for v in variants:
        text = Path(f"{source}/{file_prefix(v)}_Patterns.txt").read_text(encoding="utf-8")
        rows += pattern_rows(v, text)
    return spark.createDataFrame(rows, PATTERN_SCHEMA)


def bronze_main(argv: Sequence[str], spark: Any = None) -> int:
    a = _args(argv, "lake-bronze")
    spark = _spark(spark)
    t = tables(a.catalog)
    replace_variants(spark, read_raw_transactions(spark, a.source, a.variant_list), t["bronze_tx"], a.variant_list,
                     CLUSTERING["bronze_tx"])
    replace_variants(spark, read_raw_accounts(spark, a.source, a.variant_list), t["bronze_accounts"], a.variant_list)
    replace_variants(spark, read_raw_patterns(spark, a.source, a.variant_list), t["bronze_patterns"], a.variant_list)
    print(f"bronze loaded for {a.variant_list}", flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ silver
def silver_main(argv: Sequence[str], spark: Any = None) -> int:
    a = _args(argv, "lake-silver")
    spark = _spark(spark)
    t, vs = tables(a.catalog), a.variant_list
    raw = _in(spark.table(t["bronze_tx"]), vs).select(*RAW_TRANSACTION_COLUMNS, "variant")
    typed = tf.typed_transactions(raw)
    fx = tf.fx_rates(typed)
    replace_variants(spark, fx, t["fx_rates"], vs)
    with_usd = tf.with_usd(tf.with_txn_ids(typed), _in(spark.table(t["fx_rates"]), vs))
    tx, labels = tf.split_ground_truth(with_usd)
    replace_variants(spark, tx, t["transactions"], vs, CLUSTERING["transactions"])
    replace_variants(spark, labels, t["labels"], vs, CLUSTERING["labels"])
    replace_variants(spark, tf.typed_accounts(_in(spark.table(t["bronze_accounts"]), vs)), t["accounts"], vs)
    pattern_typed = tf.typed_transactions(_in(spark.table(t["bronze_patterns"]), vs))
    matched = tf.match_patterns(pattern_typed, _in(spark.table(t["transactions"]), vs))
    replace_variants(spark, matched, t["pattern_matches"], vs)
    replace_variants(spark, tf.restricted_patterns(_in(spark.table(t["pattern_matches"]), vs)), t["patterns"], vs)
    print(f"silver loaded for {vs}", flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ gold
def gold_main(argv: Sequence[str], spark: Any = None) -> int:
    a = _args(argv, "lake-gold")
    spark = _spark(spark)
    t, vs = tables(a.catalog), a.variant_list
    replace_variants(spark, tf.account_txn_edges(_in(spark.table(t["transactions"]), vs)), t["edges"], vs,
                     CLUSTERING["edges"])
    replace_variants(spark, tf.account_summary(_in(spark.table(t["edges"]), vs)), t["account_summary"], vs,
                     CLUSTERING["account_summary"])
    replace_variants(spark, tf.entity_summary(_in(spark.table(t["account_summary"]), vs), _in(spark.table(t["accounts"]), vs)),
                     t["entity_summary"], vs, CLUSTERING["entity_summary"])
    print(f"gold loaded for {vs}", flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ quality
def expected_rows_from_manifests(source: str, variants: Sequence[str]) -> dict[str, int]:
    """Row counts recorded when the Large files were split for upload (only split files have a manifest)."""
    out = {}
    for v in variants:
        m = Path(f"{source}/{file_prefix(v)}_Trans.manifest.json")
        if m.exists():
            out[v] = int(json.loads(m.read_text(encoding="utf-8"))["data_rows"])
    return out


QUALITY_SCHEMA = T.StructType([
    T.StructField("run_id", T.StringType()), T.StructField("name", T.StringType()),
    T.StructField("variant", T.StringType()), T.StructField("value", T.DoubleType()),
    T.StructField("expected", T.StringType()), T.StructField("passed", T.BooleanType()),
    T.StructField("hard", T.BooleanType()), T.StructField("checked_at", T.TimestampType()),
])


def quality_main(argv: Sequence[str], spark: Any = None) -> int:
    a = _args(argv, "lake-quality")
    spark = _spark(spark)
    t, vs = tables(a.catalog), a.variant_list
    checks = run_checks(
        vs,
        bronze_tx=_in(spark.table(t["bronze_tx"]), vs),
        silver_tx=_in(spark.table(t["transactions"]), vs),
        labels=_in(spark.table(t["labels"]), vs),
        accounts=_in(spark.table(t["accounts"]), vs),
        pattern_matches=_in(spark.table(t["pattern_matches"]), vs),
        edges=_in(spark.table(t["edges"]), vs),
        expected_rows=expected_rows_from_manifests(a.source, vs),
    )
    run_id, now = uuid.uuid4().hex, datetime.now(UTC).replace(tzinfo=None)
    rows = [{**r, "checked_at": now} for r in as_rows(checks, run_id)]
    results = spark.createDataFrame(rows, QUALITY_SCHEMA)
    if spark.catalog.tableExists(t["quality_runs"]):
        results.writeTo(t["quality_runs"]).append()
    else:
        results.writeTo(t["quality_runs"]).using("delta").create()
    for c in checks:
        mark = "PASS" if c.passed else ("FAIL" if c.hard else "WARN")
        print(f"{mark}  {c.variant}  {c.name:<38} {c.value:>16,.0f}  expected {c.expected}", flush=True)
    failed = failures(checks)
    print(f"quality run {run_id}: {len(checks) - len(failed)}/{len(checks)} checks passed", flush=True)
    return 1 if failed else 0
