# AGENT_LOG.md

Shared handoff log between agents. Newest entry first.
Read this before starting any task. Prepend a new entry after completing any task.
Archive to `history/YYYY-MM.md` when this file exceeds 200 lines (keep 10 most recent).

---

## [2026-06-07] claude-sonnet-4-6 - fix asyncpg build failure on Debian 13/Python 3.13 LXC deploys
**Action:** Deploys to a freshly auto-provisioned Debian 13 ("trixie") LXC were failing during `pip install -r requirements.txt` with `Failed building wheel for asyncpg` (`_PyInterpreterState_GetConfig`, `_PyLong_AsByteArray too few arguments` — CPython internal API changes in 3.13). Root cause: `asyncpg==0.29.0` has no prebuilt `cp313` wheel, so pip fell back to compiling its Cython-based C extensions against an incompatible CPython ABI. Bumped the pin to `asyncpg==0.31.0`, which ships prebuilt `manylinux` `cp313` wheels (verified locally: installs via wheel, no compilation, imports cleanly).
**Files changed:**
- `requirements.txt` - bumped `asyncpg` from `0.29.0` to `0.31.0`
- `VERSION.md` - bumped to `winky-travel-fastdb-v0.2.1`
- `AGENT_LOG.md` - prepended this entry
**Decisions:** Picked `0.31.0` specifically because it's the earliest patch in the 0.3x line confirmed (via PyPI JSON API) to publish `cp313`-tagged wheels — avoids both the 3.13 build break and an unnecessary jump to a newer minor that might need wider regression testing.
**Open items:** None for this fix. Separately, `deploy/proxmox_deploy.sh` was extended this session with SSH multiplexing, dry-run mode, health-check diagnostics, SSD-preferring storage selection, hardcoded repo URL/branch defaults, Debian template auto-detection, an `.env` upload picker (defaulting to `.env.dev`), and quieted apt/pip output — those changes are tracked in that file's own history, not duplicated here.

---

## [2026-06-07] claude-sonnet-4-6 - add CRUD endpoints for trip-planning domain entities
**Action:** Built out the previously-missing REST CRUD surface for the trip-planning domain tables that already existed in the schema (`trips`, `trip_shares`, `activities`, `travels`, `hotels`, `transits`, `schedule_items`, `custom_activity_types`, `activity_icon_overrides`). This closes the gap noted by `WinkyTravelDev` review: that app currently stores everything in browser `localStorage` because this backend had no domain endpoints to call (only `/api/users` and `/api/places` existed). Added pydantic request/record models, asyncpg-backed service functions following the existing `upsert_user`/`get_user` patterns (parameterized queries, `RETURNING`, `jsonb` handling for `attachments` via `json.dumps`/`json.loads`), and FastAPI routers with rate limiting on every route, mirroring `users.py`/`places.py` conventions. Wired all new routers into `api/main.py`.
**Files changed:**
- `services/models.py` - added `Trip*`, `TripShare*`, `Activity*`, `Travel*`, `Hotel*`, `Transit*`, `ScheduleItem*`, `CustomActivityType*`, `ActivityIconOverride*` request/record models (aliased `date`/`time` imports to `date_type`/`time_type` to avoid pydantic forward-ref collisions with same-named model fields)
- `services/postgres.py` - added CRUD functions for all nine new entities plus `_row_to_dict`/`_new_id` helpers
- `api/routes/trips.py` - new router: trip CRUD + trip-share sub-resource CRUD
- `api/routes/activities.py` - new router: activity CRUD
- `api/routes/travels.py` - new router: travel CRUD
- `api/routes/hotels.py` - new router: hotel CRUD
- `api/routes/transits.py` - new router: transit CRUD
- `api/routes/schedule_items.py` - new router: schedule item CRUD (list requires `trip_id`)
- `api/routes/settings.py` - new router: custom activity type CRUD + icon override upsert/list/delete
- `api/main.py` - registered all nine new routers
- `README.md` - documented new CRUD route groups and conventions
- `ARCHITECTURE.md` - expanded endpoint map and added trip-domain CRUD conventions section
- `VERSION.md` - bumped to `winky-travel-fastdb-v0.2.0`
- `AGENT_LOG.md` - prepended this entry
**Decisions:** Followed existing route/service/model layering exactly rather than introducing new abstractions (e.g., no generic CRUD base class) to stay consistent with `users.py`. List endpoints require an owning `user_id`/`owner_user_id` query parameter to avoid unscoped table scans. `PATCH` uses pydantic `exclude_unset` for partial updates. Verified end-to-end against a disposable Dockerized PostgreSQL instance (schema auto-creation + full CRUD + delete + 404 + foreign-key enforcement) for every new entity including trip shares; all 55 routes load and the OpenAPI schema generates cleanly.
**Open items:** No authentication/authorization layer yet — routes trust client-supplied `user_id`/`owner_user_id` as before (tracked in "Recommended next fixes" in `README.md`). The `WinkyTravelDev` frontend still needs to be migrated from `localStorage` to call these new endpoints (separate follow-up in that repo).

---

## [2026-06-07] codex-gpt-5 - scaffold initial FastAPI + MongoDB backend for Winky Travel
**Action:** Bootstrapped repository structure for a Proxmox-deployable FastAPI backend with MongoDB integration, Google Places proxy endpoints, user upsert/read routes, usage logging, env/config handling, and deployment/restart/update scripts. Added required project docs (`AGENT`, `CLAUDE`, `ARCHITECTURE`, `AGENT_LOG`, `VERSION`).
**Files changed:** `README.md`, `requirements.txt`, `.env.example`, `.env.dev`, `api/main.py`, `api/routes/health.py`, `api/routes/users.py`, `api/routes/places.py`, `config/settings.py`, `services/models.py`, `services/mongo.py`, `deploy/proxmox_deploy.sh`, `deploy/update.sh`, `deploy/restart.sh`, `AGENT.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `AGENT_LOG.md`, `VERSION.md`, package init files, and scaffold directories.
**Decisions:** Kept Google Places integration server-side only to protect API keys and enable per-user usage tracking in MongoDB. Chose a minimal but production-oriented baseline to keep future changes incremental.
**Open items:** Add authentication/authorization layer (JWT/session), rate limiting, and richer analytics queries before production exposure.
