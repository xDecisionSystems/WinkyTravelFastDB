from __future__ import annotations

# Backward-compatible shim after migrating from MongoDB to PostgreSQL.
from services.postgres import (  # noqa: F401
    close,
    connect,
    count_rate_limit_events,
    delete_all_records,
    get_user,
    insert_rate_limit_event,
    insert_usage_log,
    upsert_user,
    utcnow,
)
