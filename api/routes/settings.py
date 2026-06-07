from fastapi import APIRouter, HTTPException, Request

from services.models import (
    ActivityIconOverrideRecord,
    ActivityIconOverrideUpsertRequest,
    CustomActivityTypeCreateRequest,
    CustomActivityTypeRecord,
    CustomActivityTypeUpdateRequest,
)
from services.postgres import (
    create_custom_activity_type,
    delete_activity_icon_override,
    delete_custom_activity_type,
    list_activity_icon_overrides,
    list_custom_activity_types,
    update_custom_activity_type,
    upsert_activity_icon_override,
)
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.post("/custom-activity-types", response_model=CustomActivityTypeRecord)
async def create_custom_activity_type_route(
    payload: CustomActivityTypeCreateRequest, request: Request
) -> CustomActivityTypeRecord:
    await enforce_rate_limit(request=request, endpoint="/api/settings/custom-activity-types", user_id=payload.user_id)
    doc = await create_custom_activity_type(
        user_id=payload.user_id,
        name=payload.name,
        icon=payload.icon,
        is_default=payload.is_default,
    )
    return CustomActivityTypeRecord(**doc)


@router.get("/custom-activity-types", response_model=list[CustomActivityTypeRecord])
async def list_custom_activity_types_route(request: Request, user_id: str) -> list[CustomActivityTypeRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/settings/custom-activity-types", user_id=user_id)
    docs = await list_custom_activity_types(user_id)
    return [CustomActivityTypeRecord(**doc) for doc in docs]


@router.patch("/custom-activity-types/{type_id}", response_model=CustomActivityTypeRecord)
async def update_custom_activity_type_route(
    type_id: str, payload: CustomActivityTypeUpdateRequest, request: Request
) -> CustomActivityTypeRecord:
    await enforce_rate_limit(request=request, endpoint="/api/settings/custom-activity-types/{type_id}", user_id=None)
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_custom_activity_type(type_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Custom activity type not found")
    return CustomActivityTypeRecord(**doc)


@router.delete("/custom-activity-types/{type_id}")
async def delete_custom_activity_type_route(type_id: str, request: Request) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/settings/custom-activity-types/{type_id}", user_id=None)
    deleted = await delete_custom_activity_type(type_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Custom activity type not found")
    return {"deleted": True}


@router.put("/icon-overrides", response_model=ActivityIconOverrideRecord)
async def upsert_activity_icon_override_route(
    payload: ActivityIconOverrideUpsertRequest, request: Request
) -> ActivityIconOverrideRecord:
    await enforce_rate_limit(request=request, endpoint="/api/settings/icon-overrides", user_id=payload.user_id)
    doc = await upsert_activity_icon_override(
        user_id=payload.user_id,
        activity_type_id=payload.activity_type_id,
        icon=payload.icon,
    )
    return ActivityIconOverrideRecord(**doc)


@router.get("/icon-overrides", response_model=list[ActivityIconOverrideRecord])
async def list_activity_icon_overrides_route(request: Request, user_id: str) -> list[ActivityIconOverrideRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/settings/icon-overrides", user_id=user_id)
    docs = await list_activity_icon_overrides(user_id)
    return [ActivityIconOverrideRecord(**doc) for doc in docs]


@router.delete("/icon-overrides/{activity_type_id}")
async def delete_activity_icon_override_route(activity_type_id: str, user_id: str, request: Request) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/settings/icon-overrides/{activity_type_id}", user_id=user_id)
    deleted = await delete_activity_icon_override(user_id=user_id, activity_type_id=activity_type_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Activity icon override not found")
    return {"deleted": True}
