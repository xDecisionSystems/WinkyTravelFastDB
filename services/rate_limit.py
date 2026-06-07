from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, Request

from config.settings import settings
from services.mongo import count_rate_limit_events, insert_rate_limit_event, utcnow


def _client_ip(request: Request) -> str:
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


async def _enforce_subject_limit(
    *,
    subject_type: str,
    subject_key: str,
    endpoint: str,
    client_ip: str,
    user_id: str | None,
) -> None:
    windows = (
        ("second", 1, settings.rate_limit_per_second),
        ("hour", 3600, settings.rate_limit_per_hour),
        ("day", 86400, settings.rate_limit_per_day),
    )
    now = utcnow()

    for window_name, window_seconds, window_limit in windows:
        since = now - timedelta(seconds=window_seconds)
        request_count = await count_rate_limit_events(subject_type, subject_key, since)
        if request_count >= window_limit:
            reason = f"{window_name}_limit_exceeded"
            await insert_rate_limit_event(
                subject_type=subject_type,
                subject_key=subject_key,
                endpoint=endpoint,
                client_ip=client_ip,
                user_id=user_id,
                allowed=False,
                reason=reason,
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({window_name}); please retry later.",
            )

    await insert_rate_limit_event(
        subject_type=subject_type,
        subject_key=subject_key,
        endpoint=endpoint,
        client_ip=client_ip,
        user_id=user_id,
        allowed=True,
    )


async def enforce_rate_limit(
    *,
    request: Request,
    endpoint: str,
    user_id: str | None = None,
) -> None:
    client_ip = _client_ip(request)
    normalized_user_id = user_id.strip() if user_id else None

    # Always enforce by client IP so anonymous routes are protected too.
    await _enforce_subject_limit(
        subject_type="ip",
        subject_key=client_ip,
        endpoint=endpoint,
        client_ip=client_ip,
        user_id=normalized_user_id,
    )

    if normalized_user_id is None:
        return

    # Also enforce by user ID when known to track per-user abuse.
    await _enforce_subject_limit(
        subject_type="user_id",
        subject_key=normalized_user_id,
        endpoint=endpoint,
        client_ip=client_ip,
        user_id=normalized_user_id,
    )
