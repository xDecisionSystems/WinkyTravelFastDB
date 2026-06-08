# AGENT_LOG.md

Shared handoff log between agents. Newest entry first.
Read this before starting any task. Prepend a new entry after completing any task.
Archive to `history/YYYY-MM.md` when this file exceeds 200 lines (keep 10 most recent).

---

## [2026-06-08] claude-sonnet-4-6 - require Google sign-in; replace client-trusted user_id with verified session JWTs
**Action:** Implemented the backend half of the approved OAuth plan (`federated-wobbling-owl.md`, companion frontend repo `WinkyTravelDev`). Per explicit user decisions: (1) sessions use a backend-issued JWT sent as `Authorization: Bearer <jwt>`; (2) old anonymous device-identity data is destructively discarded — no migration path, since those accounts have no verifiable real-world identity; (3) Google sign-in is now REQUIRED for every user, closing the long-flagged gap where the API blindly trusted client-supplied `user_id`/`owner_user_id`; (4) added an env-gated dev-only login endpoint that issues the same JWT shape, for test/CI accounts that can't complete a real Google sign-in. Added `services/auth.py` (Google ID token verification via `google-auth`, HS256 session JWT issue/decode via `pyjwt`, and a `get_current_user_id` FastAPI dependency), new `api/routes/auth.py` (`POST /api/auth/google`, `POST /api/auth/dev-login`, `GET /api/auth/me`), and rewired every protected route (`trips`, `activities`, `travels`, `hotels`, `transits`, `schedule_items`, `settings`) to derive identity exclusively from the verified JWT — list/create routes no longer read `user_id`/`owner_user_id` from query params or request bodies, and get/update/delete-by-id routes fetch-then-check-ownership-then-404 (not 403, to avoid leaking existence). Replaced the wildcard CORS (`allow_origins=["*"]`) with an explicit `CORS_ALLOWED_ORIGINS` allowlist now that bearer tokens are in play. Deleted the superseded `services/mongo.py` (dead backward-compat shim) and `api/routes/users.py` (replaced entirely by `/api/auth/*`).
**Files changed:**
- `requirements.txt` - added `google-auth==2.35.0`, `pyjwt==2.9.0`, `requests==2.34.2` (the latter found missing during end-to-end verification: `google.auth.transport.requests` raises `ImportError` without it on a fresh install — it's a runtime dependency of `google-auth`'s requests transport, not just a transitive one)
- `config/settings.py` - added `google_client_id`, `jwt_secret_key`, `jwt_expiry_hours`, `dev_login_enabled`, `dev_login_master_key`, `cors_allowed_origins` settings + `_optional_bool`/`_optional_csv` helpers
- `services/auth.py` (new) - `GoogleProfile`, `AuthError`, `verify_google_id_token`, `issue_session_jwt`/`decode_session_jwt`, `get_current_user_id` FastAPI dependency
- `api/routes/auth.py` (new) - `POST /api/auth/{google,dev-login}`, `GET /api/auth/me`
- `services/models.py` - removed `UserUpsertRequest`/`UserCreateRequest`; added `GoogleLoginRequest`/`DevLoginRequest`/`AuthResponse`; removed client-supplied identity fields (`owner_user_id`, `user_id`, `shared_by_user_id`) from all `*CreateRequest`/upsert request models
- `services/postgres.py` - inserted a destructive one-time migration (adds `google_sub` to `users`, truncates `users` cascading to all dependent tables via FK `ON DELETE CASCADE`, since old anonymous rows have no verifiable identity); replaced `upsert_user`/`get_user`/`create_user` with `get_user`, `upsert_user_by_google_sub` (`user_id = "google:{sub}"`), `upsert_dev_user`; added `get_custom_activity_type` helper
- `services/mongo.py` - deleted (dead shim, nothing imported it)
- `api/routes/users.py` - deleted (superseded by `/api/auth/*`)
- `api/main.py` - registered `auth_router` in place of `users_router`; replaced wildcard CORS with `settings.cors_allowed_origins`
- `api/routes/{trips,activities,travels,hotels,transits,schedule_items,settings}.py` - every route now requires `Depends(get_current_user_id)`; create routes derive identity from the JWT instead of the request body; list routes source `user_id`/`owner_user_id` via `Depends`; get/update/delete-by-id routes fetch-then-check-ownership-then-404; trip-share creation uses the authenticated user as `shared_by_user_id` and verifies trip ownership first
- `README.md` - added "Authentication" section (flow, env vars, dev-login warnings); updated service description, core routes, and CRUD/ownership description; rewrote "Recommended next fixes" (removed now-fixed auth/CORS items)
- `ARCHITECTURE.md` - replaced the stale `/api/users/{upsert,create}` request-flow and endpoint-map entries (left over from a prior `users.py` deletion) with `/api/auth/{google,dev-login,me}` flow descriptions and a `get_current_user_id` dependency note; rewrote "Trip-domain CRUD conventions" to state identity comes exclusively from the JWT (no client-supplied `user_id`/`owner_user_id`, 404-on-ownership-mismatch); added `google_sub` to the `users` table schema; added `GOOGLE_CLIENT_ID`/`JWT_SECRET_KEY`/`JWT_EXPIRY_HOURS`/`CORS_ALLOWED_ORIGINS`/`DEV_LOGIN_ENABLED`/`DEV_LOGIN_MASTER_KEY` to the Configuration table
- `.env.example` - added `GOOGLE_CLIENT_ID`, `JWT_SECRET_KEY`, `JWT_EXPIRY_HOURS`, `CORS_ALLOWED_ORIGINS`, `DEV_LOGIN_ENABLED`, `DEV_LOGIN_MASTER_KEY`
- `VERSION.md` - bumped to `winky-travel-fastdb-v0.2.8` (incremented twice more during this entry's work: once for the `ARCHITECTURE.md` doc pass, once for the `requirements.txt` fix found during verification)
- `AGENT_LOG.md` - prepended this entry
**Decisions:** Chose a destructive migration (`TRUNCATE ... CASCADE`) over an additive one because old anonymous device-identity rows have no real-world identity to preserve or link to a Google account — the user explicitly confirmed discarding them is acceptable. Used deterministic user-id derivation (`google:{sub}` for Google users, `dev:{sha256(email)[:32]}` for dev/test users) so repeat logins always map to the same backend account. Used `404` (not `403`) on ownership mismatches to avoid leaking record existence to unauthorized callers, consistent with the pattern the user approved in the plan. Used `hmac.compare_digest` for the dev-login master-key check to avoid timing side-channels.
**Open items:** Coordinated cutover deploy with the frontend is the next step — the user explicitly chose to wait until the frontend OAuth work was complete before redeploying this backend (now done on the frontend side too). A real `GOOGLE_CLIENT_ID`/`JWT_SECRET_KEY` must be generated and configured before deploying (currently placeholders in `.env.example`/local env per the user's choice). Trip-share-aware authorization (shared collaborators viewing/editing shared trips) remains a known gap, called out in the README's "Recommended next fixes".

**Verification (end-to-end, 2026-06-08):** Spun up this backend locally against a disposable Dockerized PostgreSQL with `DEV_LOGIN_ENABLED=true`, plus the `WinkyTravelDev` frontend dev server pointed at it (a throwaway env, fully torn down afterward — no shared state touched). Confirmed via `curl`: unauthenticated requests to protected routes return `401`; `dev-login` returns `401` on a wrong master key and a valid `{ token, user }` on success; `/api/auth/me` returns the same user from a valid bearer token and `401` on a garbage token; created records' `owner_user_id`/`user_id` are derived solely from the JWT (a spoofed `owner_user_id` in the request body is silently ignored); cross-user record access returns `404` (not `403`); each user's trip list is isolated; CORS preflight succeeds for allowlisted origins and is rejected (no `access-control-allow-origin`) for others; `dev-login` 404s when `DEV_LOGIN_ENABLED` is false (confirmed in code at `api/routes/auth.py:43-44`). Also ran a Node script simulating the frontend's exact `fetch` sequence (dev-login → `/me` → list/create trips, activities, custom activity types) — all succeeded with correctly scoped ownership. `npm run build` in the frontend repo passed cleanly. This is the verification referenced as pending in the companion `WinkyTravelDev` `AGENT_LOG.md` entry — that repo's "Open items" line about pending end-to-end verification is now resolved.

---

## [2026-06-08] claude-sonnet-4-6 - validate attachments as images or PDFs with size/count limits
**Action:** Reviewed `WinkyTravelDev` (the frontend) to find backend improvement opportunities. Found that `Attachment = dict[str, Any]` in `services/models.py` was completely untyped/unvalidated — the frontend (`Schedule.tsx`/`Hotels.tsx`) reads user-picked files via `FileReader.readAsDataURL()` and stuffs the resulting base64 data URL directly into this field on `activities`/`travels`/`hotels`/`transits` records (stored as `jsonb`). There was no size limit anywhere — not in the Pydantic model, FastAPI request body config, or PostgreSQL — so a client could push arbitrarily large blobs into the DB or exhaust server memory parsing the JSON body. Per the user's request, replaced the untyped alias with a real `Attachment` Pydantic model that enforces: `type` must be `image/*` or `application/pdf`; `data` must be a base64 data URL whose declared MIME matches `type` (rejecting spoofed/mismatched pairs and non-data-URL values); `data` capped at ~5 MB (7,000,000 base64 chars); and at most 10 attachments per record. Verified with a standalone test venv (pydantic 2.9.2) that valid images/PDFs pass, `.docx`/mismatched-MIME/non-data-URL/oversized/over-count payloads are all rejected with `ValidationError` (→ FastAPI `422`), and that `model_dump()` round-trips cleanly into `services/postgres.py`'s existing `json.dumps(fields.get("attachments", []))` call (no downstream changes needed).
**Files changed:**
- `services/models.py` - replaced `Attachment = dict[str, Any]` with a validated `Attachment(BaseModel)` (`field_validator` on `type`, `model_validator` cross-checking `data`'s declared MIME against `type`); added `ATTACHMENT_ALLOWED_TYPES`/`ATTACHMENT_ALLOWED_TYPE_PREFIXES`/`ATTACHMENT_MAX_DATA_LENGTH`/`ATTACHMENT_MAX_COUNT` constants; added `max_length=ATTACHMENT_MAX_COUNT` to all 8 request-side `attachments: list[Attachment]` fields across `Activity`/`Travel`/`Hotel`/`Transit` `Create`/`Update` request models (left `*Record` response models as plain `list[Attachment]`)
- `ARCHITECTURE.md` - documented the new attachment validation rules (shape, allowed types, size/count caps, `422` on violation) in the trip-domain CRUD conventions section
- `VERSION.md` - bumped to `winky-travel-fastdb-v0.2.5`
- `AGENT_LOG.md` - prepended this entry
**Decisions:** Chose Pydantic-level validation (rejecting at the request boundary with `422`) over a Postgres `CHECK` constraint, since `jsonb` array element validation in SQL would be far more awkward and the goal is to reject bad input before it's stored, not just before it's queried. Cross-checked the `data` URL's declared MIME against the `type` field to prevent a client from declaring `image/png` while embedding a different MIME in the actual data URL — closes a spoofing gap a naive "check `type` only" validator would have left open. Did not add byte-level content sniffing (e.g., magic-number checks) since that's a much larger change and the declared-MIME cross-check already closes the most likely spoofing vector for this app's threat model (anonymous device-scoped users, not adversarial multi-tenant).
**Open items:** This only validates at the API boundary — existing rows created before this change (if any) are untouched and not re-validated. If a true content-sniffing guarantee is ever needed (e.g., multi-tenant exposure), revisit with a magic-number check via `python-magic` or similar.

---

## [2026-06-08] claude-sonnet-4-6 - fill endpoint-map gaps in ARCHITECTURE.md
**Action:** Reviewed the project for drift between docs and code (prompted by the user opening `SCHEMA.md`). `SCHEMA.md` matched `services/postgres.py`'s `_create_schema` exactly (every table/column/constraint/index), and all three `.env*` files had identical key sets — no changes needed there. Found that `ARCHITECTURE.md`'s "Endpoint Map" (section 4) was missing four routes that exist in code and are registered in `api/main.py`: `GET /llms.txt` (+ `/llm.txt` alias), `GET /api/dev/logs`, and `POST /api/dev/admin/delete-all-records`. These were already documented with curl examples in `README.md` but absent from the structural endpoint map.
**Files changed:**
- `ARCHITECTURE.md` - added the four missing routes to the endpoint map table (section 4), with one-line descriptions mirroring `README.md`'s existing documentation
- `VERSION.md` - bumped to `winky-travel-fastdb-v0.2.4`
- `AGENT_LOG.md` - prepended this entry
**Decisions:** Kept descriptions terse (matching the table's existing style) and noted the `X-Master-API-Key` auth requirement and destructive nature of the dev-admin route inline, since those are the key facts a reader of the structural map would need before reaching for `README.md`'s fuller usage docs.
**Open items:** None.

---

## [2026-06-08] claude-sonnet-4-6 - add optional Tailscale install to Proxmox deploy script
**Action:** Ported the "Install Tailscale?" flow from `fastLibrary`'s deploy script — the user noticed `WinkyTravelFastDB`'s setup script never offered this. Added an `INSTALL_TAILSCALE` setting (CLI flags `--install-tailscale`/`--no-install-tailscale`, env var, or interactive `[Y/n]` prompt defaulting to yes) that, when enabled, configures the LXC for TUN device access (`lxc.cgroup2.devices.allow`/`lxc.mount.entry` in `/etc/pve/lxc/<vmid>.conf`), installs Tailscale from its official apt repo inside the container, tags the container `tailscale`, reboots it, and waits for the API to come back up.
**Files changed:**
- `deploy/proxmox_deploy.sh` - added `INSTALL_TAILSCALE` var/flags/prompt, summary line, and the install/configure/tag/reboot block (runs after the health check passes, mirroring `fastLibrary`'s placement and logic)
- `VERSION.md` - bumped to `winky-travel-fastdb-v0.2.3`
- `AGENT_LOG.md` - prepended this entry
**Decisions:** Defaulted `INSTALL_TAILSCALE` to `n` for non-interactive runs (so scripted/CI invocations don't unexpectedly install it) but `[Y/n]` (default yes) when prompting interactively, matching `fastLibrary`'s convention. Routed all remote commands through the existing `ssh_run`/`lxc_exec` helpers so `--dry-run` and SSH multiplexing work automatically; captured the Tailscale apt install output into a temp log shown only on failure, consistent with this script's existing quiet-output pattern for the runtime package install.
**Open items:** None — not yet exercised against a live host with Tailscale enabled.

---

## [2026-06-08] claude-sonnet-4-6 - rework Proxmox deploy script (multiplexed SSH, dry-run, .env sync, diagnostics)
**Action:** Substantially reworked `deploy/proxmox_deploy.sh`, porting and adapting patterns from `fastLibrary`'s deploy script and fixing real failures hit during live deploys to a Proxmox host:
- Added SSH `ControlMaster`/`ControlPath` connection multiplexing (`ssh_open`/`ssh_close`/`ssh_run`/`lxc_exec`) so the whole run reuses one authenticated connection, plus a `--dry-run` flag that echoes remote commands instead of executing them.
- Added Debian LXC template auto-detection (`pveam`/`pvesm` query, sorted newest-first, interactive override) and made storage selection prefer pools with "ssd" in their name.
- Hardcoded `REPO_URL`/`REPO_BRANCH` defaults (no longer prompted) and fixed `DNS` to default to `8.8.8.8`.
- Added an `.env` upload picker (`--upload-env` / `UPLOAD_ENV_FILE`) that scans the working directory for `.env*` files, defaults to `.env.dev` when present, and uploads the chosen file as the container's runtime `.env` (falling back to `.env.example` from the repo when none is picked).
- **Fixed a critical credential bug**: the script previously hardcoded `CREATE ROLE winky LOGIN PASSWORD 'change-this-password'` and `CREATE DATABASE winky_travel`, which never matched the `DB_PASSWORD`/`DB_NAME` actually shipped in the uploaded `.env` (e.g. `.env.dev` uses a generated password and `DB_NAME=winky_travel_dev`), causing `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "winky"` at app startup. The script now reads `DB_USER`/`DB_PASSWORD`/`DB_NAME` out of the selected `UPLOAD_ENV_FILE` *before* provisioning PostgreSQL, SQL-escapes them, and uses them for `CREATE ROLE`/`CREATE DATABASE`/`OWNER`. Also added an `ALTER ROLE ... LOGIN PASSWORD` self-heal branch so re-running against an existing container corrects a stale password rather than leaving it mismatched.
- Replaced fragile `$...$` SQL dollar-quoting (which `printf '%q'` was corrupting into garbage like `363winky363`) with single-quoted literals plus `''`-escaping.
- Added health-check polling with `systemctl status`/`journalctl` diagnostics on failure, and a final summary block (health/docs URLs, dry-run banner, config vs. uploaded-env distinction).
- Quieted `apt-get`/`pip install` output, only surfacing it (via a captured temp log) when a step actually fails.
**Files changed:**
- `deploy/proxmox_deploy.sh` - all changes above
- `VERSION.md` - bumped to `winky-travel-fastdb-v0.2.2`
- `AGENT_LOG.md` - prepended this entry
**Decisions:** Deliberately did NOT add SSH deploy-key support for private-repo cloning (drafted it, then reverted at the user's request — they're making the GitHub repo public instead, so `REPO_URL` stays a plain HTTPS URL). Derived DB role/database identity from the uploaded `.env` rather than introducing new CLI flags, since the `.env` is already the single source of truth the running app reads from — keeping provisioning and runtime config self-consistent by construction.
**Open items:** The container from earlier failed runs was provisioned with the old hardcoded `change-this-password`; re-running this script against the same VMID should self-heal it via the new `ALTER ROLE` branch, but this hasn't yet been confirmed against a live host.

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
