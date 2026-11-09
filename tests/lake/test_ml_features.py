"""Point-in-time features on the sample bank: a transaction sees only activity strictly before its own minute."""

import pytest

pytest.importorskip("pyspark")

import sample_data as sd
from pyspark.sql import functions as F

from trustnova_ml.baseline import RULES, rule_hits, rule_score
from trustnova_ml.features import BANNED, ENTITY_TYPES, FEATURES, assign_split, transaction_features


@pytest.fixture(scope="module")
def feats(built):
    return assign_split(transaction_features(built["tx"], built["edges"], built["accounts"])).cache()


def row_for(feats, built, raw, variant="HIS", nth=0):
    """The feature row of the sample transaction `raw` (a tuple from sample_data)."""
    ts = raw[0].replace("/", "-") + ":00"
    tx = (built["tx"].where((F.col("variant") == variant) & (F.col("ts") == F.lit(ts).cast("timestamp_ntz"))
                            & (F.col("payment_format") == raw[9]) & (F.col("amount_paid") == F.lit(raw[7]).cast("decimal(22,6)")))
          .orderBy("txn_id").collect()[nth])
    return feats.where(F.col("txn_id") == tx.txn_id).first()


def test_one_row_per_transaction_and_every_feature_present(feats, built):
    assert feats.count() == built["tx"].count()
    assert set(FEATURES) <= set(feats.columns)
    assert not set(BANNED) & set(FEATURES)
    assert "is_laundering" not in feats.columns and "label" not in feats.columns
    nulls = feats.select(*[F.sum(F.col(c).isNull().cast("int")).alias(c) for c in FEATURES]).first().asDict()
    assert {k: v for k, v in nulls.items() if v} == {}


def test_same_day_history_stops_before_the_transaction(feats, built):
    first = row_for(feats, built, sd.T_LAUNDER_1)
    second = row_for(feats, built, sd.T_LAUNDER_2)
    assert (first.s_d0_n_out, first.s_d0_usd_out) == (0.0, 0.0)
    assert (second.s_d0_n_out, second.s_d0_usd_out) == (1.0, 58.5)  # sees the 00:21 payment, not itself


def test_earlier_day_windows(feats, built):
    r = row_for(feats, built, sd.T_EURO_LOCAL)  # sender 8000AAA05 on 4 Sep
    assert r.s_p1_n_out == 28.0  # 25 Euro + 3 Swiss Franc payments on 3 Sep
    assert r.s_p1_n_in == 25.0   # 25 USD->CHF payments it received on 3 Sep
    assert r.s_p1_cp_out == 1.0  # all to the same counterparty
    assert r.s_p7_n_in == 27.0   # plus the duplicated pair it received on 2 Sep
    assert r.s_account_age_days == 2.0  # first seen on 2 Sep


def test_first_time_pairs_and_amount_flags(feats, built):
    dup = sorted(row_for(feats, built, sd.T_DUP, nth=i).first_time_pair for i in (0, 1))
    assert dup == [0.0, 1.0]
    big = row_for(feats, built, sd.L_LAUNDER, variant="LIS")
    assert big.in_band == 1.0 and big.round_amount == 1.0 and big.first_time_pair == 1.0


def test_money_coming_back_is_seen_only_after_it_happened(feats, built):
    out = row_for(feats, built, sd.L_LAUNDER, variant="LIS")
    back = row_for(feats, built, sd.L_LAUNDER_OTHER, variant="LIS")
    assert out.reverse_n_7d == 0.0
    assert (back.reverse_n_7d, back.reverse_usd_7d) == (1.0, 9500.0)


def test_three_step_cycles_need_both_earlier_steps(feats, built):
    closing = row_for(feats, built, sd.L_CLOSE, variant="LIS")
    assert closing.closes_3cycle_7d == 1.0          # B->C 08:30 and C->A 08:45 happened before A->B at 10:00
    assert row_for(feats, built, sd.L_LAUNDER, variant="LIS").closes_3cycle_7d == 0.0  # 08:00 is before the loop
    assert row_for(feats, built, sd.L_B_TO_C, variant="LIS").closes_3cycle_7d == 0.0


def test_pass_through_features(feats, built):
    c = row_for(feats, built, sd.L_C_TO_A, variant="LIS")  # C received 300 at 08:30 and pays 290 at 08:45
    assert c.s_minutes_since_in == 15.0
    assert c.s_vs_inflow_24h == pytest.approx(290 / 301)
    a = row_for(feats, built, sd.L_CLOSE, variant="LIS")   # A last received at 09:00 (40 from B), 290 at 08:45
    assert a.s_minutes_since_in == 60.0
    assert a.s_vs_inflow_24h == pytest.approx(250 / 331)
    first = row_for(feats, built, sd.T_LAUNDER_1)         # the sender never received anything
    assert first.s_minutes_since_in == -1.0


def test_unusual_for_this_account_features(feats, built):
    r = row_for(feats, built, sd.T_EURO_LOCAL)  # 8000AAA05 normally pays ~116 USD; this payment is 11.70 USD
    assert r.s_amount_z_28d == -50.0            # far below its own normal (clipped)
    assert r.s_burst_vs_28d == pytest.approx(0.5)  # first payment today against 28 in the last 28 days
    assert r.s_new_cp_share_7d == pytest.approx(1 / 28)
    assert r.s_format_first == 1.0              # its first cheque
    wire = [row_for(feats, built, sd.EURO_TO_USD[i]).s_format_first for i in (0, 1)]
    assert wire == [1.0, 0.0]


def test_ach_flow_features(feats, built):
    c = row_for(feats, built, sd.L_C_TO_A, variant="LIS")  # C got its first ACH from B at 08:30, then pays A by ACH
    assert c.s_d0_ach_new_in == 1.0
    a = row_for(feats, built, sd.L_CLOSE, variant="LIS")   # A got new ACH from C at 08:45 (the 09:00 cash doesn't count)
    assert a.s_d0_ach_new_in == 1.0
    assert row_for(feats, built, sd.L_LAUNDER, variant="LIS").s_d0_ach_new_in == 0.0  # 08:00: nothing yet
    btc = row_for(feats, built, sd.T_BITCOIN)  # 8000AAA03 bought Bitcoin by ACH 22 times on 3 Sep, all self-transfers
    assert (btc.s_p1_ach_out, btc.s_p1_ach_in) == (22.0, 22.0)
    assert (btc.s_p1_ach_new_out, btc.s_p1_ach_new_in) == (0.0, 0.0)  # a self-transfer has no counterparty


def test_owner_features(feats, built):
    r = row_for(feats, built, sd.T_EURO_LOCAL)  # 8000AAA05 (owner 800E00001: two accounts at one bank) -> 8000AAA04
    assert r.s_entity_type_code == float(ENTITY_TYPES.index("Corporation"))
    assert (r.s_owner_n_accounts, r.s_owner_n_banks) == (2.0, 1.0)
    assert r.r_entity_type_code == float(ENTITY_TYPES.index("Sole Proprietorship"))
    assert (r.r_owner_n_accounts, r.r_owner_n_banks) == (1.0, 1.0)


def test_temporal_split_per_simulation(feats):
    by = {(r.variant, r.split): r["count"] for r in feats.groupBy("variant", "split").count().collect()}
    assert by[("HIS", "train")] > by[("HIS", "valid")] > 0 and by[("HIS", "test")] > 0
    order = feats.groupBy("variant", "split").agg(F.min("sec").alias("lo"), F.max("sec").alias("hi")).collect()
    span = {(r.variant, r.split): (r.lo, r.hi) for r in order}
    assert span[("HIS", "train")][1] < span[("HIS", "valid")][0] <= span[("HIS", "valid")][1] < span[("HIS", "test")][0]


def test_rule_baseline_counts_rules(feats, built):
    scored = feats.withColumn("rule_score", rule_score())
    assert set(rule_hits()) == set(RULES)
    back = row_for(scored, built, sd.L_LAUNDER_OTHER, variant="LIS")
    assert back.rule_score >= 1.0  # the cycle rule fires
    assert scored.where(F.col("rule_score") > 4).count() == 0
