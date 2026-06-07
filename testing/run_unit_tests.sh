#!/usr/bin/env bash
set -euo pipefail

# Defaults for required runtime settings during test import.
export DATABASE_URL="${DATABASE_URL:-postgresql://winky:test@127.0.0.1:5432/winky_travel_test}"

python3 -m unittest discover -s testing -p "test_*.py" -v
