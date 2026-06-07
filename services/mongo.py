from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config.settings import settings


_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def connect() -> None:
    global _client, _db
    if _client is not None:
        return

    _client = AsyncIOMotorClient(settings.mongo_uri)
    _db = _client[settings.mongo_db]

    await _db.users.create_index("user_id", unique=True)
    await _db.usage_logs.create_index([("user_id", 1), ("created_at", -1)])
    await _db.usage_logs.create_index([("endpoint", 1), ("created_at", -1)])
    await _db.rate_limit_events.create_index(
        [("subject_type", 1), ("subject_key", 1), ("allowed", 1), ("created_at", -1)]
    )
    await _db.rate_limit_events.create_index(
        "created_at",
        expireAfterSeconds=settings.rate_limit_retention_hours * 3600,
    )


async def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB is not connected")
    return _db


async def upsert_user(user_id: str, email: str | None, name: str | None) -> dict[str, Any]:
    database = db()
    now = utcnow()

    set_payload: dict[str, Any] = {"updated_at": now}
    if email is not None:
        set_payload["email"] = email
    if name is not None:
        set_payload["name"] = name

    await database.users.update_one(
        {"user_id": user_id},
        {
            "$set": set_payload,
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": now,
            },
        },
        upsert=True,
    )

    doc = await database.users.find_one({"user_id": user_id}, {"_id": 0})
    if doc is None:
        raise RuntimeError("Failed to load user after upsert")
    return doc


async def get_user(user_id: str) -> dict[str, Any] | None:
    database = db()
    return await database.users.find_one({"user_id": user_id}, {"_id": 0})


async def insert_usage_log(
    user_id: str,
    endpoint: str,
    status_code: int,
    request_summary: dict[str, Any],
) -> None:
    database = db()
    await database.usage_logs.insert_one(
        {
            "user_id": user_id,
            "endpoint": endpoint,
            "provider": "google_places",
            "status_code": status_code,
            "request_summary": request_summary,
            "created_at": utcnow(),
        }
    )


async def count_rate_limit_events(
    subject_type: str,
    subject_key: str,
    since: datetime,
) -> int:
    database = db()
    return await database.rate_limit_events.count_documents(
        {
            "subject_type": subject_type,
            "subject_key": subject_key,
            "allowed": True,
            "created_at": {"$gte": since},
        }
    )


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
    database = db()
    await database.rate_limit_events.insert_one(
        {
            "subject_type": subject_type,
            "subject_key": subject_key,
            "endpoint": endpoint,
            "client_ip": client_ip,
            "user_id": user_id,
            "allowed": allowed,
            "reason": reason,
            "created_at": utcnow(),
        }
    )
