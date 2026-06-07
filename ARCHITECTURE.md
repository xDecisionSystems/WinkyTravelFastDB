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

### `POST /api/users/upsert`

1. Validate payload (`user_id`, optional `email`, `name`).
2. Upsert user record by `user_id`.
3. Set `created_at` on insert and `updated_at` on every write.

### `POST /api/users/create`

1. Validate optional profile payload (`email`, `name`).
2. Generate a backend `user_id` (UUID).
3. Insert user record with generated ID and timestamps.
4. Return created user record.

## 4. Endpoint Map

| Method | Path | Purpose |
|-------|------|---------|
| GET | `/health` | Service health/status |
| POST | `/api/users/create` | Create user with backend-generated `user_id` |
| POST | `/api/users/upsert` | Create/update user record |
| GET | `/api/users/{user_id}` | Fetch user record |
| POST | `/api/places/autocomplete` | Google Places autocomplete proxy |
| POST | `/api/places/details` | Google place details proxy |

## 5. Data Model

### `users` table

- `user_id` (unique)
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
- `vacation_name`
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
