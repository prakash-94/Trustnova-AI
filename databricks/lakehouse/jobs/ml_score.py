"""Databricks job task: ML score. All logic lives in trustnova_ml.jobs (tested on a laptop)."""

import sys

from trustnova_ml.jobs import score_main

code = score_main(sys.argv[1:])
if code:  # a clean sys.exit(0) is reported as a failure by Databricks, so only exit on a real error
    sys.exit(code)
