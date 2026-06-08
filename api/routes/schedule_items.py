from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from services.auth import get_current_user_id
from services.models import ScheduleItemCreateRequest, ScheduleItemRecord, ScheduleItemUpdateRequest
from services.postgres import (
    create_schedule_item,
    delete_schedule_item,
    get_schedule_item,
    list_schedule_items,
    update_schedule_item,
)
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/schedule-items", tags=["schedule-items"])


@router.post("", response_model=ScheduleItemRecord)
async def create_schedule_item_route(
    payload: ScheduleItemCreateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> ScheduleItemRecord:
    await enforce_rate_limit(request=request, endpoint="/api/schedule-items", user_id=user_id)
    fields = payload.model_dump()
    doc = await create_schedule_item(user_id=user_id, fields=fields)
    return ScheduleItemRecord(**doc)


@router.get("", response_model=list[ScheduleItemRecord])
async def list_schedule_items_route(
    request: Request, trip_id: str, day_date: date | None = None, user_id: str = Depends(get_current_user_id)
) -> list[ScheduleItemRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/schedule-items", user_id=user_id)
    docs = await list_schedule_items(trip_id=trip_id, day_date=day_date)
    return [ScheduleItemRecord(**doc) for doc in docs]


@router.get("/{item_id}", response_model=ScheduleItemRecord)
async def get_schedule_item_route(
    item_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> ScheduleItemRecord:
    await enforce_rate_limit(request=request, endpoint="/api/schedule-items/{item_id}", user_id=user_id)
    doc = await get_schedule_item(item_id)
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    return ScheduleItemRecord(**doc)


@router.patch("/{item_id}", response_model=ScheduleItemRecord)
async def update_schedule_item_route(
    item_id: str, payload: ScheduleItemUpdateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> ScheduleItemRecord:
    await enforce_rate_limit(request=request, endpoint="/api/schedule-items/{item_id}", user_id=user_id)
    existing = await get_schedule_item(item_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_schedule_item(item_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    return ScheduleItemRecord(**doc)


@router.delete("/{item_id}")
async def delete_schedule_item_route(
    item_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/schedule-items/{item_id}", user_id=user_id)
    existing = await get_schedule_item(item_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    deleted = await delete_schedule_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    return {"deleted": True}
