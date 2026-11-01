"""Databricks job task: lakehouse bronze. All logic lives in trustnova_lake.jobs (tested on a laptop)."""

import sys

from trustnova_lake.jobs import bronze_main

code = bronze_main(sys.argv[1:])
if code:  # a clean sys.exit(0) is reported as a failure by Databricks, so only exit on a real error
    sys.exit(code)
