#!/usr/bin/env bash
# Daily refresh: re-download sources, rebuild every table, run the tests.
# Exits non-zero (and changes nothing worth publishing) if anything fails.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
python3 normalize.py build --refresh
python3 -m pytest -q
git status --short data/processed
