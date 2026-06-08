# AGENT_LOG.md

Shared handoff log between agents. Newest entry first.
Read this before starting any task. Prepend a new entry after completing any task.
Archive to `history/YYYY-MM.md` when this file exceeds 200 lines (keep 10 most recent).

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
