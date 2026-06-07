#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./testing/smoke_api.sh
#   API_BASE_URL=http://127.0.0.1:8000 ./testing/smoke_api.sh

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"

echo "[smoke] health"
curl -fsS "${API_BASE_URL}/health" > /tmp/winky_health.json
cat /tmp/winky_health.json
echo

echo "[smoke] upsert user"
curl -fsS -X POST "${API_BASE_URL}/api/users/upsert" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"smoke-user-1","email":"smoke@example.com","name":"Smoke Test"}' \
  > /tmp/winky_user_upsert.json
cat /tmp/winky_user_upsert.json
echo

echo "[smoke] get user"
curl -fsS "${API_BASE_URL}/api/users/smoke-user-1" > /tmp/winky_user_get.json
cat /tmp/winky_user_get.json
echo

echo "[smoke] done"
