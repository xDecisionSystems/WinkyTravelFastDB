# ARCHITECTURE.md

## 1. High-Level Design

Winky Travel FastDB is a single FastAPI service backed by PostgreSQL.

```text
Winky Web App -> FastAPI (this repo) -> PostgreSQL
                         |
                         +-> Google Places API (server-side proxy)
```

Client never receives or uses the Google Places API key directly.

## 2. Runtime Components

| Component | Technology | Port | Binding |
|----------|------------|------|---------|
| API | FastAPI + uvicorn | 8000 | 0.0.0.0 |
| Database | PostgreSQL | 5432 | localhost |
| HTTP client | httpx | n/a | outbound HTTPS |

## 3. Request Flow

### `POST /api/places/autocomplete`

1. Validate payload (`user_id`, `input`, optional session/language/region).
2. Call Google Places Autocomplete (New) with server key.
3. Store usage log (`usage_logs`) keyed by `user_id` and endpoint.
4. Return upstream JSON (or propagate upstream error status/body).

### `POST /api/places/details`

1. Validate payload (`user_id`, `place_id`, optional session/language).
2. Call Google Place Details endpoint with server key.
3. Store usage log for auditing and analytics.
4. Return upstream JSON (or upstream error).

### `POST /api/auth/google`

1. Validate payload (`id_token`).
2. Verify the Google ID token's signature and audience against `GOOGLE_CLIENT_ID`
   (`google.oauth2.id_token.verify_oauth2_token`); reject invalid/expired/wrong-audience
   tokens with `401`.
3. Derive a deterministic `user_id = "google:{sub}"` and upsert the user record by
   `google_sub`, refreshing `email`/`name` from the verified profile.
4. Issue an HS256 session JWT (`issue_session_jwt`, claims `sub`/`iat`/`exp`, expiry from
   `JWT_EXPIRY_HOURS`) and return `{ token, user }`.

### `POST /api/auth/dev-login`

1. Return `404` unless `DEV_LOGIN_ENABLED=true`.
2. Validate payload (`master_key`, optional `email`/`name`); compare `master_key`
   against `DEV_LOGIN_MASTER_KEY` with `hmac.compare_digest` (constant-time).
3. Derive a deterministic `user_id = "dev:" + sha256(email)[:32]` and upsert the user.
4. Issue and return a session JWT in the **same** `{ token, user }` shape as the Google
   flow — intended only for automated testing/local development; must stay disabled in
   production (`DEV_LOGIN_ENABLED=false`, `DEV_LOGIN_MASTER_KEY` unset).

### `GET /api/auth/me`

1. Resolve `user_id` via the `get_current_user_id` dependency (validates the bearer JWT).
2. Fetch and return the user record — used by the frontend to restore a session on reload.

### Session validation (`get_current_user_id` dependency)

Applied to every protected route (`/api/auth/me` and all trip-planning domain CRUD).
Reads `Authorization: Bearer <jwt>`, decodes/validates it via `decode_session_jwt`
(HS256, `JWT_SECRET_KEY`), and returns the embedded `user_id`. Raises `401` on a
missing, malformed, expired, or invalid-signature token. The resulting `user_id` is
the **only** source of identity for these routes — client-supplied `user_id`/
`owner_user_id` values in the request body or query string are never read or trusted.

## 4. Endpoint Map

| Method | Path | Purpose |
|-------|------|---------|
| GET | `/health` | Service health/status |
| GET | `/llms.txt` | LLM-facing project summary (`/llm.txt` alias) |
| GET | `/api/dev/logs` | Dev-only: read configured log files (requires `X-Master-API-Key`) |
| POST | `/api/dev/admin/delete-all-records` | Dev-only: delete all rows from core tables (requires `X-Master-API-Key`, destructive) |
| POST | `/api/auth/google` | Verify a Google ID token, upsert the user, issue a session JWT |
| POST | `/api/auth/dev-login` | Dev/test-only login (env-gated), issues a session JWT in the same shape as Google login |
| GET | `/api/auth/me` | Fetch the authenticated user's record from the bearer token |
| POST | `/api/places/autocomplete` | Google Places autocomplete proxy |
| POST | `/api/places/details` | Google place details proxy |
| POST | `/api/trips` | Create trip |
| GET | `/api/trips?owner_user_id=` | List trips for an owner |
| GET | `/api/trips/{trip_id}` | Fetch trip |
| PATCH | `/api/trips/{trip_id}` | Update trip fields |
| DELETE | `/api/trips/{trip_id}` | Delete trip (cascades to dependent rows) |
| POST | `/api/trips/{trip_id}/shares` | Create or replace a trip share (upsert by `shared_with_user_id`) |
| GET | `/api/trips/{trip_id}/shares` | List shares for a trip |
| PATCH | `/api/trips/{trip_id}/shares/{share_id}` | Update share permissions |
| DELETE | `/api/trips/{trip_id}/shares/{share_id}` | Remove a trip share |
| POST/GET/PATCH/DELETE | `/api/activities[/{activity_id}]` | Activity CRUD (`GET` list filters by `user_id`, optional `trip_id`) |
| POST/GET/PATCH/DELETE | `/api/travels[/{travel_id}]` | Travel segment CRUD |
| POST/GET/PATCH/DELETE | `/api/hotels[/{hotel_id}]` | Hotel stay CRUD |
| POST/GET/PATCH/DELETE | `/api/transits[/{transit_id}]` | Local transit CRUD |
| POST/GET/PATCH/DELETE | `/api/schedule-items[/{item_id}]` | Schedule item CRUD (`GET` list requires `trip_id`, optional `day_date`) |
| POST/GET/PATCH/DELETE | `/api/settings/custom-activity-types[/{type_id}]` | Custom activity type CRUD |
| PUT/GET/DELETE | `/api/settings/icon-overrides[/{activity_type_id}]` | Icon override upsert/list/delete (keyed by `user_id` + `activity_type_id`) |

### Trip-domain CRUD conventions

- Identity is derived **exclusively** from the validated session JWT via the
  `get_current_user_id` dependency — no route reads or trusts a client-supplied
  `user_id`/`owner_user_id` from the request body or query string. List endpoints no
  longer take an owning-identifier query parameter; activities/travels/hotels/transits
  still accept an optional `trip_id` filter, and schedule items still require `trip_id`
  (with optional `day_date`).
- `GET/PATCH/DELETE /{id}` routes return `404` (not `403`) when the record exists but
  is not owned by the authenticated user, to avoid leaking record existence.
- `PATCH` requests use partial-update semantics (`exclude_unset`): omitted fields are
  left unchanged.
- `attachments` fields are JSON arrays of `{ name, type, data }` base64 data-URL
  objects, stored as `jsonb`. Each attachment is validated server-side: `type` must
  be an image (`image/*`) or `application/pdf` MIME type, `data` must be a base64
  data URL whose declared MIME matches `type`, individual attachment data is capped
  at ~5 MB (7,000,000 base64 characters), and each record may hold at most 10
  attachments. Requests violating these constraints are rejected with `422`.
- Every route enforces the same per-second/hour/day rate limiting as existing
  endpoints, keyed off the JWT-derived `user_id`.
- Records reference `owner_user_id`/`user_id` via foreign keys to `users`; these are
  always populated from the verified session identity, so a foreign-key error against
  an unknown user is no longer reachable through normal use.

## 5. Data Model

### `users` table

- `user_id` (unique) — `"google:{sub}"` for Google accounts, `"dev:{hash}"` for dev-login accounts
- `google_sub` (unique, optional) — Google's stable subject identifier; the verified real-world identity for Google accounts
- `email` (optional)
- `name` (optional)
- `created_at`
- `updated_at`

### `usage_logs` table

- `user_id`
- `endpoint` (`places_autocomplete` or `place_details`)
- `provider` (`google_places`)
- `status_code`
- `request_summary` (`jsonb`)
- `created_at`

### `rate_limit_events` table

- `subject_type`
- `subject_key`
- `endpoint`
- `client_ip`
- `user_id` (optional)
- `allowed`
- `reason` (optional)
- `created_at`

### Trip-planning domain tables (aligned with `WinkyTravelDev`)

### `trips` table

- `id`
- `owner_user_id`
- `trip_name`
- `location`
- `start_date`
- `end_date`
- `created_at`
- `updated_at`

### `trip_shares` table

- `id`
- `trip_id`
- `shared_with_user_id`
- `shared_by_user_id`
- `can_view`
- `can_add`
- `can_delete`
- `can_edit`
- `can_owner`
- `created_at`
- `updated_at`

### `activities` table

- `id`
- `user_id`
- `trip_id`
- `name`
- `type`
- `notes`
- `scheduled_day` (optional)
- `scheduled_time` (optional)
- `time_of_day` (optional: `morning`/`afternoon`/`evening`)
- `attachments` (`jsonb`)
- `custom_type_name` (optional)
- `custom_icon` (optional)
- `created_at`
- `updated_at`

### `travels` table

- `id`
- `user_id`
- `trip_id`
- `type`
- `departure`
- `arrival`
- `date`
- `time`
- `confirmation_number`
- `notes`
- `attachments` (`jsonb`)
- `created_at`
- `updated_at`

### `hotels` table

- `id`
- `user_id`
- `trip_id`
- `name`
- `address`
- `check_in`
- `check_out`
- `confirmation_number`
- `notes`
- `attachments` (`jsonb`)
- `created_at`
- `updated_at`

### `transits` table

- `id`
- `user_id`
- `trip_id`
- `type`
- `from_location`
- `to_location`
- `notes`
- `attachments` (`jsonb`)
- `created_at`
- `updated_at`

### `schedule_items` table

- `id`
- `user_id`
- `trip_id`
- `day_date`
- `display_order`
- `item_type` (`activity`/`travel`/`hotel`/`transit`)
- `item_id`
- `created_at`
- `updated_at`

### `custom_activity_types` and `activity_icon_overrides`

- Persist custom activity labels/icons from the frontend settings model.

Indexes:

- `users.user_id` primary key
- `usage_logs` on `(user_id, created_at desc)`
- `usage_logs` on `(endpoint, created_at desc)`
- `rate_limit_events` on `(subject_type, subject_key, allowed, created_at desc)`
- `trips` on `(owner_user_id, start_date)`
- `trip_shares` on `(shared_with_user_id, trip_id)` and `(trip_id)`
- `activities` on `(user_id, trip_id)` and `(trip_id, scheduled_day)`
- `travels` on `(trip_id, date, time)`
- `hotels` on `(trip_id, check_in)`
- `schedule_items` on `(trip_id, day_date, display_order)`

## 6. Configuration

Loaded from `.env` via `config/settings.py`.

| Variable | Required | Default | Description |
|---------|----------|---------|-------------|
| `DB_HOST` | yes | none | PostgreSQL host |
| `DB_PORT` | no | `5432` | PostgreSQL port |
| `DB_NAME` | yes | none | PostgreSQL database name |
| `DB_USER` | yes | none | PostgreSQL database user |
| `DB_PASSWORD` | no | empty | PostgreSQL database password |
| `DB_SSLMODE` | no | `disable` | PostgreSQL SSL mode |
| `DATABASE_URL` | legacy | empty | Backward-compatible URI override |
| `API_HOST` | no | `0.0.0.0` | API bind host |
| `API_PORT` | no | `8000` | API bind port |
| `GOOGLE_MAPS_API_KEY` | recommended | empty | Server-side Places key |
| `GOOGLE_PLACES_BASE_URL` | no | `https://places.googleapis.com/v1` | Places base URL |
| `GOOGLE_TIMEOUT_SECONDS` | no | `8` | Upstream request timeout |
| `GOOGLE_CLIENT_ID` | yes | none | OAuth client ID; verified ID tokens must carry this audience |
| `JWT_SECRET_KEY` | yes | none | Symmetric (HS256) signing secret for backend-issued session JWTs |
| `JWT_EXPIRY_HOURS` | no | `168` | Session JWT lifetime in hours |
| `CORS_ALLOWED_ORIGINS` | yes | none | Comma-separated explicit origin allowlist (replaces wildcard CORS now that bearer tokens are in play) |
| `DEV_LOGIN_ENABLED` | no | `false` | Enables `POST /api/auth/dev-login`; must stay `false` in production |
| `DEV_LOGIN_MASTER_KEY` | no | empty | Shared secret required by the dev-login endpoint when enabled |
| `ENVIRONMENT` | no | `development` | Environment tag |
| `SERVICE_NAME` | no | `winky-travel-fastdb` | Service label |

## 7. Deployment Topology

```text
Proxmox host
└─ LXC (Debian)
   ├─ /opt/winky-travel-fastdb
   ├─ /opt/winky-travel-fastdb-env
   ├─ postgresql.service
   └─ winky-travel-fastdb.service
```

Deploy/update operations are scripted in `deploy/`.
