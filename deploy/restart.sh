#!/usr/bin/env bash
# restart.sh — Restart PostgreSQL then Winky Travel FastDB API.

set -euo pipefail

POSTGRES_PORT=5432
API_PORT=8000
SERVICE_NAME="winky-travel-fastdb"

log() { echo "[restart] $*"; }
die() { echo "[restart] ERROR: $*" >&2; exit 1; }

log "Restarting postgresql ..."
systemctl restart postgresql

log "Waiting for PostgreSQL on port ${POSTGRES_PORT} ..."
for i in $(seq 1 20); do
  pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT}" > /dev/null 2>&1 && break
  sleep 2
  if [[ "$i" -eq 20 ]]; then
    die "PostgreSQL did not come up after restart."
  fi
done

log "Restarting ${SERVICE_NAME} ..."
systemctl restart "${SERVICE_NAME}"

log "Waiting for API on port ${API_PORT} ..."
for i in $(seq 1 20); do
  curl -sf "http://127.0.0.1:${API_PORT}/health" > /dev/null 2>&1 && break
  sleep 2
  if [[ "$i" -eq 20 ]]; then
    die "${SERVICE_NAME} did not come up after restart."
  fi
done

log "All services restarted successfully."
