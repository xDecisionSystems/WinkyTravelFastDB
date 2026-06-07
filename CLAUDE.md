# CLAUDE.md

Repository instructions for Claude-based agents.

## Overview

Winky Travel FastDB is a FastAPI + MongoDB backend for:

- user profile upsert/read
- Google Places autocomplete/details proxy
- per-user usage logging

Deployed to a Proxmox LXC with native `mongod` and systemd-managed API.

## Commands

- Install deps: `pip install -r requirements.txt`
- Run locally: `uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`
- Health check: `curl http://127.0.0.1:8000/health`
- Syntax check:
  ```bash
  python3 -m py_compile api/main.py api/routes/health.py api/routes/users.py api/routes/places.py config/settings.py services/models.py services/mongo.py
  ```

## Change Hygiene

- Update `ARCHITECTURE.md` when endpoint/data contracts change.
- Keep `.env.example` and `.env.dev` aligned when config keys change.
- Keep Google API keys on server only.

## Version Rule

- Bump patch version in `VERSION.md` on every change.
- Format: `VERSION_NAME=<version>`

## Handoff Rule

Use `AGENT_LOG.md` for all task handoffs with newest entries first.
