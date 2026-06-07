#!/usr/bin/env bash
# restart.sh — Restart MongoDB then Winky Travel FastDB API.

set -euo pipefail

MONGO_PORT=27017
API_PORT=8000
SERVICE_NAME="winky-travel-fastdb"

log() { echo "[restart] $*"; }
die() { echo "[restart] ERROR: $*" >&2; exit 1; }

log "Restarting mongod ..."
systemctl restart mongod

log "Waiting for MongoDB on port ${MONGO_PORT} ..."
for i in $(seq 1 20); do
  mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1 && break
  sleep 2
  if [[ "$i" -eq 20 ]]; then
    die "MongoDB did not come up after restart."
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
