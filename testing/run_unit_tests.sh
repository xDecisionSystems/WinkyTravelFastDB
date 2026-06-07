#!/usr/bin/env bash
set -euo pipefail

# Defaults for required runtime settings during test import.
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-winky_travel_test}"
export DB_USER="${DB_USER:-winky}"
export DB_PASSWORD="${DB_PASSWORD:-test}"
export DB_SSLMODE="${DB_SSLMODE:-disable}"

python3 -m unittest discover -s testing -p "test_*.py" -v
