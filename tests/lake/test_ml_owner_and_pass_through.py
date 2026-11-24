"""Owner-activity and pass-through features on small hand-made histories, where the right answers are known."""

import pytest

pytest.importorskip("pyspark")

from pyspark.sql import functions as F

from trustnova_ml.features import owner_activity, pass_through

H = 3600
T0 = 1_662_364_800  # 2022-09-05 08:00 UTC


def _real(spark, rows):
    """rows: (txn_id, from, to, seconds after T0, paid USD, received USD)"""
    df = spark.createDataFrame(rows, "txn_id string, from_account string, to_account string, s long, paid long, rec long")
    return df.select("txn_id", F.lit("HIS").alias("variant"), "from_account", "to_account",
                     (F.col("s") + T0).alias("sec"), F.col("paid").cast("double").alias("amount_paid_usd"),
                     F.col("rec").cast("double").alias("amount_received_usd"))


CYCLE = [  # six accounts, the amount shrinking a little at every hop, money returning to A
    ("c1", "A", "B", 0, 1000, 1000), ("c2", "B", "C", 1 * H, 990, 990), ("c3", "C", "D", 2 * H, 985, 985),
    ("c4", "D", "E", 3 * H, 980, 980), ("c5", "E", "F", 4 * H, 975, 975), ("c6", "F", "A", 5 * H, 970, 970),
]
OTHERS = [
    ("n1", "N", "B", H // 2, 5000, 5000),                          # a different amount into B: no match
    ("q1", "Q", "R", 0, 500, 500), ("q2", "R", "Q", H, 500, 500),  # straight back to the payer: money_back's job
    ("g1", "H", "G", 0, 200, 200), ("g2", "G", "I", 8 * 24 * H, 200, 200),  # 8 days later: outside the window
    ("j1", "K", "J", 0, 1000, 1000), ("j2", "J", "L", H, 850, 850),        # 15% less: a loose match only
    ("m1", "S", "M", 0, 700, 700), ("m2", "M", "T", 0, 700, 700),          # same minute: not before
]


@pytest.fixture(scope="module")
def pt(spark):
    rows = pass_through(_real(spark, CYCLE + OTHERS)).collect()
    return {r.txn_id: r for r in rows}


def test_a_cycle_is_followed_back_to_its_start(pt):
    assert [pt[t].pt_chain_len for t in ("c2", "c3", "c4", "c5", "c6")] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert pt["c6"].pt_chain_returns == 1.0        # F->A, and the chain started with A paying
    assert pt["c5"].pt_chain_returns == 0.0
    assert "c1" not in pt                          # nothing came into A before it paid
    assert pt["c2"].pt_match_5pct == 1.0 and pt["c2"].pt_match_20pct == 1.0
    assert pt["c2"].pt_best_gap == pytest.approx(10 / 990)   # gap is measured against the amount paid out
    assert pt["c2"].pt_minutes_since_match == 60.0


def test_only_similar_earlier_amounts_from_someone_else_count(pt):
    assert "q2" not in pt   # R pays back the account that paid it
    assert "g2" not in pt   # older than 7 days
    assert "m2" not in pt   # same minute
    j = pt["j2"]
    assert (j.pt_match_5pct, j.pt_match_20pct) == (0.0, 1.0) and j.pt_best_gap == pytest.approx(150 / 850)


def test_pass_through_never_looks_ahead(spark, pt):
    """Removing everything after c4 must not change the features of c1..c4."""
    early = {r.txn_id: r for r in pass_through(_real(spark, CYCLE[:4] + OTHERS)).collect()}
    for t in ("c2", "c3", "c4"):
        assert early[t] == pt[t]


# ------------------------------------------------------------------------------------------------ owner activity
def _edges(spark, rows):
    """rows: (txn_id, from, to, 'YYYY-MM-DD HH:MM', payment format) -> both sides, as gold.account_txn_edges has them"""
    tx = spark.createDataFrame(rows, "txn_id string, f string, t string, ts string, fmt string").withColumns(
        {"ts": F.to_timestamp("ts"), "usd": F.lit(100.0), "variant": F.lit("HIS")})
    side = lambda acct, cp, d: tx.select(F.col(acct).alias("account_id"), F.col(cp).alias("counterparty_id"),
                                         F.lit(d).alias("direction"), F.col("usd").alias("amount_usd"), "ts",
                                         F.col("fmt").alias("payment_format"), (F.col("f") == F.col("t")).alias("is_self_transfer"),
                                         "txn_id", "variant")
    return side("f", "t", "out").unionByName(side("t", "f", "in"))


OWNER_TXNS = [
    ("o1", "acc1", "x1", "2022-09-05 10:00", "ACH"), ("o2", "acc2", "x2", "2022-09-05 11:00", "ACH"),
    ("o3", "acc3", "x3", "2022-09-05 12:00", "ACH"),
    ("o4", "acc1", "x4", "2022-09-06 09:00", "ACH"), ("o5", "acc2", "acc3", "2022-09-06 10:00", "ACH"),  # between own accounts
    ("o6", "acc1", "x5", "2022-09-07 09:00", "Cheque"),
]


@pytest.fixture(scope="module")
def owner(spark):
    accounts = spark.createDataFrame([("HIS", a, "HIS:E1") for a in ("acc1", "acc2", "acc3")],
                                     "variant string, account_id string, entity_id string")
    rows = owner_activity(_edges(spark, OWNER_TXNS), accounts).collect()
    return {(r.txn_id, r.direction): r for r in rows}


def test_the_owner_sees_what_each_quiet_account_hides(owner):
    assert owner[("o1", "out")].d0_n_out == 0.0
    assert owner[("o3", "out")].d0_n_out == 2.0    # acc1 and acc2 already paid out today; acc3 itself had not
    day2 = owner[("o4", "out")]
    assert (day2.p1_n_out, day2.p7_new_cp_out, day2.p7_ach_new_out, day2.n_accounts_active_7d) == (3.0, 3.0, 3.0, 3.0)


def test_transfers_inside_the_owner_are_not_counterparties(owner):
    day3 = owner[("o6", "out")]
    assert day3.p1_n_out == 2.0                    # o4 and the internal o5
    assert day3.p7_cp_out == 4.0                   # x1, x2, x3, x4 - not acc3
    assert day3.n_accounts_active_7d == 3.0        # acc1, acc2 and acc3 all paid out in the previous 7 days


def test_an_account_missing_from_the_accounts_file_is_its_own_owner(owner):
    assert owner[("o1", "in")].d0_n_in == 0.0      # x1 is not in the accounts file
    assert owner[("o4", "in")].n_accounts_active_7d == 0.0
