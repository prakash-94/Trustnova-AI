"""TrustNova lakehouse: the IBM AML dataset as one combined bank (Bronze -> Silver -> Gold) on Databricks.

    ibm         file names, identifier rules and the patterns-file parser (plain Python)
    transforms  the Spark transforms, DataFrame in -> DataFrame out
    quality     the checks that must pass before a load counts
    jobs        the Databricks job entry points (I/O against Unity Catalog tables)
"""
