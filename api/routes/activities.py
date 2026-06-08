from fastapi import APIRouter, Depends, HTTPException, Request

from services.auth import get_current_user_id
from services.models import ActivityCreateRequest, ActivityRecord, ActivityUpdateRequest
from services.postgres import create_activity, delete_activity, get_activity, list_activities, update_activity
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.post("", response_model=ActivityRecord)
async def create_activity_route(
    payload: ActivityCreateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> ActivityRecord:
    await enforce_rate_limit(request=request, endpoint="/api/activities", user_id=user_id)
    fields = payload.model_dump()
    doc = await create_activity(user_id=user_id, fields=fields)
    return ActivityRecord(**doc)


@router.get("", response_model=list[ActivityRecord])
async def list_activities_route(
    request: Request, user_id: str = Depends(get_current_user_id), trip_id: str | None = None
) -> list[ActivityRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/activities", user_id=user_id)
    docs = await list_activities(user_id=user_id, trip_id=trip_id)
    return [ActivityRecord(**doc) for doc in docs]


@router.get("/{activity_id}", response_model=ActivityRecord)
async def get_activity_route(
    activity_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> ActivityRecord:
    await enforce_rate_limit(request=request, endpoint="/api/activities/{activity_id}", user_id=user_id)
    doc = await get_activity(activity_id)
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Activity not found")
    return ActivityRecord(**doc)


@router.patch("/{activity_id}", response_model=ActivityRecord)
async def update_activity_route(
    activity_id: str, payload: ActivityUpdateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> ActivityRecord:
    await enforce_rate_limit(request=request, endpoint="/api/activities/{activity_id}", user_id=user_id)
    existing = await get_activity(activity_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Activity not found")
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_activity(activity_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return ActivityRecord(**doc)


@router.delete("/{activity_id}")
async def delete_activity_route(
    activity_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/activities/{activity_id}", user_id=user_id)
    existing = await get_activity(activity_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Activity not found")
    deleted = await delete_activity(activity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"deleted": True}
