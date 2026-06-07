from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserUpsertRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=320)
    name: str | None = Field(default=None, max_length=160)


class UserCreateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    name: str | None = Field(default=None, max_length=160)


class UserRecord(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    created_at: datetime
    updated_at: datetime


class PlaceAutocompleteRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    input: str = Field(min_length=1, max_length=256)
    session_token: str | None = Field(default=None, max_length=128)
    language_code: str | None = Field(default=None, max_length=12)
    region_code: str | None = Field(default=None, max_length=12)


class PlaceDetailsRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    place_id: str = Field(min_length=1, max_length=256)
    session_token: str | None = Field(default=None, max_length=128)
    language_code: str | None = Field(default=None, max_length=12)


class UsageLog(BaseModel):
    user_id: str
    endpoint: Literal["places_autocomplete", "place_details"]
    provider: Literal["google_places"] = "google_places"
    request_summary: dict[str, Any]
    status_code: int
    created_at: datetime = Field(default_factory=utcnow)
