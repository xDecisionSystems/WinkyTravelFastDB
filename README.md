# Winky Travel FastDB

FastAPI + PostgreSQL backend for Winky Travel.

## What this service does

- Persists app users in PostgreSQL.
- Includes PostgreSQL domain tables aligned to WinkyTravelDev entities (`trips`, `activities`, `travels`, `hotels`, `transits`, `schedule_items`).
- Includes trip sharing schema with per-user permissions (`owner`, `view`, `add`, `delete`, `edit`).
- Proxies Google Places autocomplete/details requests so API keys remain server-side.
- Logs per-user Google Places usage events for tracking and analytics.
- Applies rate limiting on all endpoints (per second, per hour, per day) by client IP and user ID.
- Supports deployment to a Debian-based Proxmox LXC.

Schema reference: see `SCHEMA.md`.

## Quick start (local)

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy env file:
   ```bash
   cp .env.dev .env
   ```
4. Run API:
   ```bash
   uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
   ```
5. Health check:
   ```bash
   curl http://127.0.0.1:8000/health
   ```

## Abuse protection configuration

Configured via environment variables:

- `RATE_LIMIT_PER_SECOND` (default `5`)
- `RATE_LIMIT_PER_HOUR` (default `1000`)
- `RATE_LIMIT_PER_DAY` (default `10000`)
- `RATE_LIMIT_RETENTION_HOURS` (default `48`)

Rate-limit events are stored in PostgreSQL `rate_limit_events` and include allowed and blocked attempts.

## Core routes

- `GET /health`
- `GET /llms.txt` (`GET /llm.txt` alias)
- `POST /api/users/upsert`
- `GET /api/users/{user_id}`
- `POST /api/places/autocomplete`
- `POST /api/places/details`
- `GET /api/dev/logs?path=<relative-log-path>&lines=200` (dev-only, master key required)
- `POST /api/dev/admin/delete-all-records?confirm=DELETE_ALL_RECORDS` (dev-only, destructive)

## Dev log endpoint (for coding-agent testing)

`GET /api/dev/logs` lets your coding agent read log files from a configured dev log directory.

Security controls:

- Enabled only when `ENVIRONMENT` is `development` or `dev`.
- Requires header `X-Master-API-Key: <DEV_MASTER_API_KEY>`.
- Restricts file access to paths under `DEV_LOG_ROOT_DIR`.
- Caps output using `DEV_LOG_MAX_BYTES` and `DEV_LOG_MAX_LINES`.

Example:

```bash
curl -sS "http://127.0.0.1:8000/api/dev/logs?path=syslog&lines=120" \
  -H "X-Master-API-Key: change-this-dev-master-key"
```

## Dev admin endpoint: delete all records

`POST /api/dev/admin/delete-all-records` deletes all rows from core PostgreSQL tables.

Safety controls:

- Enabled only when `ENVIRONMENT` is `development` or `dev`.
- Requires header `X-Master-API-Key: <DEV_MASTER_API_KEY>`.
- Requires query param `confirm=DELETE_ALL_RECORDS`.
- Subject to rate limiting.

Example:

```bash
curl -sS -X POST \
  "http://127.0.0.1:8000/api/dev/admin/delete-all-records?confirm=DELETE_ALL_RECORDS" \
  -H "X-Master-API-Key: change-this-dev-master-key"
```

## Recommended next fixes

1. Add real authentication/authorization and stop trusting client-supplied `user_id` directly.
2. Replace wildcard CORS with an explicit origin allowlist for your frontend domains.
3. Trust proxy headers safely (`X-Forwarded-For`) only from known reverse proxies so IP rate limiting is accurate in production.
4. Harden Places upstream failure handling by catching timeouts/network errors and non-JSON error bodies, then returning stable `502/504` responses.
5. Add automated tests for rate limiting and abuse logging paths (allow, block, and boundary behavior across second/hour/day windows).

## Deployment scripts

- `deploy/proxmox_deploy.sh`
- `deploy/update.sh`
- `deploy/restart.sh`
