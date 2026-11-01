"""The rule-only detector every model must beat: AML Copilot's rule ideas, written on the same point-in-time features.

score = number of rules hit (0-4):
    structuring  the sender made 3+ transfers in the $7k-$10k band over the previous 28 days, counting this one
    fan-out      the sender paid 5+ distinct counterparties over the previous day, plus this payment and earlier today
    fan-in       the receiver was paid by 5+ distinct counterparties over the previous day, plus earlier today
    cycle        the receiver sent money to the sender within the last 7 days (money coming back)
"""

from pyspark.sql import Column
from pyspark.sql import functions as F

RULES = ("structuring", "fan_out", "fan_in", "cycle")


def rule_hits() -> dict[str, Column]:
    """Column expressions over the feature table (see trustnova_ml.features)."""
    return {
        "structuring": (F.col("s_p28_band_out") + F.col("in_band")) >= 3,
        "fan_out": (F.col("s_p1_cp_out") + F.col("s_d0_n_out") + 1) >= 5,
        "fan_in": (F.col("r_p1_cp_in") + F.col("r_d0_n_in") + 1) >= 5,
        "cycle": F.col("reverse_n_7d") > 0,
    }


def rule_score() -> Column:
    hits = rule_hits()
    return sum((F.when(hits[r], 1).otherwise(0) for r in RULES), F.lit(0)).cast("double")
