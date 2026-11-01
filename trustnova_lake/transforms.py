"""Spark transforms for the IBM AML lakehouse. Every function is DataFrame in -> DataFrame out, with no I/O, so the
same code runs in the Databricks jobs and in the local tests. Nothing here uses RDDs, `sparkContext` or caching,
which Databricks serverless (Spark Connect) does not allow."""

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from trustnova_lake.ibm import NOT_A_COUNTRY, RAW_ACCOUNT_COLUMNS, RAW_TRANSACTION_COLUMNS, VARIANTS

AMOUNT = T.DecimalType(22, 6)  # Bitcoin amounts carry 6 decimals; the largest transfer is about 1.05e12
USD = T.DecimalType(22, 2)
TS_FORMAT = "yyyy/MM/dd HH:mm"
BANK_ZEROS = r"^0+(?=\d)"  # same rule as ibm.normalize_bank_id: "010" -> "10", "000" -> "0"
FX_MIN_SAMPLES = 20  # fewer direct X->USD conversions than this and the inverse USD->X rate is used instead

RAW_TRANSACTION_SCHEMA = T.StructType([T.StructField(c, T.StringType(), False) for c in RAW_TRANSACTION_COLUMNS])
RAW_ACCOUNT_SCHEMA = T.StructType([T.StructField(c, T.StringType(), False) for c in RAW_ACCOUNT_COLUMNS])

# The typed columns that identify a transaction; patterns are matched to transactions on exactly these.
TXN_KEY = ("variant", "ts", "from_account", "to_account", "amount_received", "received_currency",
           "amount_paid", "paid_currency", "payment_format")


def variant_from_file(path: Column) -> Column:
    """`.../HI-Large_Trans.part-002.csv` -> "HIL" (null for anything else)."""
    prefix = F.regexp_extract(path, r"((?:HI|LI)-(?:Small|Medium|Large))_", 1)
    mapping = F.create_map(*[F.lit(x) for kv in VARIANTS.items() for x in kv])
    return F.element_at(mapping, prefix)


def _bank(c: Column) -> Column:
    return F.regexp_replace(c, BANK_ZEROS, "")


def _account(variant: Column, bank: Column, account: Column) -> Column:
    return F.concat_ws(":", variant, _bank(bank), account)


def _try_cast(col: str, sql_type: str) -> Column:
    # SQL try_cast: a bad value becomes null (counted by the quality gate) instead of failing the job under ANSI mode.
    return F.expr(f"try_cast(`{col}` AS {sql_type})")


def typed_transactions(raw: DataFrame) -> DataFrame:
    """Raw string rows (the 11 file columns plus `variant`) -> typed rows. Works for *_Trans.csv rows and for the
    transaction lines of *_Patterns.txt, which is what lets patterns be joined back to transactions exactly."""
    v = F.col("variant")
    return raw.select(
        v.alias("variant"),
        # The files carry wall-clock times with no zone, so they are kept as TIMESTAMP_NTZ (never shifted by a zone).
        F.expr(f"CAST(try_to_timestamp(`timestamp`, '{TS_FORMAT}') AS TIMESTAMP_NTZ)").alias("ts"),
        _bank(F.col("from_bank")).alias("from_bank"),
        _account(v, F.col("from_bank"), F.col("from_account")).alias("from_account"),
        _bank(F.col("to_bank")).alias("to_bank"),
        _account(v, F.col("to_bank"), F.col("to_account")).alias("to_account"),
        _try_cast("amount_received", "DECIMAL(22,6)").alias("amount_received"),
        F.col("receiving_currency").alias("received_currency"),
        _try_cast("amount_paid", "DECIMAL(22,6)").alias("amount_paid"),
        F.col("payment_currency").alias("paid_currency"),
        F.col("payment_format").alias("payment_format"),
        _try_cast("is_laundering", "INT").alias("is_laundering"),
        *[F.col(c) for c in raw.columns if c not in (*RAW_TRANSACTION_COLUMNS, "variant")],
    ).withColumn("is_self_transfer", F.col("from_account") == F.col("to_account"))


def with_txn_ids(typed: DataFrame) -> DataFrame:
    """Deterministic ids without a global sort (a row number over 180M rows would be one huge partition):
    `{variant}-{first 24 hex of sha256(all fields)}-{n}`, where n numbers exact duplicate rows 1, 2, ..."""
    fields = [*TXN_KEY, "is_laundering"]
    digest = F.substring(F.sha2(F.concat_ws("|", *[F.col(c).cast("string") for c in fields]), 256), 1, 24)
    dup = F.row_number().over(Window.partitionBy("variant", "_h").orderBy(F.lit(1)))
    return (typed.withColumn("_h", digest)
            .withColumn("txn_id", F.concat_ws("-", F.col("variant"), F.col("_h"), dup.cast("string")))
            .drop("_h"))


def split_ground_truth(with_ids: DataFrame) -> tuple[DataFrame, DataFrame]:
    """-> (transactions without the label, labels). The label leaves Silver here and lives only in `restricted`."""
    labels = with_ids.select("txn_id", "variant", "is_laundering")
    return with_ids.drop("is_laundering"), labels


def fx_rates(typed: DataFrame) -> DataFrame:
    """USD rate per (variant, currency), measured from the data's own currency conversions: the median of
    received/paid for X->USD rows, else the inverse of the USD->X median (Bitcoin is only ever bought with USD)."""
    cross = (typed.where((F.col("paid_currency") != F.col("received_currency")) & (F.col("amount_paid") > 1))
             .withColumn("ratio", (F.col("amount_received") / F.col("amount_paid")).cast("double")))
    pairs = cross.groupBy("variant", "paid_currency", "received_currency").agg(
        F.percentile_approx("ratio", 0.5, 10000).alias("median"),
        F.percentile_approx("ratio", 0.05, 10000).alias("p05"),
        F.percentile_approx("ratio", 0.95, 10000).alias("p95"),
        F.count("*").alias("samples"),
    )
    direct = pairs.where(F.col("received_currency") == "US Dollar").select(
        "variant", F.col("paid_currency").alias("currency"), F.col("median").alias("usd_rate"),
        ((F.col("p95") - F.col("p05")) / F.col("median")).alias("spread"), "samples",
        F.lit("direct").alias("method"))
    inverse = pairs.where(F.col("paid_currency") == "US Dollar").select(
        "variant", F.col("received_currency").alias("currency"), (F.lit(1.0) / F.col("median")).alias("usd_rate"),
        ((F.col("p95") - F.col("p05")) / F.col("median")).alias("spread"), "samples",
        F.lit("inverse").alias("method"))
    priority = (F.when((F.col("method") == "direct") & (F.col("samples") >= FX_MIN_SAMPLES), 0)
                .when(F.col("method") == "inverse", 1).otherwise(2))
    best = (direct.unionByName(inverse).withColumn("_p", priority)
            .withColumn("_r", F.row_number().over(Window.partitionBy("variant", "currency").orderBy("_p", F.desc("samples"))))
            .where(F.col("_r") == 1).drop("_p", "_r"))
    usd = (typed.select("variant").distinct()
           .select("variant", F.lit("US Dollar").alias("currency"), F.lit(1.0).alias("usd_rate"),
                   F.lit(0.0).alias("spread"), F.lit(0).cast("long").alias("samples"), F.lit("identity").alias("method")))
    return best.where(F.col("currency") != "US Dollar").unionByName(usd)


def with_usd(tx: DataFrame, fx: DataFrame) -> DataFrame:
    """Add amount_paid_usd and amount_received_usd. A currency without a rate gives null (the quality gate fails)."""
    rate = fx.select("variant", "currency", "usd_rate")
    paid = rate.withColumnRenamed("currency", "paid_currency").withColumnRenamed("usd_rate", "_paid_rate")
    recv = rate.withColumnRenamed("currency", "received_currency").withColumnRenamed("usd_rate", "_recv_rate")
    return (tx.join(F.broadcast(paid), ["variant", "paid_currency"], "left")
            .join(F.broadcast(recv), ["variant", "received_currency"], "left")
            .withColumn("amount_paid_usd", F.round(F.col("amount_paid").cast("double") * F.col("_paid_rate"), 2).cast(USD))
            .withColumn("amount_received_usd", F.round(F.col("amount_received").cast("double") * F.col("_recv_rate"), 2).cast(USD))
            .drop("_paid_rate", "_recv_rate"))


def typed_accounts(raw: DataFrame) -> DataFrame:
    """Raw *_accounts.csv rows plus `variant` -> one row per account with its owner (entity) and bank country."""
    v = F.col("variant")
    country = F.regexp_extract("bank_name", r"^(.+?) Bank #\d+$", 1)
    return raw.select(
        v.alias("variant"),
        _account(v, F.col("bank_id"), F.col("account_number")).alias("account_id"),
        _bank(F.col("bank_id")).alias("bank_id"),
        F.col("account_number"),
        F.concat_ws(":", v, F.col("entity_id")).alias("entity_id"),
        F.col("entity_name"),
        F.trim(F.regexp_replace("entity_name", r"\s*#\d+$", "")).alias("entity_type"),
        F.col("bank_name"),
        F.when((country != "") & ~country.isin(*NOT_A_COUNTRY), country).alias("bank_country"),
    )


def match_patterns(pattern_typed: DataFrame, transactions: DataFrame) -> DataFrame:
    """Typed pattern lines joined to transactions on every identifying field.
    Returns one row per pattern line with `matches` (0 = not found) and, when found, the matched txn_ids."""
    t = transactions.select(*TXN_KEY, "txn_id")
    joined = pattern_typed.join(t, list(TXN_KEY), "left")
    return joined.groupBy("variant", "attempt_id", "pattern_type", "pattern_detail", "attempt_line").agg(
        F.count("txn_id").alias("matches"), F.collect_list("txn_id").alias("txn_ids"))


def restricted_patterns(matched: DataFrame) -> DataFrame:
    """The ground-truth table: one row per (attempt, transaction)."""
    return (matched.where(F.col("matches") > 0)
            .select("variant", "attempt_id", "pattern_type", "pattern_detail",
                    F.col("attempt_line").cast("int").alias("attempt_line"), F.explode("txn_ids").alias("txn_id")))


def account_txn_edges(tx: DataFrame) -> DataFrame:
    """Two rows per transaction, one per account side, so one lookup by account returns money in and out."""
    common = ["ts", "payment_format", "is_self_transfer", "txn_id", "variant"]
    out = tx.select(F.col("from_account").alias("account_id"), F.col("to_account").alias("counterparty_id"),
                    F.lit("out").alias("direction"), F.col("amount_paid").alias("amount"),
                    F.col("paid_currency").alias("currency"), F.col("amount_paid_usd").alias("amount_usd"), *common)
    inc = tx.select(F.col("to_account").alias("account_id"), F.col("from_account").alias("counterparty_id"),
                    F.lit("in").alias("direction"), F.col("amount_received").alias("amount"),
                    F.col("received_currency").alias("currency"), F.col("amount_received_usd").alias("amount_usd"), *common)
    return out.unionByName(inc)


PAYMENT_FORMATS = ("ACH", "Bitcoin", "Cash", "Cheque", "Credit Card", "Reinvestment", "Wire")


def _fmt_col(name: str) -> str:
    return "n_" + name.lower().replace(" ", "_")


def account_summary(edges: DataFrame) -> DataFrame:
    """Per account: counts and USD totals each way, counterparties, activity dates and payment-format mix."""
    is_out, is_in = F.col("direction") == "out", F.col("direction") == "in"
    real = ~F.col("is_self_transfer")
    aggs = [
        F.sum(F.when(is_out, 1).otherwise(0)).alias("n_out"),
        F.sum(F.when(is_in, 1).otherwise(0)).alias("n_in"),
        F.sum(F.when(is_out, F.col("amount_usd"))).cast(USD).alias("usd_out"),
        F.sum(F.when(is_in, F.col("amount_usd"))).cast(USD).alias("usd_in"),
        F.countDistinct(F.when(is_out & real, F.col("counterparty_id"))).alias("counterparties_out"),
        F.countDistinct(F.when(is_in & real, F.col("counterparty_id"))).alias("counterparties_in"),
        F.sum(F.when(is_out & F.col("is_self_transfer"), 1).otherwise(0)).alias("n_self_transfers"),
        F.countDistinct("currency").alias("n_currencies"),
        F.min("ts").alias("first_ts"),
        F.max("ts").alias("last_ts"),
        *[F.sum(F.when(F.col("payment_format") == f, 1).otherwise(0)).alias(_fmt_col(f)) for f in PAYMENT_FORMATS],
    ]
    return edges.groupBy("variant", "account_id").agg(*aggs)


def entity_summary(summary: DataFrame, accounts: DataFrame) -> DataFrame:
    """Per owner (entity): its accounts, banks, countries and activity. These rows become Supabase customers."""
    acc = accounts.select("variant", "account_id", "entity_id", "entity_name", "entity_type", "bank_id", "bank_country")
    j = acc.join(summary, ["variant", "account_id"], "left")
    return j.groupBy("variant", "entity_id", "entity_name", "entity_type").agg(
        F.count("account_id").alias("n_accounts"),
        F.sum(F.when(F.col("n_out").isNotNull() | F.col("n_in").isNotNull(), 1).otherwise(0)).alias("n_active_accounts"),
        F.countDistinct("bank_id").alias("n_banks"),
        F.array_sort(F.collect_set("bank_country")).alias("bank_countries"),
        F.coalesce(F.sum("n_out"), F.lit(0)).alias("n_out"),
        F.coalesce(F.sum("n_in"), F.lit(0)).alias("n_in"),
        F.sum("usd_out").cast(USD).alias("usd_out"),
        F.sum("usd_in").cast(USD).alias("usd_in"),
        F.min("first_ts").alias("first_ts"),
        F.max("last_ts").alias("last_ts"),
    )
