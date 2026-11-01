"""TrustNova AML detection: trained models decide what is suspicious (GenAI never does).

    features  point-in-time transaction features from the lakehouse (Spark)
    baseline  the rule-only detector every model must beat (Spark)
    metrics   precision/recall metrics from binned score counts, so they scale to 430M rows (plain Python)
    train     LightGBM M1 (transaction risk) and M3 (pattern type), calibration and the promotion gate
    jobs      Databricks job entry points: features, train, score
"""
