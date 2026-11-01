"""One local Spark session for the lakehouse tests. Tests that use it skip when pyspark or Java is missing."""

import glob
import os
import shutil
import sys

import pytest


def _find_java_home() -> str | None:
    if os.environ.get("JAVA_HOME"):
        return os.environ["JAVA_HOME"]
    java = shutil.which("java")
    if java:
        return os.path.dirname(os.path.dirname(os.path.realpath(java)))
    # Windows: a JDK installed in this shell's lifetime is not on PATH until the shell restarts
    found = sorted(glob.glob(r"C:\Program Files\Microsoft\jdk-17*")) + sorted(glob.glob(r"C:\Program Files\Eclipse Adoptium\jdk-17*"))
    return found[-1] if found else None


@pytest.fixture(scope="session")
def spark():
    pytest.importorskip("pyspark")
    java_home = _find_java_home()
    if not java_home:
        pytest.skip("Java 17 is not installed; the Spark transform tests need it")
    os.environ["JAVA_HOME"] = java_home
    # Spark starts its Python workers with whatever `python` is first on PATH unless told otherwise; a different
    # interpreter version crashes the worker.
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    from pyspark.sql import SparkSession

    s = (SparkSession.builder.master("local[2]").appName("trustnova-lake-tests")
         .config("spark.ui.enabled", "false")
         .config("spark.sql.shuffle.partitions", "2")
         .config("spark.default.parallelism", "1")  # the sample is tiny; fewer tasks = fewer slow Python-worker starts
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.sql.ansi.enabled", "true")  # as on Databricks serverless
         .getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


@pytest.fixture(scope="session")
def built(spark):
    """The sample bank's Bronze -> Gold chain, built once. Caching is for test speed only (the jobs never cache,
    because Databricks serverless does not allow it)."""
    import sample_data

    return {name: df.cache() for name, df in sample_data.build(spark).items()}
