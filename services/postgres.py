from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from config.settings import settings


_pool: asyncpg.Pool | None = None
_last_rate_limit_prune_seconds: float = 0.0
_RATE_LIMIT_PRUNE_INTERVAL_SECONDS = 300.0


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pool_or_raise() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("PostgreSQL is not connected")
    return _pool


async def _create_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT,
            name TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            provider TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            request_summary JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            trip_name TEXT NOT NULL,
            location TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trip_shares (
            id BIGSERIAL PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            shared_with_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            shared_by_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            can_view BOOLEAN NOT NULL DEFAULT TRUE,
            can_add BOOLEAN NOT NULL DEFAULT FALSE,
            can_delete BOOLEAN NOT NULL DEFAULT FALSE,
            can_edit BOOLEAN NOT NULL DEFAULT FALSE,
            can_owner BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            UNIQUE (trip_id, shared_with_user_id),
            CHECK (can_view = TRUE),
            CHECK (
                can_owner = FALSE OR
                (can_view = TRUE AND can_add = TRUE AND can_delete = TRUE AND can_edit = TRUE)
            )
        )
        """
    )
    # Backward-compatible migration for earlier schema naming.
    await conn.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'trips'
                  AND column_name = 'user_id'
            ) THEN
                ALTER TABLE trips RENAME COLUMN user_id TO owner_user_id;
            END IF;
        END $$;
        """
    )
    await conn.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'trips'
                  AND column_name = 'vacation_name'
            ) THEN
                ALTER TABLE trips RENAME COLUMN vacation_name TO trip_name;
            END IF;
        END $$;
        """
    )
    # Backward-compatible migration for earlier share permissions.
    await conn.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'trip_shares'
                  AND column_name = 'can_owner'
            ) THEN
                ALTER TABLE trip_shares ADD COLUMN can_owner BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
        """
    )
    await conn.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'trip_shares_can_owner_requires_full_access'
            ) THEN
                ALTER TABLE trip_shares
                ADD CONSTRAINT trip_shares_can_owner_requires_full_access
                CHECK (
                    can_owner = FALSE OR
                    (can_view = TRUE AND can_add = TRUE AND can_delete = TRUE AND can_edit = TRUE)
                );
            END IF;
        END $$;
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            trip_id TEXT REFERENCES trips(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            scheduled_day DATE,
            scheduled_time TIME,
            time_of_day TEXT CHECK (time_of_day IN ('morning', 'afternoon', 'evening')),
            attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
            custom_type_name TEXT,
            custom_icon TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS travels (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            trip_id TEXT REFERENCES trips(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            departure TEXT NOT NULL,
            arrival TEXT NOT NULL,
            date DATE NOT NULL,
            time TIME NOT NULL,
            confirmation_number TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hotels (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            trip_id TEXT REFERENCES trips(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            check_in DATE NOT NULL,
            check_out DATE NOT NULL,
            confirmation_number TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transits (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            trip_id TEXT REFERENCES trips(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            from_location TEXT NOT NULL DEFAULT '',
            to_location TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_items (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            day_date DATE NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            item_type TEXT NOT NULL CHECK (item_type IN ('activity', 'travel', 'hotel', 'transit')),
            item_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            UNIQUE (trip_id, day_date, display_order)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_activity_types (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            icon TEXT NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_icon_overrides (
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            activity_type_id TEXT NOT NULL,
            icon TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (user_id, activity_type_id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            id BIGSERIAL PRIMARY KEY,
            subject_type TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            client_ip TEXT NOT NULL,
            user_id TEXT,
            allowed BOOLEAN NOT NULL,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )

    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_usage_logs_user_created_at
        ON usage_logs (user_id, created_at DESC)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_usage_logs_endpoint_created_at
        ON usage_logs (endpoint, created_at DESC)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trips_owner_start_date
        ON trips (owner_user_id, start_date)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trip_shares_shared_with_user
        ON trip_shares (shared_with_user_id, trip_id)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trip_shares_trip_id
        ON trip_shares (trip_id)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_activities_user_trip
        ON activities (user_id, trip_id)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_activities_trip_scheduled_day
        ON activities (trip_id, scheduled_day)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_activities_type
        ON activities (type)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_travels_trip_datetime
        ON travels (trip_id, date, time)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hotels_trip_checkin
        ON hotels (trip_id, check_in)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_transits_trip
        ON transits (trip_id)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_items_trip_day_order
        ON schedule_items (trip_id, day_date, display_order)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_items_lookup
        ON schedule_items (item_type, item_id)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_custom_activity_types_user
        ON custom_activity_types (user_id)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rate_limit_events_subject_allowed_created_at
        ON rate_limit_events (subject_type, subject_key, allowed, created_at DESC)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rate_limit_events_created_at
        ON rate_limit_events (created_at DESC)
        """
    )


async def _prune_old_rate_limit_events(conn: asyncpg.Connection) -> None:
    cutoff = utcnow() - timedelta(hours=settings.rate_limit_retention_hours)
    await conn.execute(
        "DELETE FROM rate_limit_events WHERE created_at < $1",
        cutoff,
    )


async def _maybe_prune_old_rate_limit_events(conn: asyncpg.Connection) -> None:
    global _last_rate_limit_prune_seconds
    now_seconds = time.monotonic()
    if now_seconds - _last_rate_limit_prune_seconds < _RATE_LIMIT_PRUNE_INTERVAL_SECONDS:
        return
    _last_rate_limit_prune_seconds = now_seconds
    await _prune_old_rate_limit_events(conn)


async def connect() -> None:
    global _pool
    if _pool is not None:
        return

    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=10,
    )

    async with _pool.acquire() as conn:
        await _create_schema(conn)
        await _prune_old_rate_limit_events(conn)


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
    _pool = None


async def upsert_user(user_id: str, email: str | None, name: str | None) -> dict[str, Any]:
    now = utcnow()
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (user_id, email, name, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $4)
            ON CONFLICT (user_id)
            DO UPDATE
            SET email = COALESCE(EXCLUDED.email, users.email),
                name = COALESCE(EXCLUDED.name, users.name),
                updated_at = EXCLUDED.updated_at
            RETURNING user_id, email, name, created_at, updated_at
            """,
            user_id,
            email,
            name,
            now,
        )

    if row is None:
        raise RuntimeError("Failed to load user after upsert")
    return dict(row)


async def get_user(user_id: str) -> dict[str, Any] | None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, email, name, created_at, updated_at FROM users WHERE user_id = $1",
            user_id,
        )
    return dict(row) if row is not None else None


async def create_user(email: str | None, name: str | None) -> dict[str, Any]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        for _ in range(5):
            generated_user_id = str(uuid.uuid4())
            now = utcnow()
            row = await conn.fetchrow(
                """
                INSERT INTO users (user_id, email, name, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $4)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING user_id, email, name, created_at, updated_at
                """,
                generated_user_id,
                email,
                name,
                now,
            )
            if row is not None:
                return dict(row)

    raise RuntimeError("Failed to create user after retries")


async def insert_usage_log(
    user_id: str,
    endpoint: str,
    status_code: int,
    request_summary: dict[str, Any],
) -> None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usage_logs (user_id, endpoint, provider, status_code, request_summary, created_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            """,
            user_id,
            endpoint,
            "google_places",
            status_code,
            json.dumps(request_summary),
            utcnow(),
        )


async def count_rate_limit_events(
    subject_type: str,
    subject_key: str,
    since: datetime,
) -> int:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS count
            FROM rate_limit_events
            WHERE subject_type = $1
              AND subject_key = $2
              AND allowed = TRUE
              AND created_at >= $3
            """,
            subject_type,
            subject_key,
            since,
        )
    if row is None:
        return 0
    return int(row["count"])


async def insert_rate_limit_event(
    *,
    subject_type: str,
    subject_key: str,
    endpoint: str,
    client_ip: str,
    user_id: str | None,
    allowed: bool,
    reason: str | None = None,
) -> None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO rate_limit_events (
                subject_type,
                subject_key,
                endpoint,
                client_ip,
                user_id,
                allowed,
                reason,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            subject_type,
            subject_key,
            endpoint,
            client_ip,
            user_id,
            allowed,
            reason,
            utcnow(),
        )
        await _maybe_prune_old_rate_limit_events(conn)


def _row_to_dict(row: asyncpg.Record | None, *, json_fields: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if row is None:
        return None
    doc = dict(row)
    for field in json_fields:
        if isinstance(doc.get(field), str):
            doc[field] = json.loads(doc[field])
    return doc


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Trips
# ---------------------------------------------------------------------------


async def create_trip(
    *,
    owner_user_id: str,
    trip_name: str,
    location: str,
    start_date: Any,
    end_date: Any,
) -> dict[str, Any]:
    now = utcnow()
    trip_id = _new_id()
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO trips (id, owner_user_id, trip_name, location, start_date, end_date, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
            RETURNING id, owner_user_id, trip_name, location, start_date, end_date, created_at, updated_at
            """,
            trip_id,
            owner_user_id,
            trip_name,
            location,
            start_date,
            end_date,
            now,
        )
    if row is None:
        raise RuntimeError("Failed to create trip")
    return dict(row)


async def list_trips(owner_user_id: str) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, owner_user_id, trip_name, location, start_date, end_date, created_at, updated_at
            FROM trips
            WHERE owner_user_id = $1
            ORDER BY start_date ASC
            """,
            owner_user_id,
        )
    return [dict(row) for row in rows]


async def get_trip(trip_id: str) -> dict[str, Any] | None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, owner_user_id, trip_name, location, start_date, end_date, created_at, updated_at
            FROM trips
            WHERE id = $1
            """,
            trip_id,
        )
    return dict(row) if row is not None else None


async def update_trip(trip_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        return await get_trip(trip_id)

    assignments: list[str] = []
    values: list[Any] = []
    for index, (column, value) in enumerate(fields.items(), start=1):
        assignments.append(f"{column} = ${index}")
        values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(trip_id)
    trip_id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE trips
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${trip_id_index}
            RETURNING id, owner_user_id, trip_name, location, start_date, end_date, created_at, updated_at
            """,
            *values,
        )
    return dict(row) if row is not None else None


async def delete_trip(trip_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM trips WHERE id = $1", trip_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Trip shares
# ---------------------------------------------------------------------------


async def create_trip_share(
    *,
    trip_id: str,
    shared_with_user_id: str,
    shared_by_user_id: str,
    can_view: bool,
    can_add: bool,
    can_delete: bool,
    can_edit: bool,
    can_owner: bool,
) -> dict[str, Any]:
    now = utcnow()
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO trip_shares (
                trip_id, shared_with_user_id, shared_by_user_id,
                can_view, can_add, can_delete, can_edit, can_owner,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
            ON CONFLICT (trip_id, shared_with_user_id)
            DO UPDATE
            SET shared_by_user_id = EXCLUDED.shared_by_user_id,
                can_view = EXCLUDED.can_view,
                can_add = EXCLUDED.can_add,
                can_delete = EXCLUDED.can_delete,
                can_edit = EXCLUDED.can_edit,
                can_owner = EXCLUDED.can_owner,
                updated_at = EXCLUDED.updated_at
            RETURNING id, trip_id, shared_with_user_id, shared_by_user_id,
                      can_view, can_add, can_delete, can_edit, can_owner,
                      created_at, updated_at
            """,
            trip_id,
            shared_with_user_id,
            shared_by_user_id,
            can_view,
            can_add,
            can_delete,
            can_edit,
            can_owner,
            now,
        )
    if row is None:
        raise RuntimeError("Failed to create trip share")
    return dict(row)


async def list_trip_shares(trip_id: str) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, trip_id, shared_with_user_id, shared_by_user_id,
                   can_view, can_add, can_delete, can_edit, can_owner,
                   created_at, updated_at
            FROM trip_shares
            WHERE trip_id = $1
            ORDER BY created_at ASC
            """,
            trip_id,
        )
    return [dict(row) for row in rows]


async def update_trip_share(share_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        pool = _pool_or_raise()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, trip_id, shared_with_user_id, shared_by_user_id,
                       can_view, can_add, can_delete, can_edit, can_owner,
                       created_at, updated_at
                FROM trip_shares WHERE id = $1
                """,
                share_id,
            )
        return dict(row) if row is not None else None

    assignments: list[str] = []
    values: list[Any] = []
    for index, (column, value) in enumerate(fields.items(), start=1):
        assignments.append(f"{column} = ${index}")
        values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(share_id)
    share_id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE trip_shares
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${share_id_index}
            RETURNING id, trip_id, shared_with_user_id, shared_by_user_id,
                      can_view, can_add, can_delete, can_edit, can_owner,
                      created_at, updated_at
            """,
            *values,
        )
    return dict(row) if row is not None else None


async def delete_trip_share(share_id: int) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM trip_shares WHERE id = $1", share_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

_ACTIVITY_COLUMNS = (
    "id", "user_id", "trip_id", "name", "type", "notes",
    "scheduled_day", "scheduled_time", "time_of_day", "attachments",
    "custom_type_name", "custom_icon", "created_at", "updated_at",
)


async def create_activity(*, user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    record_id = _new_id()
    attachments = json.dumps(fields.get("attachments", []))
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO activities (
                id, user_id, trip_id, name, type, notes,
                scheduled_day, scheduled_time, time_of_day, attachments,
                custom_type_name, custom_icon, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $13)
            RETURNING id, user_id, trip_id, name, type, notes,
                      scheduled_day, scheduled_time, time_of_day, attachments,
                      custom_type_name, custom_icon, created_at, updated_at
            """,
            record_id,
            user_id,
            fields.get("trip_id"),
            fields["name"],
            fields["type"],
            fields.get("notes", ""),
            fields.get("scheduled_day"),
            fields.get("scheduled_time"),
            fields.get("time_of_day"),
            attachments,
            fields.get("custom_type_name"),
            fields.get("custom_icon"),
            now,
        )
    doc = _row_to_dict(row, json_fields=("attachments",))
    if doc is None:
        raise RuntimeError("Failed to create activity")
    return doc


async def list_activities(*, user_id: str, trip_id: str | None = None) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        if trip_id is not None:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, name, type, notes,
                       scheduled_day, scheduled_time, time_of_day, attachments,
                       custom_type_name, custom_icon, created_at, updated_at
                FROM activities
                WHERE user_id = $1 AND trip_id = $2
                ORDER BY created_at ASC
                """,
                user_id,
                trip_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, name, type, notes,
                       scheduled_day, scheduled_time, time_of_day, attachments,
                       custom_type_name, custom_icon, created_at, updated_at
                FROM activities
                WHERE user_id = $1
                ORDER BY created_at ASC
                """,
                user_id,
            )
    docs = [_row_to_dict(row, json_fields=("attachments",)) for row in rows]
    return [doc for doc in docs if doc is not None]


async def get_activity(activity_id: str) -> dict[str, Any] | None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, trip_id, name, type, notes,
                   scheduled_day, scheduled_time, time_of_day, attachments,
                   custom_type_name, custom_icon, created_at, updated_at
            FROM activities
            WHERE id = $1
            """,
            activity_id,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def update_activity(activity_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        return await get_activity(activity_id)

    assignments: list[str] = []
    values: list[Any] = []
    for column, value in fields.items():
        if column == "attachments":
            index = len(values) + 1
            assignments.append(f"attachments = ${index}::jsonb")
            values.append(json.dumps(value))
        else:
            index = len(values) + 1
            assignments.append(f"{column} = ${index}")
            values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(activity_id)
    id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE activities
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${id_index}
            RETURNING id, user_id, trip_id, name, type, notes,
                      scheduled_day, scheduled_time, time_of_day, attachments,
                      custom_type_name, custom_icon, created_at, updated_at
            """,
            *values,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def delete_activity(activity_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM activities WHERE id = $1", activity_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Travels
# ---------------------------------------------------------------------------


async def create_travel(*, user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    record_id = _new_id()
    attachments = json.dumps(fields.get("attachments", []))
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO travels (
                id, user_id, trip_id, type, departure, arrival, date, time,
                confirmation_number, notes, attachments, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $12)
            RETURNING id, user_id, trip_id, type, departure, arrival, date, time,
                      confirmation_number, notes, attachments, created_at, updated_at
            """,
            record_id,
            user_id,
            fields.get("trip_id"),
            fields["type"],
            fields["departure"],
            fields["arrival"],
            fields["date"],
            fields["time"],
            fields.get("confirmation_number", ""),
            fields.get("notes", ""),
            attachments,
            now,
        )
    doc = _row_to_dict(row, json_fields=("attachments",))
    if doc is None:
        raise RuntimeError("Failed to create travel")
    return doc


async def list_travels(*, user_id: str, trip_id: str | None = None) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        if trip_id is not None:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, type, departure, arrival, date, time,
                       confirmation_number, notes, attachments, created_at, updated_at
                FROM travels
                WHERE user_id = $1 AND trip_id = $2
                ORDER BY date ASC, time ASC
                """,
                user_id,
                trip_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, type, departure, arrival, date, time,
                       confirmation_number, notes, attachments, created_at, updated_at
                FROM travels
                WHERE user_id = $1
                ORDER BY date ASC, time ASC
                """,
                user_id,
            )
    docs = [_row_to_dict(row, json_fields=("attachments",)) for row in rows]
    return [doc for doc in docs if doc is not None]


async def get_travel(travel_id: str) -> dict[str, Any] | None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, trip_id, type, departure, arrival, date, time,
                   confirmation_number, notes, attachments, created_at, updated_at
            FROM travels
            WHERE id = $1
            """,
            travel_id,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def update_travel(travel_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        return await get_travel(travel_id)

    assignments: list[str] = []
    values: list[Any] = []
    for column, value in fields.items():
        if column == "attachments":
            index = len(values) + 1
            assignments.append(f"attachments = ${index}::jsonb")
            values.append(json.dumps(value))
        else:
            index = len(values) + 1
            assignments.append(f"{column} = ${index}")
            values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(travel_id)
    id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE travels
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${id_index}
            RETURNING id, user_id, trip_id, type, departure, arrival, date, time,
                      confirmation_number, notes, attachments, created_at, updated_at
            """,
            *values,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def delete_travel(travel_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM travels WHERE id = $1", travel_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Hotels
# ---------------------------------------------------------------------------


async def create_hotel(*, user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    record_id = _new_id()
    attachments = json.dumps(fields.get("attachments", []))
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO hotels (
                id, user_id, trip_id, name, address, check_in, check_out,
                confirmation_number, notes, attachments, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $11)
            RETURNING id, user_id, trip_id, name, address, check_in, check_out,
                      confirmation_number, notes, attachments, created_at, updated_at
            """,
            record_id,
            user_id,
            fields.get("trip_id"),
            fields["name"],
            fields["address"],
            fields["check_in"],
            fields["check_out"],
            fields.get("confirmation_number", ""),
            fields.get("notes", ""),
            attachments,
            now,
        )
    doc = _row_to_dict(row, json_fields=("attachments",))
    if doc is None:
        raise RuntimeError("Failed to create hotel")
    return doc


async def list_hotels(*, user_id: str, trip_id: str | None = None) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        if trip_id is not None:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, name, address, check_in, check_out,
                       confirmation_number, notes, attachments, created_at, updated_at
                FROM hotels
                WHERE user_id = $1 AND trip_id = $2
                ORDER BY check_in ASC
                """,
                user_id,
                trip_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, name, address, check_in, check_out,
                       confirmation_number, notes, attachments, created_at, updated_at
                FROM hotels
                WHERE user_id = $1
                ORDER BY check_in ASC
                """,
                user_id,
            )
    docs = [_row_to_dict(row, json_fields=("attachments",)) for row in rows]
    return [doc for doc in docs if doc is not None]


async def get_hotel(hotel_id: str) -> dict[str, Any] | None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, trip_id, name, address, check_in, check_out,
                   confirmation_number, notes, attachments, created_at, updated_at
            FROM hotels
            WHERE id = $1
            """,
            hotel_id,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def update_hotel(hotel_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        return await get_hotel(hotel_id)

    assignments: list[str] = []
    values: list[Any] = []
    for column, value in fields.items():
        if column == "attachments":
            index = len(values) + 1
            assignments.append(f"attachments = ${index}::jsonb")
            values.append(json.dumps(value))
        else:
            index = len(values) + 1
            assignments.append(f"{column} = ${index}")
            values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(hotel_id)
    id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE hotels
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${id_index}
            RETURNING id, user_id, trip_id, name, address, check_in, check_out,
                      confirmation_number, notes, attachments, created_at, updated_at
            """,
            *values,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def delete_hotel(hotel_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM hotels WHERE id = $1", hotel_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Transits
# ---------------------------------------------------------------------------


async def create_transit(*, user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    record_id = _new_id()
    attachments = json.dumps(fields.get("attachments", []))
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO transits (
                id, user_id, trip_id, type, from_location, to_location,
                notes, attachments, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $9)
            RETURNING id, user_id, trip_id, type, from_location, to_location,
                      notes, attachments, created_at, updated_at
            """,
            record_id,
            user_id,
            fields.get("trip_id"),
            fields["type"],
            fields.get("from_location", ""),
            fields.get("to_location", ""),
            fields.get("notes", ""),
            attachments,
            now,
        )
    doc = _row_to_dict(row, json_fields=("attachments",))
    if doc is None:
        raise RuntimeError("Failed to create transit")
    return doc


async def list_transits(*, user_id: str, trip_id: str | None = None) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        if trip_id is not None:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, type, from_location, to_location,
                       notes, attachments, created_at, updated_at
                FROM transits
                WHERE user_id = $1 AND trip_id = $2
                ORDER BY created_at ASC
                """,
                user_id,
                trip_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, type, from_location, to_location,
                       notes, attachments, created_at, updated_at
                FROM transits
                WHERE user_id = $1
                ORDER BY created_at ASC
                """,
                user_id,
            )
    docs = [_row_to_dict(row, json_fields=("attachments",)) for row in rows]
    return [doc for doc in docs if doc is not None]


async def get_transit(transit_id: str) -> dict[str, Any] | None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, trip_id, type, from_location, to_location,
                   notes, attachments, created_at, updated_at
            FROM transits
            WHERE id = $1
            """,
            transit_id,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def update_transit(transit_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        return await get_transit(transit_id)

    assignments: list[str] = []
    values: list[Any] = []
    for column, value in fields.items():
        if column == "attachments":
            index = len(values) + 1
            assignments.append(f"attachments = ${index}::jsonb")
            values.append(json.dumps(value))
        else:
            index = len(values) + 1
            assignments.append(f"{column} = ${index}")
            values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(transit_id)
    id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE transits
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${id_index}
            RETURNING id, user_id, trip_id, type, from_location, to_location,
                      notes, attachments, created_at, updated_at
            """,
            *values,
        )
    return _row_to_dict(row, json_fields=("attachments",))


async def delete_transit(transit_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM transits WHERE id = $1", transit_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Schedule items
# ---------------------------------------------------------------------------


async def create_schedule_item(*, user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    record_id = _new_id()
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO schedule_items (
                id, user_id, trip_id, day_date, display_order, item_type, item_id,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
            RETURNING id, user_id, trip_id, day_date, display_order, item_type, item_id,
                      created_at, updated_at
            """,
            record_id,
            user_id,
            fields["trip_id"],
            fields["day_date"],
            fields.get("display_order", 0),
            fields["item_type"],
            fields["item_id"],
            now,
        )
    if row is None:
        raise RuntimeError("Failed to create schedule item")
    return dict(row)


async def list_schedule_items(*, trip_id: str, day_date: Any | None = None) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        if day_date is not None:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, day_date, display_order, item_type, item_id,
                       created_at, updated_at
                FROM schedule_items
                WHERE trip_id = $1 AND day_date = $2
                ORDER BY display_order ASC
                """,
                trip_id,
                day_date,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, user_id, trip_id, day_date, display_order, item_type, item_id,
                       created_at, updated_at
                FROM schedule_items
                WHERE trip_id = $1
                ORDER BY day_date ASC, display_order ASC
                """,
                trip_id,
            )
    return [dict(row) for row in rows]


async def get_schedule_item(item_id: str) -> dict[str, Any] | None:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, trip_id, day_date, display_order, item_type, item_id,
                   created_at, updated_at
            FROM schedule_items
            WHERE id = $1
            """,
            item_id,
        )
    return dict(row) if row is not None else None


async def update_schedule_item(item_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        return await get_schedule_item(item_id)

    assignments: list[str] = []
    values: list[Any] = []
    for index, (column, value) in enumerate(fields.items(), start=1):
        assignments.append(f"{column} = ${index}")
        values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(item_id)
    id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE schedule_items
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${id_index}
            RETURNING id, user_id, trip_id, day_date, display_order, item_type, item_id,
                      created_at, updated_at
            """,
            *values,
        )
    return dict(row) if row is not None else None


async def delete_schedule_item(item_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM schedule_items WHERE id = $1", item_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Custom activity types
# ---------------------------------------------------------------------------


async def create_custom_activity_type(
    *, user_id: str, name: str, icon: str, is_default: bool
) -> dict[str, Any]:
    now = utcnow()
    record_id = _new_id()
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO custom_activity_types (id, user_id, name, icon, is_default, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $6)
            RETURNING id, user_id, name, icon, is_default, created_at, updated_at
            """,
            record_id,
            user_id,
            name,
            icon,
            is_default,
            now,
        )
    if row is None:
        raise RuntimeError("Failed to create custom activity type")
    return dict(row)


async def list_custom_activity_types(user_id: str) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, name, icon, is_default, created_at, updated_at
            FROM custom_activity_types
            WHERE user_id = $1
            ORDER BY created_at ASC
            """,
            user_id,
        )
    return [dict(row) for row in rows]


async def update_custom_activity_type(type_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        pool = _pool_or_raise()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, user_id, name, icon, is_default, created_at, updated_at "
                "FROM custom_activity_types WHERE id = $1",
                type_id,
            )
        return dict(row) if row is not None else None

    assignments: list[str] = []
    values: list[Any] = []
    for index, (column, value) in enumerate(fields.items(), start=1):
        assignments.append(f"{column} = ${index}")
        values.append(value)

    now = utcnow()
    values.append(now)
    updated_at_index = len(values)
    values.append(type_id)
    id_index = len(values)

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE custom_activity_types
            SET {', '.join(assignments)}, updated_at = ${updated_at_index}
            WHERE id = ${id_index}
            RETURNING id, user_id, name, icon, is_default, created_at, updated_at
            """,
            *values,
        )
    return dict(row) if row is not None else None


async def delete_custom_activity_type(type_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM custom_activity_types WHERE id = $1", type_id)
    return result.endswith(" 1")


# ---------------------------------------------------------------------------
# Activity icon overrides
# ---------------------------------------------------------------------------


async def upsert_activity_icon_override(*, user_id: str, activity_type_id: str, icon: str) -> dict[str, Any]:
    now = utcnow()
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO activity_icon_overrides (user_id, activity_type_id, icon, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $4)
            ON CONFLICT (user_id, activity_type_id)
            DO UPDATE
            SET icon = EXCLUDED.icon,
                updated_at = EXCLUDED.updated_at
            RETURNING user_id, activity_type_id, icon, created_at, updated_at
            """,
            user_id,
            activity_type_id,
            icon,
            now,
        )
    if row is None:
        raise RuntimeError("Failed to upsert activity icon override")
    return dict(row)


async def list_activity_icon_overrides(user_id: str) -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id, activity_type_id, icon, created_at, updated_at
            FROM activity_icon_overrides
            WHERE user_id = $1
            ORDER BY activity_type_id ASC
            """,
            user_id,
        )
    return [dict(row) for row in rows]


async def delete_activity_icon_override(*, user_id: str, activity_type_id: str) -> bool:
    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM activity_icon_overrides WHERE user_id = $1 AND activity_type_id = $2",
            user_id,
            activity_type_id,
        )
    return result.endswith(" 1")


async def delete_all_records() -> dict[str, Any]:
    tables = (
        "trip_shares",
        "schedule_items",
        "activities",
        "travels",
        "hotels",
        "transits",
        "custom_activity_types",
        "activity_icon_overrides",
        "trips",
        "users",
        "usage_logs",
        "rate_limit_events",
    )
    counts_by_table: dict[str, int] = {}

    pool = _pool_or_raise()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for table in tables:
                row = await conn.fetchrow(f"SELECT COUNT(*) AS count FROM {table}")
                counts_by_table[table] = int(row["count"]) if row is not None else 0

            await conn.execute(
                """
                TRUNCATE TABLE
                    trip_shares,
                    schedule_items,
                    activities,
                    travels,
                    hotels,
                    transits,
                    custom_activity_types,
                    activity_icon_overrides,
                    trips,
                    users,
                    usage_logs,
                    rate_limit_events
                RESTART IDENTITY CASCADE
                """
            )

    total_deleted = sum(counts_by_table.values())
    return {
        "tables": counts_by_table,
        "total_deleted": total_deleted,
    }
