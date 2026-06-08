from fastapi import APIRouter, Depends, HTTPException, Request

from services.auth import get_current_user_id
from services.models import TravelCreateRequest, TravelRecord, TravelUpdateRequest
from services.postgres import create_travel, delete_travel, get_travel, list_travels, update_travel
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/travels", tags=["travels"])


@router.post("", response_model=TravelRecord)
async def create_travel_route(
    payload: TravelCreateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> TravelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/travels", user_id=user_id)
    fields = payload.model_dump()
    doc = await create_travel(user_id=user_id, fields=fields)
    return TravelRecord(**doc)


@router.get("", response_model=list[TravelRecord])
async def list_travels_route(
    request: Request, user_id: str = Depends(get_current_user_id), trip_id: str | None = None
) -> list[TravelRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/travels", user_id=user_id)
    docs = await list_travels(user_id=user_id, trip_id=trip_id)
    return [TravelRecord(**doc) for doc in docs]


@router.get("/{travel_id}", response_model=TravelRecord)
async def get_travel_route(
    travel_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> TravelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/travels/{travel_id}", user_id=user_id)
    doc = await get_travel(travel_id)
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Travel not found")
    return TravelRecord(**doc)


@router.patch("/{travel_id}", response_model=TravelRecord)
async def update_travel_route(
    travel_id: str, payload: TravelUpdateRequest, request: Request, user_id: str = Depends(get_current_user_id)
) -> TravelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/travels/{travel_id}", user_id=user_id)
    existing = await get_travel(travel_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Travel not found")
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_travel(travel_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Travel not found")
    return TravelRecord(**doc)


@router.delete("/{travel_id}")
async def delete_travel_route(
    travel_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/travels/{travel_id}", user_id=user_id)
    existing = await get_travel(travel_id)
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Travel not found")
    deleted = await delete_travel(travel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Travel not found")
    return {"deleted": True}
