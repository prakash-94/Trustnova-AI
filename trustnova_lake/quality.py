"""The checks a load must pass before its tables count. Hard checks fail the job; soft checks are recorded only.
Each check is a small grouped aggregate, so the gate stays cheap even on the full 430M rows."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


@dataclass(frozen=True)
class Check:
    name: str
    variant: str
    value: float
    expected: str
    passed: bool
    hard: bool = True


def _per_variant(df: DataFrame, *aggs) -> dict[str, dict]:
    return {r["variant"]: r.asDict() for r in df.groupBy("variant").agg(*aggs).collect()}


def run_checks(
    variants: Sequence[str],
    bronze_tx: DataFrame,
    silver_tx: DataFrame,
    labels: DataFrame,
    accounts: DataFrame,
    pattern_matches: DataFrame,
    edges: DataFrame,
    expected_rows: Mapping[str, int] | None = None,
) -> list[Check]:
    expected_rows = expected_rows or {}
    bronze = _per_variant(bronze_tx, F.count("*").alias("n"))
    silver = _per_variant(
        silver_tx,
        F.count("*").alias("n"),
        F.countDistinct("txn_id").alias("ids"),
        F.sum(F.when(F.col("ts").isNull() | F.col("amount_paid").isNull() | F.col("amount_received").isNull(), 1)
              .otherwise(0)).alias("unparsed"),
        F.sum(F.when(F.col("amount_paid_usd").isNull() | F.col("amount_received_usd").isNull(), 1)
              .otherwise(0)).alias("no_rate"),
    )
    lab = _per_variant(labels, F.count("*").alias("n"), F.sum("is_laundering").alias("laundering"),
                       F.sum(F.when(F.col("is_laundering").isNull(), 1).otherwise(0)).alias("null_labels"))
    edge = _per_variant(edges, F.count("*").alias("n"))
    tx_accounts = (silver_tx.select("variant", F.col("from_account").alias("account_id"))
                   .unionByName(silver_tx.select("variant", F.col("to_account").alias("account_id"))).distinct())
    missing = _per_variant(tx_accounts.join(accounts.select("variant", "account_id"), ["variant", "account_id"], "left_anti"),
                           F.count("*").alias("n"))
    pats = _per_variant(pattern_matches, F.count("*").alias("lines"),
                        F.sum(F.when(F.col("matches") == 0, 1).otherwise(0)).alias("unmatched"),
                        F.sum(F.when(F.col("matches") > 1, 1).otherwise(0)).alias("multi"))

    def get(d: dict, v: str, k: str, default=0):
        return (d.get(v) or {}).get(k) or default

    checks: list[Check] = []
    for v in variants:
        b, s = get(bronze, v, "n"), get(silver, v, "n")
        if v in expected_rows:
            checks.append(Check("bronze_rows_match_manifest", v, b, f"= {expected_rows[v]}", b == expected_rows[v]))
        checks += [
            Check("bronze_has_rows", v, b, "> 0", b > 0),
            Check("silver_rows_equal_bronze", v, s, f"= {b}", s == b),
            Check("unparsed_values", v, get(silver, v, "unparsed"), "= 0", get(silver, v, "unparsed") == 0),
            Check("duplicate_txn_ids", v, s - get(silver, v, "ids"), "= 0", s == get(silver, v, "ids")),
            Check("labels_rows_equal_silver", v, get(lab, v, "n"), f"= {s}", get(lab, v, "n") == s),
            Check("null_labels", v, get(lab, v, "null_labels"), "= 0", get(lab, v, "null_labels") == 0),
            Check("accounts_missing_from_accounts_file", v, get(missing, v, "n"), "= 0", get(missing, v, "n") == 0),
            Check("rows_without_usd_rate", v, get(silver, v, "no_rate"), "= 0", get(silver, v, "no_rate") == 0),
            Check("edges_twice_transactions", v, get(edge, v, "n"), f"= {2 * s}", get(edge, v, "n") == 2 * s),
            Check("pattern_lines_parsed", v, get(pats, v, "lines"), "> 0", get(pats, v, "lines") > 0),
            Check("pattern_lines_unmatched", v, get(pats, v, "unmatched"), "= 0", get(pats, v, "unmatched") == 0),
            Check("pattern_lines_matching_duplicates", v, get(pats, v, "multi"), "info", True, hard=False),
            Check("laundering_transactions", v, get(lab, v, "laundering"), "info", True, hard=False),
        ]
    return checks


def failures(checks: Sequence[Check]) -> list[Check]:
    return [c for c in checks if c.hard and not c.passed]


def as_rows(checks: Sequence[Check], run_id: str) -> list[dict]:
    return [{"run_id": run_id, **asdict(c), "value": float(c.value)} for c in checks]
