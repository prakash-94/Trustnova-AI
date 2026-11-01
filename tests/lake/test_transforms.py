"""The Spark transforms on a tiny bank in the real IBM formats (see sample_data.py)."""

from decimal import Decimal

import pytest

pytest.importorskip("pyspark")

import sample_data as sd
from pyspark.sql import functions as F

from trustnova_lake import ibm
from trustnova_lake import transforms as tf


def rows(df, *cols, order=None):
    return [tuple(r) for r in df.select(*cols).orderBy(*(order or cols)).collect()]


def test_variant_comes_from_the_file_name(spark):
    df = spark.createDataFrame([("HI-Large_Trans.part-002.csv",), ("LI-Small_Trans.csv",), ("other.csv",)], ["f"])
    assert [r[0] for r in df.select(tf.variant_from_file(F.col("f"))).collect()] == ["HIL", "LIS", None]


def test_spark_and_python_identifier_rules_agree(spark):
    banks = ["010", "03208", "0", "000", "021174", "10"]
    got = [r[0] for r in spark.createDataFrame([(b,) for b in banks], ["b"]).select(tf._bank(F.col("b"))).collect()]
    assert got == [ibm.normalize_bank_id(b) for b in banks]
    accounts = tf.typed_accounts(sd.raw_accounts(spark)).collect()
    for r in accounts:
        assert r.entity_type == ibm.entity_type(r.entity_name)
        assert r.bank_country == ibm.bank_country(r.bank_name)


def test_transactions_are_typed_and_namespaced(built):
    first = built["typed"].where((F.col("variant") == "HIS") & (F.col("payment_format") == "Reinvestment")).first()
    assert first.from_account == "HIS:10:8000AAA01" and first.is_self_transfer
    assert str(first.ts) == "2022-09-01 00:20:00"
    btc = built["typed"].where(F.col("paid_currency") == "Bitcoin").first()
    assert btc.amount_paid == Decimal("0.010000")
    assert built["typed"].where(F.col("ts").isNull() | F.col("amount_paid").isNull()).count() == 0
    # the same raw account in another simulation is a different account
    lis = built["typed"].where(F.col("variant") == "LIS").first()
    assert lis.from_account == "LIS:10:8000AAA01"


def test_bad_values_become_nulls_instead_of_failing(spark):
    bad = sd.raw_transactions(spark).limit(1).withColumn("amount_paid", F.lit("12,5")).withColumn("timestamp", F.lit("01/09/2022"))
    r = tf.typed_transactions(bad).first()
    assert r.amount_paid is None and r.ts is None


def test_every_transaction_gets_a_unique_repeatable_id(built, spark):
    ids = built["tx"].select("txn_id")
    assert ids.count() == len(sd.HIS_TRANSACTIONS) + len(sd.LIS_TRANSACTIONS) == ids.distinct().count()
    dups = [r.txn_id for r in built["tx"].where(F.col("payment_format") == "Cash").where(F.col("variant") == "HIS").collect()]
    assert len(dups) == 2 and {d.rsplit("-", 1)[1] for d in dups} == {"1", "2"}
    again = sd.build(spark)["tx"].select("txn_id")
    assert sorted(r[0] for r in ids.collect()) == sorted(r[0] for r in again.collect())


def test_the_label_never_reaches_silver_or_gold(built):
    for name in ("tx", "edges", "summary", "entities"):
        assert "is_laundering" not in built[name].columns, name
    assert built["labels"].columns == ["txn_id", "variant", "is_laundering"]
    assert built["labels"].where(F.col("is_laundering") == 1).count() == 4


def test_fx_rates_come_from_the_data(built):
    fx = {(r.variant, r.currency): r for r in built["fx"].collect()}
    euro, chf, btc = fx[("HIS", "Euro")], fx[("HIS", "Swiss Franc")], fx[("HIS", "Bitcoin")]
    assert euro.method == "direct" and euro.usd_rate == pytest.approx(1.17) and euro.samples == 25
    assert chf.method == "inverse" and chf.usd_rate == pytest.approx(1 / 0.9)  # only 3 direct samples
    assert btc.method == "inverse" and btc.usd_rate == pytest.approx(40000)
    assert fx[("HIS", "US Dollar")].usd_rate == 1.0 and fx[("LIS", "US Dollar")].method == "identity"


def test_amounts_are_converted_to_usd(built):
    tx = built["tx"]
    euro = tx.where((F.col("paid_currency") == "Euro") & (F.col("received_currency") == "Euro")).first()
    assert euro.amount_paid_usd == Decimal("11.70")
    btc = tx.where(F.col("paid_currency") == "Bitcoin").first()
    assert btc.amount_paid_usd == Decimal("400.00")
    assert tx.where(F.col("amount_paid_usd").isNull() | F.col("amount_received_usd").isNull()).count() == 0


def test_accounts_keep_their_owner_and_country(built):
    acc = {r.account_id: r for r in built["accounts"].collect()}
    assert acc["HIS:10:8000AAA01"].entity_id == acc["HIS:10:8000AAA05"].entity_id == "HIS:800E00001"
    assert acc["HIS:12:8000AAA01"].entity_id == "HIS:800E00005"  # same number, different bank, different owner
    assert acc["HIS:10:8000AAA01"].bank_country == "Germany"
    assert acc["HIS:1:8000AAA03"].bank_country is None and acc["HIS:1:8000AAA03"].entity_type == "Individual"


def test_pattern_lines_match_exactly_one_transaction(built):
    m = rows(built["pattern_matches"], "variant", "attempt_id", "attempt_line", "matches")
    assert m == [("HIS", "HIS-P00001", "1", 1), ("HIS", "HIS-P00001", "2", 1), ("LIS", "LIS-P00001", "1", 1)]
    p = built["patterns"].collect()
    assert {r.pattern_type for r in p} == {"FAN-OUT", "CYCLE"} and len(p) == 3
    labelled = {r.txn_id for r in built["labels"].where(F.col("is_laundering") == 1).collect()}
    assert {r.txn_id for r in p} <= labelled  # one LIS laundering transaction is outside any pattern ("other")


def test_an_unknown_pattern_line_is_reported_as_unmatched(spark, built):
    fake = sd.T_LAUNDER_1[:5] + ("99.99",) + sd.T_LAUNDER_1[6:]
    text = f"BEGIN LAUNDERING ATTEMPT - STACK: x\n{','.join(fake)}\nEND LAUNDERING ATTEMPT - STACK\n"
    from trustnova_lake.jobs import PATTERN_SCHEMA

    pats = tf.typed_transactions(spark.createDataFrame(ibm.pattern_rows("HIS", text), PATTERN_SCHEMA))
    assert tf.match_patterns(pats, built["tx"]).first().matches == 0


def test_every_transaction_becomes_two_edges(built):
    edges = built["edges"]
    assert edges.count() == 2 * built["tx"].count()
    t = built["tx"].where(F.col("paid_currency") == "Euro").where(F.col("received_currency") == "US Dollar").first()
    sides = {r.direction: r for r in edges.where(F.col("txn_id") == t.txn_id).collect()}
    assert sides["out"].account_id == t.from_account and sides["out"].counterparty_id == t.to_account
    assert sides["in"].account_id == t.to_account and sides["in"].currency == "US Dollar"
    assert sides["out"].amount_usd == Decimal("117.00") == sides["in"].amount_usd


def test_account_and_entity_summaries(built):
    s = {r.account_id: r for r in built["summary"].collect()}
    a2 = s["HIS:3208:8000AAA02"]
    assert (a2.n_out, a2.n_in, a2.counterparties_out, a2.usd_out) == (2, 0, 2, Decimal("1258.50"))
    self_acct = s["HIS:10:8000AAA01"]
    assert self_acct.n_self_transfers == 1 and self_acct.counterparties_out == 0  # the self-transfer is not a counterparty
    e = {r.entity_id: r for r in built["entities"].collect()}
    corp = e["HIS:800E00001"]
    assert corp.n_accounts == 2 and corp.entity_type == "Corporation" and corp.bank_countries == ["Germany"]
    assert e["HIS:800E00004"].bank_countries == []
