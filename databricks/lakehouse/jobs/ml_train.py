"""Databricks job task: ML train. All logic lives in trustnova_ml.jobs (tested on a laptop)."""

import sys

from trustnova_ml.jobs import train_main

code = train_main(sys.argv[1:])
if code:  # a clean sys.exit(0) is reported as a failure by Databricks, so only exit on a real error
    sys.exit(code)
