"""Risk memory: what the first-stage model already thought of each account's recent payments.

Two-stage detection. Stage 1 is the ordinary M1 model (`FEATURES`). It scores every transaction. Stage 2 sees the
same features plus these memory features, built from stage-1 scores of the sender's and the receiver's EARLIER
payments (earlier minutes of the same day and the 7 whole days before, the same point-in-time rule as every other
feature). Laundering moves through accounts that were recently involved in other suspicious-looking payments: a
stack or a chain looks ordinary hop by hop, but the account in the middle has just received money the model
already found risky.

In production this is exactly what is known at payment time: the earlier payments were scored when they happened.

Training must not use in-sample stage-1 scores (stage 1 memorised its own training rows, so their scores are too
confident). `trustnova_ml.train.out_of_fold` scores the training sample with models that never saw those rows.
"""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

MEMORY_DAYS = 7
MEMORY_HOT = 0.5  # a stage-1 score at or above this counts as a "hot" payment
SIDE_MEMORY = ("mem_max_in", "mem_max_out", "mem_sum_in", "mem_sum_out", "mem_n_hot")
MEMORY_FEATURES = (*[f"s_{c}" for c in SIDE_MEMORY], *[f"r_{c}" for c in SIDE_MEMORY])


def _side_memory(scored: DataFrame) -> DataFrame:
    """One row per (txn_id, direction): the account's stage-1 score history just before that transaction."""
    cols = ["txn_id", "variant", "sec", "day", "stage1"]
    ev = (scored.select(*cols, F.col("from_account").alias("account_id"), F.lit("out").alias("direction"))
          .unionByName(scored.select(*cols, F.col("to_account").alias("account_id"), F.lit("in").alias("direction"))))
    out, inn = F.col("direction") == "out", F.col("direction") == "in"
    s1 = F.col("stage1").cast("double")
    hot = F.when(s1 >= MEMORY_HOT, 1).otherwise(0)

    # earlier minutes of the same day (IBM timestamps are whole minutes, so -1 second means an earlier minute)
    before = (Window.partitionBy("variant", "account_id", "day").orderBy("sec")
              .rangeBetween(Window.unboundedPreceding, -1))
    ev = (ev.withColumn("_d0_max_in", F.max(F.when(inn, s1)).over(before))
            .withColumn("_d0_max_out", F.max(F.when(out, s1)).over(before))
            .withColumn("_d0_sum_in", F.sum(F.when(inn, s1)).over(before))
            .withColumn("_d0_sum_out", F.sum(F.when(out, s1)).over(before))
            .withColumn("_d0_hot", F.sum(hot).over(before)))

    daily = ev.groupBy("variant", "account_id", "day").agg(
        F.max(F.when(inn, s1)).alias("_max_in"), F.max(F.when(out, s1)).alias("_max_out"),
        F.sum(F.when(inn, s1)).alias("_sum_in"), F.sum(F.when(out, s1)).alias("_sum_out"),
        F.sum(hot).alias("_hot"))
    prior = Window.partitionBy("variant", "account_id").orderBy("day").rangeBetween(-MEMORY_DAYS, -1)
    hist = daily.select(
        "variant", "account_id", "day",
        F.max("_max_in").over(prior).alias("_p_max_in"), F.max("_max_out").over(prior).alias("_p_max_out"),
        F.sum("_sum_in").over(prior).alias("_p_sum_in"), F.sum("_sum_out").over(prior).alias("_p_sum_out"),
        F.sum("_hot").over(prior).alias("_p_hot"))

    z = F.lit(0.0)
    s = ev.join(hist, ["variant", "account_id", "day"])
    return s.select(
        "txn_id", "direction",
        F.coalesce(F.greatest("_d0_max_in", "_p_max_in"), z).alias("mem_max_in"),
        F.coalesce(F.greatest("_d0_max_out", "_p_max_out"), z).alias("mem_max_out"),
        (F.coalesce("_d0_sum_in", z) + F.coalesce("_p_sum_in", z)).alias("mem_sum_in"),
        (F.coalesce("_d0_sum_out", z) + F.coalesce("_p_sum_out", z)).alias("mem_sum_out"),
        (F.coalesce("_d0_hot", z) + F.coalesce("_p_hot", z)).cast("double").alias("mem_n_hot"))


def memory_features(scored: DataFrame) -> DataFrame:
    """`scored`: txn_id, variant, from_account, to_account, sec, day, stage1 for every transaction of the simulations.
    Returns txn_id + MEMORY_FEATURES (s_ = the sender's history, r_ = the receiver's)."""
    sides = _side_memory(scored)
    s = sides.where(F.col("direction") == "out").select("txn_id", *[F.col(c).alias(f"s_{c}") for c in SIDE_MEMORY])
    r = sides.where(F.col("direction") == "in").select("txn_id", *[F.col(c).alias(f"r_{c}") for c in SIDE_MEMORY])
    return s.join(r, "txn_id")
