# Winky Travel FastDB

FastAPI + PostgreSQL backend for Winky Travel.

## What this service does

- Authenticates users via Google Sign-In and issues backend session JWTs (see "Authentication").
- Persists app users in PostgreSQL, keyed on their verified Google identity.
- Provides full CRUD REST endpoints for WinkyTravelDev domain entities: `trips`, `activities`, `travels`, `hotels`, `transits`, `schedule_items`, plus trip sharing and per-user settings (`custom_activity_types`, `activity_icon_overrides`). Every entity route requires a valid session JWT and is scoped to the authenticated user.
- Includes trip sharing with per-user permissions (`owner`, `view`, `add`, `delete`, `edit`).
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

## Authentication

All trip-planning domain routes require a session token issued by this service. There is no
anonymous access — clients must sign in before calling any `/api/trips`, `/api/activities`,
`/api/settings/*`, etc. endpoint.

Flow:

1. The frontend obtains a Google ID token via Google Sign-In and posts it to
   `POST /api/auth/google` (`{ "id_token": "<google-id-token>" }`). The backend verifies the
   token's signature and audience against `GOOGLE_CLIENT_ID`, creates or looks up the user by
   their Google `sub`, and returns `{ "token": "<jwt>", "user": { ... } }`.
2. The frontend sends that JWT on every subsequent request as `Authorization: Bearer <jwt>`.
3. `GET /api/auth/me` returns the authenticated user's record — useful for restoring a session
   after a page reload.

Configured via environment variables:

- `GOOGLE_CLIENT_ID` (required) — OAuth client ID; the backend rejects ID tokens issued for any
  other audience.
- `JWT_SECRET_KEY` (required) — symmetric (HS256) signing secret for backend-issued session JWTs.
  Use a long random value and keep it secret.
- `JWT_EXPIRY_HOURS` (default `168`) — session token lifetime.
- `CORS_ALLOWED_ORIGINS` (default `http://localhost:5173,http://127.0.0.1:5173`) — comma-separated
  list of allowed frontend origins.

### Dev-only login (test/CI accounts)

`POST /api/auth/dev-login` issues a session JWT in the same shape as the Google flow, without
requiring a Google account. It is intended only for automated testing and local development.

- Disabled by default; only reachable (returns `404` otherwise) when `DEV_LOGIN_ENABLED=true`.
- Requires `{ "master_key": "<DEV_LOGIN_MASTER_KEY>", "email": "...", "name": "..." }` in the
  request body — `email`/`name` are optional and default to a fixed dev account identity.
- **Must remain disabled in production.** Set `DEV_LOGIN_ENABLED=false` (the default) and leave
  `DEV_LOGIN_MASTER_KEY` unset/empty for any production or shared deployment.

Configured via environment variables:

- `DEV_LOGIN_ENABLED` (default `false`)
- `DEV_LOGIN_MASTER_KEY` (default empty — the endpoint always rejects requests when empty, even
  if `DEV_LOGIN_ENABLED=true`)

## Abuse protection configuration

Configured via environment variables:

- `RATE_LIMIT_PER_SECOND` (default `5`)
- `RATE_LIMIT_PER_HOUR` (default `1000`)
- `RATE_LIMIT_PER_DAY` (default `10000`)
- `RATE_LIMIT_RETENTION_HOURS` (default `48`)

Rate-limit events are stored in PostgreSQL `rate_limit_events` and include allowed and blocked attempts.

## Database configuration

Configured via environment variables:

- `DB_HOST` (required)
- `DB_PORT` (default `5432`)
- `DB_NAME` (required)
- `DB_USER` (required)
- `DB_PASSWORD` (optional but recommended)
- `DB_SSLMODE` (default `disable`)

Legacy `DATABASE_URL` is still accepted for backward compatibility.

## Core routes

- `GET /health`
- `GET /llms.txt` (`GET /llm.txt` alias)
- `POST /api/auth/google` (sign in with a Google ID token, returns `{ token, user }`)
- `POST /api/auth/dev-login` (dev-only test-account login, returns `{ token, user }`)
- `GET /api/auth/me` (current authenticated user; requires `Authorization: Bearer <jwt>`)
- `POST /api/places/autocomplete`
- `POST /api/places/details`
- `GET /api/dev/logs?path=<relative-log-path>&lines=200` (dev-only, master key required)
- `POST /api/dev/admin/delete-all-records?confirm=DELETE_ALL_RECORDS` (dev-only, destructive)

### Trip-planning domain CRUD

Each resource follows the same REST shape: `POST` (create), `GET` (list, scoped to the
authenticated user and optionally filtered by `trip_id`), `GET /{id}` (read one),
`PATCH /{id}` (partial update), `DELETE /{id}` (delete). Every route requires
`Authorization: Bearer <jwt>`; the user identity comes from the verified token, never from the
request body or query string, and `GET/PATCH/DELETE /{id}` return `404` for records owned by a
different user (so existence isn't leaked). All are rate limited like other endpoints.

- `/api/trips` and `/api/trips/{trip_id}/shares` (trip sharing sub-resource)
- `/api/activities`
- `/api/travels`
- `/api/hotels`
- `/api/transits`
- `/api/schedule-items` (list requires `trip_id`, optional `day_date` filter)
- `/api/settings/custom-activity-types`
- `/api/settings/icon-overrides` (`PUT` to upsert, `GET`/`DELETE` keyed by the authenticated user + `activity_type_id`)

See `ARCHITECTURE.md` for the full endpoint map and request/response contracts.

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

1. Trust proxy headers safely (`X-Forwarded-For`) only from known reverse proxies so IP rate limiting is accurate in production.
2. Harden Places upstream failure handling by catching timeouts/network errors and non-JSON error bodies, then returning stable `502/504` responses.
3. Add automated tests for rate limiting, abuse logging, and the new auth paths (Google login, dev login gating, JWT expiry/invalidation, ownership checks on protected routes).
4. Implement trip-share-aware authorization on trip/entity routes (currently only direct ownership is checked; shared collaborators cannot yet view/edit shared trips through the API).

## Deployment scripts

- `deploy/proxmox_deploy.sh`
- `deploy/update.sh`
- `deploy/restart.sh`
