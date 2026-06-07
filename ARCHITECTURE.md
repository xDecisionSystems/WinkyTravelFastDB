# ARCHITECTURE.md

## 1. High-Level Design

Winky Travel FastDB is a single FastAPI service backed by MongoDB.

```text
Winky Web App -> FastAPI (this repo) -> MongoDB
                         |
                         +-> Google Places API (server-side proxy)
```

Client never receives or uses the Google Places API key directly.

## 2. Runtime Components

| Component | Technology | Port | Binding |
|----------|------------|------|---------|
| API | FastAPI + uvicorn | 8000 | 0.0.0.0 |
| Database | MongoDB 8.0 | 27017 | localhost |
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

## 4. Endpoint Map

| Method | Path | Purpose |
|-------|------|---------|
| GET | `/health` | Service health/status |
| POST | `/api/users/upsert` | Create/update user record |
| GET | `/api/users/{user_id}` | Fetch user record |
| POST | `/api/places/autocomplete` | Google Places autocomplete proxy |
| POST | `/api/places/details` | Google place details proxy |

## 5. Data Model

### `users` collection

- `user_id` (unique)
- `email` (optional)
- `name` (optional)
- `created_at`
- `updated_at`

### `usage_logs` collection

- `user_id`
- `endpoint` (`places_autocomplete` or `place_details`)
- `provider` (`google_places`)
- `status_code`
- `request_summary`
- `created_at`

Indexes:

- `users.user_id` unique
- `usage_logs` on `(user_id, created_at desc)`
- `usage_logs` on `(endpoint, created_at desc)`

## 6. Configuration

Loaded from `.env` via `config/settings.py`.

| Variable | Required | Default | Description |
|---------|----------|---------|-------------|
| `MONGO_URI` | yes | none | Mongo connection URI |
| `MONGO_DB` | yes | none | DB name |
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
   ├─ mongod.service
   └─ winky-travel-fastdb.service
```

Deploy/update operations are scripted in `deploy/`.
