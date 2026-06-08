from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from datetime import time as time_type
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


Attachment = dict[str, Any]


class TripCreateRequest(BaseModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    trip_name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    start_date: date_type
    end_date: date_type


class TripUpdateRequest(BaseModel):
    trip_name: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date_type | None = None
    end_date: date_type | None = None


class TripRecord(BaseModel):
    id: str
    owner_user_id: str
    trip_name: str
    location: str
    start_date: date_type
    end_date: date_type
    created_at: datetime
    updated_at: datetime


class TripShareCreateRequest(BaseModel):
    trip_id: str = Field(min_length=1, max_length=64)
    shared_with_user_id: str = Field(min_length=1, max_length=128)
    shared_by_user_id: str = Field(min_length=1, max_length=128)
    can_view: bool = True
    can_add: bool = False
    can_delete: bool = False
    can_edit: bool = False
    can_owner: bool = False


class TripShareUpdateRequest(BaseModel):
    can_view: bool | None = None
    can_add: bool | None = None
    can_delete: bool | None = None
    can_edit: bool | None = None
    can_owner: bool | None = None


class TripShareRecord(BaseModel):
    id: int
    trip_id: str
    shared_with_user_id: str
    shared_by_user_id: str
    can_view: bool
    can_add: bool
    can_delete: bool
    can_edit: bool
    can_owner: bool
    created_at: datetime
    updated_at: datetime


class ActivityCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    trip_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=64)
    notes: str = Field(default="", max_length=4000)
    scheduled_day: date_type | None = None
    scheduled_time: time_type | None = None
    time_of_day: Literal["morning", "afternoon", "evening"] | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    custom_type_name: str | None = Field(default=None, max_length=120)
    custom_icon: str | None = Field(default=None, max_length=120)


class ActivityUpdateRequest(BaseModel):
    trip_id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=4000)
    scheduled_day: date_type | None = None
    scheduled_time: time_type | None = None
    time_of_day: Literal["morning", "afternoon", "evening"] | None = None
    attachments: list[Attachment] | None = None
    custom_type_name: str | None = Field(default=None, max_length=120)
    custom_icon: str | None = Field(default=None, max_length=120)


class ActivityRecord(BaseModel):
    id: str
    user_id: str
    trip_id: str | None = None
    name: str
    type: str
    notes: str
    scheduled_day: date_type | None = None
    scheduled_time: time_type | None = None
    time_of_day: Literal["morning", "afternoon", "evening"] | None = None
    attachments: list[Attachment]
    custom_type_name: str | None = None
    custom_icon: str | None = None
    created_at: datetime
    updated_at: datetime


class TravelCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    trip_id: str | None = Field(default=None, max_length=64)
    type: str = Field(min_length=1, max_length=64)
    departure: str = Field(min_length=1, max_length=200)
    arrival: str = Field(min_length=1, max_length=200)
    date: date_type
    time: time_type
    confirmation_number: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=4000)
    attachments: list[Attachment] = Field(default_factory=list)


class TravelUpdateRequest(BaseModel):
    trip_id: str | None = Field(default=None, max_length=64)
    type: str | None = Field(default=None, min_length=1, max_length=64)
    departure: str | None = Field(default=None, min_length=1, max_length=200)
    arrival: str | None = Field(default=None, min_length=1, max_length=200)
    date: date_type | None = None
    time: time_type | None = None
    confirmation_number: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    attachments: list[Attachment] | None = None


class TravelRecord(BaseModel):
    id: str
    user_id: str
    trip_id: str | None = None
    type: str
    departure: str
    arrival: str
    date: date_type
    time: time_type
    confirmation_number: str
    notes: str
    attachments: list[Attachment]
    created_at: datetime
    updated_at: datetime


class HotelCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    trip_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=400)
    check_in: date_type
    check_out: date_type
    confirmation_number: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=4000)
    attachments: list[Attachment] = Field(default_factory=list)


class HotelUpdateRequest(BaseModel):
    trip_id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, min_length=1, max_length=400)
    check_in: date_type | None = None
    check_out: date_type | None = None
    confirmation_number: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    attachments: list[Attachment] | None = None


class HotelRecord(BaseModel):
    id: str
    user_id: str
    trip_id: str | None = None
    name: str
    address: str
    check_in: date_type
    check_out: date_type
    confirmation_number: str
    notes: str
    attachments: list[Attachment]
    created_at: datetime
    updated_at: datetime


class TransitCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    trip_id: str | None = Field(default=None, max_length=64)
    type: str = Field(min_length=1, max_length=64)
    from_location: str = Field(default="", max_length=200)
    to_location: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=4000)
    attachments: list[Attachment] = Field(default_factory=list)


class TransitUpdateRequest(BaseModel):
    trip_id: str | None = Field(default=None, max_length=64)
    type: str | None = Field(default=None, min_length=1, max_length=64)
    from_location: str | None = Field(default=None, max_length=200)
    to_location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    attachments: list[Attachment] | None = None


class TransitRecord(BaseModel):
    id: str
    user_id: str
    trip_id: str | None = None
    type: str
    from_location: str
    to_location: str
    notes: str
    attachments: list[Attachment]
    created_at: datetime
    updated_at: datetime


class ScheduleItemCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    trip_id: str = Field(min_length=1, max_length=64)
    day_date: date_type
    display_order: int = Field(default=0, ge=0)
    item_type: Literal["activity", "travel", "hotel", "transit"]
    item_id: str = Field(min_length=1, max_length=64)


class ScheduleItemUpdateRequest(BaseModel):
    day_date: date_type | None = None
    display_order: int | None = Field(default=None, ge=0)
    item_type: Literal["activity", "travel", "hotel", "transit"] | None = None
    item_id: str | None = Field(default=None, min_length=1, max_length=64)


class ScheduleItemRecord(BaseModel):
    id: str
    user_id: str
    trip_id: str
    day_date: date_type
    display_order: int
    item_type: Literal["activity", "travel", "hotel", "transit"]
    item_id: str
    created_at: datetime
    updated_at: datetime


class CustomActivityTypeCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    icon: str = Field(min_length=1, max_length=120)
    is_default: bool = False


class CustomActivityTypeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, min_length=1, max_length=120)
    is_default: bool | None = None


class CustomActivityTypeRecord(BaseModel):
    id: str
    user_id: str
    name: str
    icon: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ActivityIconOverrideUpsertRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    activity_type_id: str = Field(min_length=1, max_length=120)
    icon: str = Field(min_length=1, max_length=120)


class ActivityIconOverrideRecord(BaseModel):
    user_id: str
    activity_type_id: str
    icon: str
    created_at: datetime
    updated_at: datetime
