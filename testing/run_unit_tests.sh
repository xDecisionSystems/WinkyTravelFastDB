#!/usr/bin/env bash
set -euo pipefail

# Defaults for required runtime settings during test import.
export MONGO_URI="${MONGO_URI:-mongodb://127.0.0.1:27017}"
export MONGO_DB="${MONGO_DB:-winky_travel_test}"

python3 -m unittest discover -s testing -p "test_*.py" -v
