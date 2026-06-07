from __future__ import annotations

import os
import sys
import types
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Lightweight stubs so tests can run even before project deps are installed.
try:
    from fastapi import HTTPException
except ModuleNotFoundError:
    fastapi_stub = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: object) -> None:
            super().__init__(str(detail))
            self.status_code = status_code
            self.detail = detail

    class Request:
        pass

    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Request = Request
    sys.modules["fastapi"] = fastapi_stub

if "dotenv" not in sys.modules:
    try:
        import dotenv  # noqa: F401
    except ModuleNotFoundError:
        dotenv_stub = types.ModuleType("dotenv")

        def load_dotenv(*_args: object, **_kwargs: object) -> bool:
            return False

        dotenv_stub.load_dotenv = load_dotenv
        sys.modules["dotenv"] = dotenv_stub

if "asyncpg" not in sys.modules:
    try:
        import asyncpg  # noqa: F401
    except ModuleNotFoundError:
        asyncpg_stub = types.ModuleType("asyncpg")

        class Pool:
            async def acquire(self) -> object:
                raise RuntimeError("stub pool has no connections")

        class Connection:
            pass

        async def create_pool(*_args: object, **_kwargs: object) -> Pool:
            return Pool()

        asyncpg_stub.Pool = Pool
        asyncpg_stub.Connection = Connection
        asyncpg_stub.create_pool = create_pool
        sys.modules["asyncpg"] = asyncpg_stub

# Ensure required settings vars exist before importing app modules.
os.environ.setdefault("DATABASE_URL", "postgresql://winky:test@127.0.0.1:5432/winky_travel_test")

from services.rate_limit import enforce_rate_limit


class RateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_request_when_under_limits(self) -> None:
        request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"))
        fake_settings = SimpleNamespace(
            rate_limit_per_second=5,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
        )

        with (
            patch("services.rate_limit.settings", fake_settings),
            patch("services.rate_limit.utcnow", return_value=datetime.now(timezone.utc)),
            patch("services.rate_limit.count_rate_limit_events", AsyncMock(return_value=0)),
            patch("services.rate_limit.insert_rate_limit_event", AsyncMock()) as log_event,
        ):
            await enforce_rate_limit(
                request=request,
                endpoint="/api/users/upsert",
                user_id="user-123",
            )

        # One allowed event for IP, one for user_id.
        self.assertEqual(log_event.await_count, 2)
        ip_call = log_event.await_args_list[0].kwargs
        user_call = log_event.await_args_list[1].kwargs
        self.assertEqual(ip_call["subject_type"], "ip")
        self.assertEqual(user_call["subject_type"], "user_id")

    async def test_blocks_when_hour_limit_is_hit(self) -> None:
        request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.2"))
        fake_settings = SimpleNamespace(
            rate_limit_per_second=5,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
        )

        # Counts are checked in order: second, hour, day.
        # Return hour count at limit to force a block.
        with (
            patch("services.rate_limit.settings", fake_settings),
            patch("services.rate_limit.utcnow", return_value=datetime.now(timezone.utc)),
            patch(
                "services.rate_limit.count_rate_limit_events",
                AsyncMock(side_effect=[0, 1000]),
            ),
            patch("services.rate_limit.insert_rate_limit_event", AsyncMock()) as log_event,
        ):
            with self.assertRaises(HTTPException) as exc:
                await enforce_rate_limit(
                    request=request,
                    endpoint="/api/places/autocomplete",
                    user_id="user-999",
                )

        self.assertEqual(exc.exception.status_code, 429)
        self.assertIn("hour", str(exc.exception.detail))
        blocked_call = log_event.await_args_list[0].kwargs
        self.assertFalse(blocked_call["allowed"])
        self.assertEqual(blocked_call["reason"], "hour_limit_exceeded")

    async def test_anonymous_request_only_checks_ip(self) -> None:
        request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.3"))
        fake_settings = SimpleNamespace(
            rate_limit_per_second=5,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
        )

        with (
            patch("services.rate_limit.settings", fake_settings),
            patch("services.rate_limit.utcnow", return_value=datetime.now(timezone.utc)),
            patch("services.rate_limit.count_rate_limit_events", AsyncMock(return_value=0)),
            patch("services.rate_limit.insert_rate_limit_event", AsyncMock()) as log_event,
        ):
            await enforce_rate_limit(
                request=request,
                endpoint="/health",
            )

        self.assertEqual(log_event.await_count, 1)
        only_call = log_event.await_args_list[0].kwargs
        self.assertEqual(only_call["subject_type"], "ip")
        self.assertIsNone(only_call["user_id"])


if __name__ == "__main__":
    unittest.main()
