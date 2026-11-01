"""A tiny bank in the exact IBM AML file formats, covering what the real data showed: zero-padded bank ids, an account
number reused by another bank and by another simulation, an owner with two accounts, self-transfers, one exact
duplicate row, Euro converted directly to USD, Swiss Franc with too few direct samples (so the inverse rate wins),
Bitcoin only ever bought with USD, and pattern blocks in both simulations."""

from trustnova_lake import transforms as tf
from trustnova_lake.ibm import RAW_ACCOUNT_COLUMNS, RAW_TRANSACTION_COLUMNS, pattern_rows


def _t(ts, fb, fa, tb, ta, ar, rc, ap, pc, fmt, lab):
    return (ts, fb, fa, tb, ta, ar, rc, ap, pc, fmt, lab)


T_SELF = _t("2022/09/01 00:20", "010", "8000AAA01", "010", "8000AAA01", "100.00", "US Dollar", "100.00", "US Dollar", "Reinvestment", "0")
T_LAUNDER_1 = _t("2022/09/01 00:21", "03208", "8000AAA02", "001", "8000AAA03", "58.50", "US Dollar", "58.50", "US Dollar", "ACH", "1")
T_LAUNDER_2 = _t("2022/09/01 01:00", "03208", "8000AAA02", "0220", "8000AAA04", "1200.00", "US Dollar", "1200.00", "US Dollar", "ACH", "1")
T_DUP = _t("2022/09/02 10:00", "012", "8000AAA01", "010", "8000AAA05", "5.00", "US Dollar", "5.00", "US Dollar", "Cash", "0")
T_EURO_LOCAL = _t("2022/09/04 09:00", "010", "8000AAA05", "0220", "8000AAA04", "10.00", "Euro", "10.00", "Euro", "Cheque", "0")
T_BITCOIN = _t("2022/09/04 10:00", "001", "8000AAA03", "001", "8000AAA03", "0.010000", "Bitcoin", "0.010000", "Bitcoin", "Bitcoin", "0")

EURO_TO_USD = [_t(f"2022/09/03 00:{i:02d}", "010", "8000AAA05", "0220", "8000AAA04", "117.00", "US Dollar", "100.00", "Euro", "Wire", "0")
               for i in range(25)]
CHF_TO_USD = [_t(f"2022/09/03 01:{i:02d}", "010", "8000AAA05", "0220", "8000AAA04", "120.00", "US Dollar", "100.00", "Swiss Franc", "Wire", "0")
              for i in range(3)]  # direct rate 1.2, but only 3 samples
USD_TO_CHF = [_t(f"2022/09/03 02:{i:02d}", "0220", "8000AAA04", "010", "8000AAA05", "90.00", "Swiss Franc", "100.00", "US Dollar", "Wire", "0")
              for i in range(25)]  # inverse rate 1/0.9
USD_TO_BTC = [_t(f"2022/09/03 03:{i:02d}", "001", "8000AAA03", "001", "8000AAA03", "0.025000", "Bitcoin", "1000.00", "US Dollar", "ACH", "0")
              for i in range(22)]  # Bitcoin at 40,000 USD

HIS_TRANSACTIONS = [T_SELF, T_LAUNDER_1, T_LAUNDER_2, T_DUP, T_DUP, T_EURO_LOCAL, T_BITCOIN,
                    *EURO_TO_USD, *CHF_TO_USD, *USD_TO_CHF, *USD_TO_BTC]

L_SELF = _t("2022/09/01 00:20", "010", "8000AAA01", "010", "8000AAA01", "100.00", "US Dollar", "100.00", "US Dollar", "Reinvestment", "0")
L_LAUNDER = _t("2022/09/05 08:00", "010", "8000AAA01", "03208", "8000AAA02", "9500.00", "US Dollar", "9500.00", "US Dollar", "Cash", "1")
L_LAUNDER_OTHER = _t("2022/09/05 09:00", "03208", "8000AAA02", "010", "8000AAA01", "40.00", "US Dollar", "40.00", "US Dollar", "Cash", "1")
LIS_TRANSACTIONS = [L_SELF, L_LAUNDER, L_LAUNDER_OTHER]

HIS_ACCOUNTS = [
    ("Germany Bank #1", "10", "8000AAA01", "800E00001", "Corporation #1"),
    ("Germany Bank #1", "10", "8000AAA05", "800E00001", "Corporation #1"),
    ("UK Bank #7", "3208", "8000AAA02", "800E00002", "Partnership #2"),
    ("Crytpo Bank #5", "1", "8000AAA03", "800E00003", "Individual #3"),
    ("National Bank of Harrisburg", "220", "8000AAA04", "800E00004", "Sole Proprietorship #4"),
    ("Spain Bank #9", "12", "8000AAA01", "800E00005", "Corporation #5"),
]
LIS_ACCOUNTS = [
    ("Germany Bank #1", "10", "8000AAA01", "800E00001", "Corporation #1"),
    ("UK Bank #7", "3208", "8000AAA02", "800E00002", "Partnership #2"),
]


def _line(t):
    return ",".join(t)


HIS_PATTERNS = (
    "BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out\n"
    f"{_line(T_LAUNDER_1)}\n{_line(T_LAUNDER_2)}\n"
    "END LAUNDERING ATTEMPT - FAN-OUT\n\n"
)
LIS_PATTERNS = (
    "BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 1 hops\n"
    f"{_line(L_LAUNDER)}\n"
    "END LAUNDERING ATTEMPT - CYCLE\n\n"
)


def raw_transactions(spark):
    rows = [(*r, "HIS") for r in HIS_TRANSACTIONS] + [(*r, "LIS") for r in LIS_TRANSACTIONS]
    return spark.createDataFrame(rows, [*RAW_TRANSACTION_COLUMNS, "variant"])


def raw_accounts(spark):
    rows = [(*r, "HIS") for r in HIS_ACCOUNTS] + [(*r, "LIS") for r in LIS_ACCOUNTS]
    return spark.createDataFrame(rows, [*RAW_ACCOUNT_COLUMNS, "variant"])


def raw_patterns(spark):
    from trustnova_lake.jobs import PATTERN_SCHEMA

    return spark.createDataFrame(pattern_rows("HIS", HIS_PATTERNS) + pattern_rows("LIS", LIS_PATTERNS), PATTERN_SCHEMA)


def build(spark) -> dict:
    """The whole Bronze -> Gold chain in memory, as the jobs run it (minus the table writes)."""
    raw = raw_transactions(spark)
    typed = tf.typed_transactions(raw)
    fx = tf.fx_rates(typed)
    with_usd = tf.with_usd(tf.with_txn_ids(typed), fx)
    tx, labels = tf.split_ground_truth(with_usd)
    accounts = tf.typed_accounts(raw_accounts(spark))
    matches = tf.match_patterns(tf.typed_transactions(raw_patterns(spark)), tx)
    edges = tf.account_txn_edges(tx)
    summary = tf.account_summary(edges)
    return {
        "raw": raw, "typed": typed, "fx": fx, "tx": tx, "labels": labels, "accounts": accounts,
        "pattern_matches": matches, "patterns": tf.restricted_patterns(matches), "edges": edges,
        "summary": summary, "entities": tf.entity_summary(summary, accounts),
    }
