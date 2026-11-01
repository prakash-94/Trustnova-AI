"""Databricks job task: lakehouse silver. All logic lives in trustnova_lake.jobs (tested on a laptop)."""

import sys

from trustnova_lake.jobs import silver_main

code = silver_main(sys.argv[1:])
if code:  # a clean sys.exit(0) is reported as a failure by Databricks, so only exit on a real error
    sys.exit(code)
