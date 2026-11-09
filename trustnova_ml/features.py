"""Point-in-time features for every transaction, from the sender's and the receiver's history.

A transaction at time t only sees activity strictly before its own minute: earlier minutes of the same day, and
whole earlier days. Same-minute and later activity never leaks in. Labels, pattern ids and `variant` are never
features (`variant` encodes the simulation's laundering rate), and neither are synthetic customer profile fields.

Feature families
    transaction    amount, payment format, currency change, bank, time, band, round amount, first-time pair
    history        per side (sender s_, receiver r_): earlier today, previous 1 / 7 / 28 days
    unusual-for-this-account   amount z-score against the account's own 28 days, bursts against its normal daily
                   rate, share of new counterparties, first use of a payment format (for laundering hidden in the
                   normal-looking traffic of busy accounts)
    multi-hop      money coming straight back (2-step), 3-step cycles through a low-degree intermediary, minutes
                   since money last came in, and the payment against what came in over the last day (pass-through)
    ACH flow       ACH payments in and out, and those with a counterparty never seen before: the labelled laundering
                   patterns move money by ACH between new pairs, so ACH arriving from new counterparties and then
                   leaving again is the upstream half of a layering chain
    owner          from the IBM accounts file: the owner's type (individual, sole proprietorship, partnership,
                   corporation...) and how many accounts and banks it has. These are account-opening (KYC) facts, not
                   activity, so they are the same at every point in time
"""

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

EPOCH = "2022-01-01"
WINDOW_DAYS = (1, 7, 28)
CYCLE_DAYS = 7
MAX_INTERMEDIARY_TXNS = 500  # 3-step cycles only through accounts with at most this many transactions (no hubs)
BAND_LOW_USD, BAND_HIGH_USD = 7000, 10000  # the structuring band AML Copilot's rule uses
PAYMENT_FORMATS = ("ACH", "Bitcoin", "Cash", "Cheque", "Credit Card", "Reinvestment", "Wire")
DAY = 86400

DAILY_METRICS = ("n_out", "n_in", "usd_out", "usd_in", "cp_out", "cp_in", "band_out", "band_in", "cash_out",
                 "crypto_out", "usd_out_sq", "usd_in_sq", "new_cp_out", "new_cp_in",
                 "ach_out", "ach_in", "ach_new_out", "ach_new_in")
INTRADAY = ("d0_n_out", "d0_n_in", "d0_usd_out", "d0_usd_in", "d0_ach_new_in")
DERIVED = ("amount_z_28d", "burst_vs_28d", "new_cp_share_7d", "format_first", "minutes_since_in", "vs_inflow_24h")
SIDE_FEATURES = (*INTRADAY, *[f"p{w}_{m}" for w in WINDOW_DAYS for m in DAILY_METRICS], "account_age_days", *DERIVED)
TXN_FEATURES = ("log_amount_usd", "payment_format_code", "currency_change", "cross_bank", "is_self_transfer",
                "hour", "weekday", "in_band", "round_amount", "first_time_pair", "reverse_n_7d", "reverse_usd_7d",
                "closes_3cycle_7d")
ENTITY_TYPES = ("Individual", "Sole Proprietorship", "Partnership", "Corporation", "Country", "Direct")
OWNER_FEATURES = ("entity_type_code", "owner_n_accounts", "owner_n_banks")
FEATURES = (*TXN_FEATURES, *[f"s_{c}" for c in SIDE_FEATURES], *[f"r_{c}" for c in SIDE_FEATURES],
            *[f"s_{c}" for c in OWNER_FEATURES], *[f"r_{c}" for c in OWNER_FEATURES])
CATEGORICAL = ("payment_format_code", "s_entity_type_code", "r_entity_type_code")
BANNED = ("is_laundering", "attempt_id", "pattern_type", "variant", "entity_id", "entity_name")


def with_time(df: DataFrame) -> DataFrame:
    ts = F.col("ts").cast("timestamp")
    return (df.withColumn("sec", F.unix_timestamp(ts))
            .withColumn("day", F.datediff(F.to_date(F.col("ts")), F.lit(EPOCH))))


def _flag(c: Column) -> Column:
    return F.when(c, 1).otherwise(0)


def _ratio(num: Column, den: Column) -> Column:
    return F.when(den > 0, num / den).otherwise(F.lit(0.0))


def side_features(edges: DataFrame) -> DataFrame:
    """One row per (txn_id, direction): the account's history at the moment of that transaction."""
    out, inn = F.col("direction") == "out", F.col("direction") == "in"
    real = ~F.col("is_self_transfer")
    ach = F.col("payment_format") == "ACH"
    usd = F.col("amount_usd").cast("double")
    e = with_time(edges)

    first_of = lambda *keys: F.row_number().over(Window.partitionBy("variant", "account_id", "direction", *keys)
                                                  .orderBy("sec", "txn_id")) == 1
    e = (e.withColumn("_new_cp", first_of("counterparty_id") & real)
          .withColumn("format_first", _flag(first_of("payment_format")).cast("double")))

    same_day_before = (Window.partitionBy("variant", "account_id", "day").orderBy("sec")
                       .rangeBetween(Window.unboundedPreceding, -1))
    e = (e.withColumn("d0_n_out", F.coalesce(F.sum(_flag(out)).over(same_day_before), F.lit(0)))
          .withColumn("d0_n_in", F.coalesce(F.sum(_flag(inn)).over(same_day_before), F.lit(0)))
          .withColumn("d0_usd_out", F.coalesce(F.sum(F.when(out, usd)).over(same_day_before), F.lit(0.0)))
          .withColumn("d0_usd_in", F.coalesce(F.sum(F.when(inn, usd)).over(same_day_before), F.lit(0.0)))
          .withColumn("d0_ach_new_in", F.coalesce(F.sum(_flag(inn & ach & F.col("_new_cp"))).over(same_day_before), F.lit(0)))
          .withColumn("_d0_last_in", F.max(F.when(inn, F.col("sec"))).over(same_day_before)))

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
        F.coalesce(F.sum(F.when(out, usd * usd)), F.lit(0.0)).alias("usd_out_sq"),
        F.coalesce(F.sum(F.when(inn, usd * usd)), F.lit(0.0)).alias("usd_in_sq"),
        F.sum(_flag(out & F.col("_new_cp"))).alias("new_cp_out"),
        F.sum(_flag(inn & F.col("_new_cp"))).alias("new_cp_in"),
        F.sum(_flag(out & ach)).alias("ach_out"),
        F.sum(_flag(inn & ach)).alias("ach_in"),
        F.sum(_flag(out & ach & F.col("_new_cp"))).alias("ach_new_out"),
        F.sum(_flag(inn & ach & F.col("_new_cp"))).alias("ach_new_in"),
        F.max(F.when(inn, F.col("sec"))).alias("_last_in"),
    )
    hist = daily
    by_account = Window.partitionBy("variant", "account_id").orderBy("day")
    for w in WINDOW_DAYS:
        prior = by_account.rangeBetween(-w, -1)  # whole earlier days only
        for m in DAILY_METRICS:
            hist = hist.withColumn(f"p{w}_{m}", F.coalesce(F.sum(m).over(prior), F.lit(0)).cast("double"))
    first_day = F.min("day").over(by_account.rangeBetween(Window.unboundedPreceding, -1))
    hist = (hist.withColumn("account_age_days", F.coalesce(F.col("day") - first_day, F.lit(0)))
            .withColumn("_p28_last_in", F.max("_last_in").over(by_account.rangeBetween(-28, -1))))
    # today's totals include activity after the transaction, so they are dropped (only the d0_* prefixes survive)
    hist = hist.drop(*DAILY_METRICS, "_last_in")

    s = e.join(hist, ["variant", "account_id", "day"])
    # the account's own normal, in the direction of this transaction
    n28 = F.when(out, F.col("p28_n_out")).otherwise(F.col("p28_n_in"))
    s28 = F.when(out, F.col("p28_usd_out")).otherwise(F.col("p28_usd_in"))
    q28 = F.when(out, F.col("p28_usd_out_sq")).otherwise(F.col("p28_usd_in_sq"))
    mean = _ratio(s28, n28)
    var = F.greatest(_ratio(q28, n28) - mean * mean, F.lit(0.0))
    z = F.when((n28 >= 2) & (var > 1e-6), (usd - mean) / F.sqrt(var)).otherwise(F.lit(0.0))
    d0_n = F.when(out, F.col("d0_n_out")).otherwise(F.col("d0_n_in"))
    new7 = F.when(out, F.col("p7_new_cp_out")).otherwise(F.col("p7_new_cp_in"))
    n7 = F.when(out, F.col("p7_n_out")).otherwise(F.col("p7_n_in"))
    last_in = F.coalesce(F.col("_d0_last_in"), F.col("_p28_last_in"))
    s = (s.withColumn("amount_z_28d", F.least(F.greatest(z, F.lit(-50.0)), F.lit(50.0)))
          .withColumn("burst_vs_28d", (d0_n + 1) / (n28 / 28 + 1))
          .withColumn("new_cp_share_7d", _ratio(new7, n7))
          .withColumn("minutes_since_in", F.when(last_in.isNull(), F.lit(-1.0)).otherwise((F.col("sec") - last_in) / 60))
          .withColumn("vs_inflow_24h", usd / (F.col("d0_usd_in") + F.col("p1_usd_in") + 1)))

    return s.select("txn_id", "direction", *[F.col(c).cast("double").alias(c) for c in SIDE_FEATURES])


def _prefixed(sides: DataFrame, direction: str, prefix: str) -> DataFrame:
    return sides.where(F.col("direction") == direction).select(
        "txn_id", *[F.col(c).alias(f"{prefix}{c}") for c in SIDE_FEATURES])


def owner_attributes(accounts: DataFrame) -> DataFrame:
    """One row per account: its owner's type and how many accounts and banks the owner has (in that simulation)."""
    owners = accounts.groupBy("variant", "entity_id").agg(F.count("*").cast("double").alias("owner_n_accounts"),
                                                         F.countDistinct("bank_id").cast("double").alias("owner_n_banks"))
    code = F.coalesce(F.array_position(F.array(*[F.lit(t) for t in ENTITY_TYPES]), F.col("entity_type")) - 1, F.lit(-1))
    return (accounts.join(owners, ["variant", "entity_id"])
            .groupBy("account_id").agg(F.first(code.cast("double")).alias("entity_type_code"),
                                       F.first("owner_n_accounts").alias("owner_n_accounts"),
                                       F.first("owner_n_banks").alias("owner_n_banks")))


def _owner(owners: DataFrame, key: str, prefix: str) -> DataFrame:
    return owners.select(F.col("account_id").alias(key), *[F.col(c).alias(f"{prefix}{c}") for c in OWNER_FEATURES])


def money_back(real: DataFrame) -> DataFrame:
    """2-step: an earlier transaction from this receiver to this sender within CYCLE_DAYS."""
    earlier_reverse = real.select(
        "variant", F.col("to_account").alias("from_account"), F.col("from_account").alias("to_account"),
        F.col("sec").alias("rev_sec"), F.col("amount_paid_usd").cast("double").alias("rev_usd"))
    return (real.select("txn_id", "variant", "from_account", "to_account", "sec")
            .join(earlier_reverse, ["variant", "from_account", "to_account"])
            .where((F.col("rev_sec") < F.col("sec")) & (F.col("rev_sec") >= F.col("sec") - CYCLE_DAYS * DAY))
            .groupBy("txn_id").agg(F.count("*").cast("double").alias("reverse_n_7d"),
                                   F.sum("rev_usd").alias("reverse_usd_7d")))


def three_step_cycles(real: DataFrame) -> DataFrame:
    """3-step: this payment A->B closes a loop when B->X and then X->A already happened within CYCLE_DAYS.
    Intermediaries X are limited to accounts with at most MAX_INTERMEDIARY_TXNS transactions, so hub accounts
    (which would join with millions of rows) are skipped; laundering intermediaries are rarely hubs."""
    deg = (real.select("variant", F.col("from_account").alias("x"))
           .unionByName(real.select("variant", F.col("to_account").alias("x")))
           .groupBy("variant", "x").count().where(F.col("count") <= MAX_INTERMEDIARY_TXNS).select("variant", "x"))
    b_to_x = real.select("variant", F.col("from_account").alias("b"), F.col("to_account").alias("x"),
                         F.col("sec").alias("s1")).join(deg, ["variant", "x"])
    x_to_a = real.select("variant", F.col("from_account").alias("x"), F.col("to_account").alias("a"),
                         F.col("sec").alias("s2")).join(deg, ["variant", "x"])
    paths = (b_to_x.join(x_to_a, ["variant", "x"])
             .where((F.col("s1") < F.col("s2")) & (F.col("s2") - F.col("s1") <= CYCLE_DAYS * DAY) & (F.col("a") != F.col("b")))
             .select("variant", "a", "b", "s1", "s2"))
    now = real.select("txn_id", "variant", F.col("from_account").alias("a"), F.col("to_account").alias("b"), "sec")
    return (now.join(paths, ["variant", "a", "b"])
            .where((F.col("s2") < F.col("sec")) & (F.col("s1") >= F.col("sec") - CYCLE_DAYS * DAY))
            .groupBy("txn_id").agg(F.count("*").cast("double").alias("closes_3cycle_7d")))


def transaction_features(tx: DataFrame, edges: DataFrame, accounts: DataFrame) -> DataFrame:
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
    real = t.where(~F.col("is_self_transfer"))
    sides = side_features(edges)
    side_cols = [f"{p}{c}" for p in ("s_", "r_") for c in SIDE_FEATURES]
    owners = owner_attributes(accounts)
    return (base.join(_prefixed(sides, "out", "s_"), "txn_id", "left")
            .join(_prefixed(sides, "in", "r_"), "txn_id", "left")
            .join(money_back(real), "txn_id", "left")
            .join(three_step_cycles(real), "txn_id", "left")
            .join(_owner(owners, "from_account", "s_"), "from_account", "left")
            .join(_owner(owners, "to_account", "r_"), "to_account", "left")
            .fillna(0.0, subset=[*side_cols, "reverse_n_7d", "reverse_usd_7d", "closes_3cycle_7d",
                                 *[f"{p}{c}" for p in ("s_", "r_") for c in OWNER_FEATURES[1:]]])
            .fillna(-1.0, subset=["s_entity_type_code", "r_entity_type_code"]))


def assign_split(features: DataFrame, train: float = 0.6, valid: float = 0.8) -> DataFrame:
    """Temporal split per simulation: the earliest 60% of its transactions train, the next 20% validate, the last
    20% test. Each simulation covers different dates, so each is split on its own timeline."""
    q = features.groupBy("variant").agg(F.percentile_approx("sec", [train, valid], 100000).alias("_q"))
    return (features.join(F.broadcast(q), "variant")
            .withColumn("split", F.when(F.col("sec") < F.col("_q")[0], "train")
                        .when(F.col("sec") < F.col("_q")[1], "valid").otherwise("test"))
            .drop("_q"))
