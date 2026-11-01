"""Databricks job task: lakehouse gold. All logic lives in trustnova_lake.jobs (tested on a laptop)."""

import sys

from trustnova_lake.jobs import gold_main

code = gold_main(sys.argv[1:])
if code:  # a clean sys.exit(0) is reported as a failure by Databricks, so only exit on a real error
    sys.exit(code)
