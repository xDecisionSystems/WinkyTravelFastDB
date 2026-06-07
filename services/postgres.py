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
            vacation_name TEXT NOT NULL,
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
