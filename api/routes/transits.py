from fastapi import APIRouter, Depends, HTTPException, Request

from services.auth import get_current_user_id
from services.models import TransitCreateRequest, TransitRecord, TransitUpdateRequest
from services.postgres import create_transit, delete_transit, get_transit, list_transits, update_transit
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/transits", tags=["transits"])


@router.post("", response_model=TransitRecord)
async def create_transit_route(
    payload: TransitCreateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> TransitRecord:
    await enforce_rate_limit(request=request, endpoint="/api/transits", user_id=user_id)
    fields = payload.model_dump()
    doc = await create_transit(user_id=user_id, fields=fields)
    return TransitRecord(**doc)


@router.get("", response_model=list[TransitRecord])
async def list_transits_route(
    request: Request, user_id: str = Depends(get_current_user_id), trip_id: str | None = None
) -> list[TransitRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/transits", user_id=user_id)
    docs = await list_transits(user_id=user_id, trip_id=trip_id)
    return [TransitRecord(**doc) for doc in docs]


@router.get("/{transit_id}", response_model=TransitRecord)
async def get_transit_route(
    transit_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> TransitRecord:
    await enforce_rate_limit(request=request, endpoint="/api/transits/{transit_id}", user_id=user_id)
    doc = await get_transit(transit_id)
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Transit not found")
    return TransitRecord(**doc)


@router.patch("/{transit_id}", response_model=TransitRecord)
async def update_transit_route(
    transit_id: str, payload: TransitUpdateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> TransitRecord:
    await enforce_rate_limit(request=request, endpoint="/api/transits/{transit_id}", user_id=user_id)
    existing = await get_transit(transit_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Transit not found")
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_transit(transit_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Transit not found")
    return TransitRecord(**doc)


@router.delete("/{transit_id}")
async def delete_transit_route(
    transit_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/transits/{transit_id}", user_id=user_id)
    existing = await get_transit(transit_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Transit not found")
    deleted = await delete_transit(transit_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transit not found")
    return {"deleted": True}
