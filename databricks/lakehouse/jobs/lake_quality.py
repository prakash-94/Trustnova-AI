"""Databricks job task: lakehouse quality. All logic lives in trustnova_lake.jobs (tested on a laptop)."""

import sys

from trustnova_lake.jobs import quality_main

code = quality_main(sys.argv[1:])
if code:  # a clean sys.exit(0) is reported as a failure by Databricks, so only exit on a real error
    sys.exit(code)
