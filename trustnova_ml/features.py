"""Point-in-time features for every transaction, from the sender's and the receiver's history.

A transaction at time t only sees activity strictly before its own minute: earlier minutes of the same day, and
whole earlier days. Same-minute and later activity never leaks in. Labels, pattern ids and `variant` are never
features (`variant` encodes the simulation's laundering rate), and neither are synthetic customer profile fields.
"""

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

EPOCH = "2022-01-01"
WINDOW_DAYS = (1, 7, 28)
CYCLE_DAYS = 7
BAND_LOW_USD, BAND_HIGH_USD = 7000, 10000  # the structuring band AML Copilot's rule uses
PAYMENT_FORMATS = ("ACH", "Bitcoin", "Cash", "Cheque", "Credit Card", "Reinvestment", "Wire")

DAILY_METRICS = ("n_out", "n_in", "usd_out", "usd_in", "cp_out", "cp_in", "band_out", "band_in", "cash_out", "crypto_out")
INTRADAY = ("d0_n_out", "d0_n_in", "d0_usd_out", "d0_usd_in")
SIDE_FEATURES = (*INTRADAY, *[f"p{w}_{m}" for w in WINDOW_DAYS for m in DAILY_METRICS], "account_age_days")
TXN_FEATURES = ("log_amount_usd", "payment_format_code", "currency_change", "cross_bank", "is_self_transfer",
                "hour", "weekday", "in_band", "round_amount", "first_time_pair", "reverse_n_7d", "reverse_usd_7d")
FEATURES = (*TXN_FEATURES, *[f"s_{c}" for c in SIDE_FEATURES], *[f"r_{c}" for c in SIDE_FEATURES])
CATEGORICAL = ("payment_format_code",)
BANNED = ("is_laundering", "attempt_id", "pattern_type", "variant", "entity_id", "entity_name")


def with_time(df: DataFrame) -> DataFrame:
    ts = F.col("ts").cast("timestamp")
    return (df.withColumn("sec", F.unix_timestamp(ts))
            .withColumn("day", F.datediff(F.to_date(F.col("ts")), F.lit(EPOCH))))


def _flag(c: Column) -> Column:
    return F.when(c, 1).otherwise(0)


def side_features(edges: DataFrame) -> DataFrame:
    """One row per (txn_id, direction): the account's history at the moment of that transaction."""
    out, inn = F.col("direction") == "out", F.col("direction") == "in"
    real = ~F.col("is_self_transfer")
    usd = F.col("amount_usd").cast("double")
    e = with_time(edges)

    same_day_before = (Window.partitionBy("variant", "account_id", "day").orderBy("sec")
                       .rangeBetween(Window.unboundedPreceding, -1))
    e = (e.withColumn("d0_n_out", F.coalesce(F.sum(_flag(out)).over(same_day_before), F.lit(0)))
          .withColumn("d0_n_in", F.coalesce(F.sum(_flag(inn)).over(same_day_before), F.lit(0)))
          .withColumn("d0_usd_out", F.coalesce(F.sum(F.when(out, usd)).over(same_day_before), F.lit(0.0)))
          .withColumn("d0_usd_in", F.coalesce(F.sum(F.when(inn, usd)).over(same_day_before), F.lit(0.0))))

    band = (usd >= BAND_LOW_USD) & (usd < BAND_HIGH_USD)
    daily = e.groupBy("variant", "account_id", "day").agg(
        F.sum(_flag(out)).alias("n_out"),
        F.sum(_flag(inn)).alias("n_in"),
        F.coalesce(F.sum(F.when(out, usd)), F.lit(0.0)).alias("usd_out"),
        F.coalesce(F.sum(F.when(inn, usd)), F.lit(0.0)).alias("usd_in"),
        F.countDistinct(F.when(out & real, F.col("counterparty_id"))).alias("cp_out"),
        F.countDistinct(F.when(inn & real, F.col("counterparty_id"))).alias("cp_in"),
        F.sum(_flag(out & band)).alias("band_out"),
        F.sum(_flag(inn & band)).alias("band_in"),
        F.sum(_flag(out & (F.col("payment_format") == "Cash"))).alias("cash_out"),
        F.sum(_flag(out & (F.col("payment_format") == "Bitcoin"))).alias("crypto_out"),
    )
    hist = daily
    by_account = Window.partitionBy("variant", "account_id").orderBy("day")
    for w in WINDOW_DAYS:
        prior = by_account.rangeBetween(-w, -1)  # whole earlier days only
        for m in DAILY_METRICS:
            hist = hist.withColumn(f"p{w}_{m}", F.coalesce(F.sum(m).over(prior), F.lit(0)).cast("double"))
    first_day = F.min("day").over(by_account.rangeBetween(Window.unboundedPreceding, -1))
    hist = hist.withColumn("account_age_days", F.coalesce(F.col("day") - first_day, F.lit(0)))
    # today's totals include activity after the transaction, so they are dropped (only the d0_* prefixes survive)
    hist = hist.drop(*DAILY_METRICS)

    return (e.join(hist, ["variant", "account_id", "day"])
            .select("txn_id", "direction", *[F.col(c).cast("double").alias(c) for c in SIDE_FEATURES]))


def _prefixed(sides: DataFrame, direction: str, prefix: str) -> DataFrame:
    return sides.where(F.col("direction") == direction).select(
        "txn_id", *[F.col(c).alias(f"{prefix}{c}") for c in SIDE_FEATURES])


def transaction_features(tx: DataFrame, edges: DataFrame) -> DataFrame:
    """All model features for every transaction, plus the keys needed downstream (no label)."""
    t = with_time(tx)
    usd = F.col("amount_paid_usd").cast("double")
    fmt_code = F.coalesce(F.array_position(F.array(*[F.lit(f) for f in PAYMENT_FORMATS]), F.col("payment_format")) - 1,
                          F.lit(-1)).cast("double")
    pair_first = F.row_number().over(Window.partitionBy("variant", "from_account", "to_account").orderBy("sec", "txn_id"))
    base = t.select(
        "txn_id", "variant", "ts", "sec", "day", "from_account", "to_account",
        F.log1p(usd).alias("log_amount_usd"),
        fmt_code.alias("payment_format_code"),
        _flag(F.col("paid_currency") != F.col("received_currency")).cast("double").alias("currency_change"),
        _flag(F.col("from_bank") != F.col("to_bank")).cast("double").alias("cross_bank"),
        _flag(F.col("is_self_transfer")).cast("double").alias("is_self_transfer"),
        F.hour(F.col("ts").cast("timestamp")).cast("double").alias("hour"),
        F.dayofweek(F.col("ts").cast("timestamp")).cast("double").alias("weekday"),
        _flag((usd >= BAND_LOW_USD) & (usd < BAND_HIGH_USD)).cast("double").alias("in_band"),
        _flag((usd >= 100) & (F.pmod(usd, F.lit(100.0)) == 0)).cast("double").alias("round_amount"),
        _flag(pair_first == 1).cast("double").alias("first_time_pair"),
    )

    # Money coming back: an earlier transaction from this receiver to this sender within CYCLE_DAYS.
    real = t.where(~F.col("is_self_transfer"))
    earlier_reverse = real.select(
        "variant", F.col("to_account").alias("from_account"), F.col("from_account").alias("to_account"),
        F.col("sec").alias("rev_sec"), F.col("amount_paid_usd").cast("double").alias("rev_usd"))
    cycles = (real.select("txn_id", "variant", "from_account", "to_account", "sec")
              .join(earlier_reverse, ["variant", "from_account", "to_account"])
              .where((F.col("rev_sec") < F.col("sec")) & (F.col("rev_sec") >= F.col("sec") - CYCLE_DAYS * 86400))
              .groupBy("txn_id").agg(F.count("*").cast("double").alias("reverse_n_7d"),
                                     F.sum("rev_usd").alias("reverse_usd_7d")))

    sides = side_features(edges)
    side_cols = [f"{p}{c}" for p in ("s_", "r_") for c in SIDE_FEATURES]
    return (base.join(_prefixed(sides, "out", "s_"), "txn_id", "left")
            .join(_prefixed(sides, "in", "r_"), "txn_id", "left")
            .join(cycles, "txn_id", "left")
            .fillna(0.0, subset=[*side_cols, "reverse_n_7d", "reverse_usd_7d"]))


def assign_split(features: DataFrame, train: float = 0.6, valid: float = 0.8) -> DataFrame:
    """Temporal split per simulation: the earliest 60% of its transactions train, the next 20% validate, the last
    20% test. Each simulation covers different dates, so each is split on its own timeline."""
    q = features.groupBy("variant").agg(F.percentile_approx("sec", [train, valid], 100000).alias("_q"))
    return (features.join(F.broadcast(q), "variant")
            .withColumn("split", F.when(F.col("sec") < F.col("_q")[0], "train")
                        .when(F.col("sec") < F.col("_q")[1], "valid").otherwise("test"))
            .drop("_q"))
