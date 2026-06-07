# AGENT.md

Guidance for programming agents contributing to this repository.

## 1. Mission

Maintain a self-hosted backend for Winky Travel running in a Debian-based Proxmox LXC:

- FastAPI HTTP service for health, user records, and Google Places proxy endpoints.
- PostgreSQL persistence for users and per-user Places usage logs.
- Deployment/update scripts for repeatable LXC operations.

Prioritize security (server-side API key handling), stable API contracts, and reliable operations.

## 2. Repository Scope

```text
WinkyTravelFastDB/
|- api/
|  |- main.py
|  `- routes/
|     |- health.py
|     |- users.py
|     `- places.py
|- config/
|  `- settings.py
|- services/
|  |- models.py
|  `- mongo.py
|- deploy/
|  |- proxmox_deploy.sh
|  |- update.sh
|  `- restart.sh
|- scripts/
|- .env.example
|- .env.dev
|- requirements.txt
|- AGENT.md
|- CLAUDE.md
|- ARCHITECTURE.md
|- SCHEMA.md
|- AGENT_LOG.md
`- VERSION.md
```

## 3. Runtime Services

| Service | Description | Port | Binding |
|--------|-------------|------|---------|
| `postgresql` | PostgreSQL (native apt) | 5432 | localhost only |
| `winky-travel-fastdb` | FastAPI API (uvicorn) | 8000 | 0.0.0.0 |

PostgreSQL must not be exposed publicly.

## 4. Environment Rules

- Python 3.10+.
- Use a project venv (`/opt/winky-travel-fastdb-env` in production).
- Install dependencies with `pip install -r requirements.txt`.

## 5. Coding Rules

- Async I/O for database and upstream HTTP calls.
- Validate request payloads with Pydantic at API boundaries.
- Keep Google API keys server-side only; never return keys to clients.
- Preserve endpoint behavior documented in `ARCHITECTURE.md`.
- If database schema changes, update `SCHEMA.md` in the same change.

## 6. Version Rule

- On every code/doc change, increment patch version in `VERSION.md`.
- If user specifies an exact version name, use that exact value.
- Format: `VERSION_NAME=<version>`

## 7. Agent Log Rule

Before work:
1. Read `AGENT_LOG.md`.
2. Note open items.

After work:
1. Prepend a new entry in this format:

```markdown
## [YYYY-MM-DD] <agent-name> - <one-line summary>
**Action:** What was done and why.
**Files changed:** List each file modified/created/deleted.
**Decisions:** Non-obvious choices and rationale.
**Open items:** Follow-ups or deferred work.
```

2. If `AGENT_LOG.md` exceeds 200 lines, archive old entries to `history/YYYY-MM.md`, keeping the 10 newest entries in `AGENT_LOG.md`.
