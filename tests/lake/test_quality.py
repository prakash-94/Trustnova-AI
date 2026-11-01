"""The quality gate passes on a correct load and fails on each kind of damage it exists to catch."""

import pytest

pytest.importorskip("pyspark")

import sample_data as sd
from pyspark.sql import functions as F

from trustnova_lake.quality import failures, run_checks


def check(built, **override):
    frames = {"bronze_tx": built["raw"], "silver_tx": built["tx"], "labels": built["labels"],
              "accounts": built["accounts"], "pattern_matches": built["pattern_matches"], "edges": built["edges"]}
    expected = override.pop("expected_rows", None)
    frames.update(override)
    return run_checks(["HIS", "LIS"], expected_rows=expected, **frames)


def failed_names(checks):
    return {(c.name, c.variant) for c in failures(checks)}


def test_a_correct_load_passes(built):
    checks = check(built, expected_rows={"HIS": len(sd.HIS_TRANSACTIONS)})
    assert failed_names(checks) == set()
    laundering = {c.variant: c.value for c in checks if c.name == "laundering_transactions"}
    assert laundering == {"HIS": 2, "LIS": 2}


def test_a_lost_row_is_caught(built):
    assert ("silver_rows_equal_bronze", "HIS") in failed_names(check(built, silver_tx=built["tx"].where(F.col("payment_format") != "Cheque")))


def test_a_manifest_mismatch_is_caught(built):
    assert ("bronze_rows_match_manifest", "HIS") in failed_names(check(built, expected_rows={"HIS": 999}))


def test_duplicate_ids_are_caught(built):
    doubled = built["tx"].unionByName(built["tx"].where(F.col("variant") == "LIS"))
    names = failed_names(check(built, silver_tx=doubled))
    assert ("duplicate_txn_ids", "LIS") in names


def test_an_account_missing_from_the_accounts_file_is_caught(built):
    names = failed_names(check(built, accounts=built["accounts"].where(F.col("account_id") != "HIS:1:8000AAA03")))
    assert ("accounts_missing_from_accounts_file", "HIS") in names


def test_a_missing_fx_rate_is_caught(built):
    no_btc = built["tx"].withColumn("amount_paid_usd", F.when(F.col("paid_currency") == "Bitcoin", None).otherwise(F.col("amount_paid_usd")))
    assert ("rows_without_usd_rate", "HIS") in failed_names(check(built, silver_tx=no_btc))


def test_unmatched_pattern_lines_and_half_written_edges_are_caught(built):
    pm = built["pattern_matches"].withColumn("matches", F.lit(0))
    edges = built["edges"].where(F.col("direction") == "out")
    names = failed_names(check(built, pattern_matches=pm, edges=edges))
    assert {("pattern_lines_unmatched", "HIS"), ("edges_twice_transactions", "HIS")} <= names
