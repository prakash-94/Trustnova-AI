"""Risk memory (stage-2 features) on a small hand-made history, where the right answers are known."""

import pytest

pytest.importorskip("pyspark")

from pyspark.sql import functions as F

from trustnova_ml.features import EPOCH
from trustnova_ml.memory import MEMORY_FEATURES, memory_features

H, D = 3600, 86400
T0 = 1_662_364_800  # 2022-09-05 08:00 UTC

# (txn_id, from, to, seconds after T0, stage-1 score)
HISTORY = [
    ("e1", "X", "A", 0, 0.9),          # A receives a hot payment
    ("e2", "A", "B", H, 0.2),          # A pays on, an hour later
    ("e3", "A", "C", H, 0.3),          # same minute as e2: neither sees the other
    ("e6", "B", "A", 3 * H, 0.4),      # later the same day, back into A
    ("e4", "A", "D", 2 * D, 0.6),      # two days later: sees the whole first day
    ("e5", "A", "E", 9 * D, 0.1),      # nine days later: the first day is out of the 7-day window
]


def _scored(spark, rows):
    df = spark.createDataFrame(rows, "txn_id string, from_account string, to_account string, s long, stage1 double")
    sec = F.col("s") + T0
    return df.select("txn_id", F.lit("HIS").alias("variant"), "from_account", "to_account", sec.alias("sec"),
                     F.datediff(F.to_date(F.from_unixtime(sec)), F.lit(EPOCH)).alias("day"), "stage1")


@pytest.fixture(scope="module")
def mem(spark):
    return {r.txn_id: r.asDict() for r in memory_features(_scored(spark, HISTORY)).collect()}


def test_every_transaction_gets_every_feature(mem):
    assert set(mem) == {"e1", "e2", "e3", "e4", "e5", "e6"}
    assert all(set(MEMORY_FEATURES) <= set(v) for v in mem.values())


def test_the_sender_remembers_the_hot_payment_it_just_received(mem):
    e2 = mem["e2"]
    assert e2["s_mem_max_in"] == pytest.approx(0.9)
    assert e2["s_mem_n_hot"] == 1
    assert e2["s_mem_max_out"] == 0  # e3 happened in the same minute, so it is not "before"
    assert e2["r_mem_max_in"] == 0 and e2["r_mem_max_out"] == 0  # B has no history yet
    assert mem["e3"]["s_mem_max_out"] == 0


def test_the_receiver_side_and_sums(mem):
    e6 = mem["e6"]
    assert e6["r_mem_max_in"] == pytest.approx(0.9)
    assert e6["r_mem_max_out"] == pytest.approx(0.3)
    assert e6["r_mem_sum_out"] == pytest.approx(0.5)
    assert e6["s_mem_max_in"] == pytest.approx(0.2)  # B received e2 earlier


def test_earlier_days_count_for_seven_days_only(mem):
    e4 = mem["e4"]
    assert (e4["s_mem_max_in"], e4["s_mem_max_out"]) == (pytest.approx(0.9), pytest.approx(0.3))
    assert e4["s_mem_sum_in"] == pytest.approx(1.3) and e4["s_mem_sum_out"] == pytest.approx(0.5)
    e5 = mem["e5"]
    assert e5["s_mem_max_in"] == 0  # the first day is now 9 days back
    assert e5["s_mem_max_out"] == pytest.approx(0.6) and e5["s_mem_n_hot"] == 1


def test_memory_never_looks_ahead(spark, mem):
    early = {r.txn_id: r.asDict() for r in memory_features(_scored(spark, HISTORY[:3])).collect()}
    for t in ("e1", "e2", "e3"):
        assert early[t] == mem[t]
