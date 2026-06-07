from fastapi import APIRouter, HTTPException, Request

from services.models import TravelCreateRequest, TravelRecord, TravelUpdateRequest
from services.postgres import create_travel, delete_travel, get_travel, list_travels, update_travel
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/travels", tags=["travels"])


@router.post("", response_model=TravelRecord)
async def create_travel_route(payload: TravelCreateRequest, request: Request) -> TravelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/travels", user_id=payload.user_id)
    fields = payload.model_dump(exclude={"user_id"})
    doc = await create_travel(user_id=payload.user_id, fields=fields)
    return TravelRecord(**doc)


@router.get("", response_model=list[TravelRecord])
async def list_travels_route(request: Request, user_id: str, trip_id: str | None = None) -> list[TravelRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/travels", user_id=user_id)
    docs = await list_travels(user_id=user_id, trip_id=trip_id)
    return [TravelRecord(**doc) for doc in docs]


@router.get("/{travel_id}", response_model=TravelRecord)
async def get_travel_route(travel_id: str, request: Request) -> TravelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/travels/{travel_id}", user_id=None)
    doc = await get_travel(travel_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Travel not found")
    return TravelRecord(**doc)


@router.patch("/{travel_id}", response_model=TravelRecord)
async def update_travel_route(travel_id: str, payload: TravelUpdateRequest, request: Request) -> TravelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/travels/{travel_id}", user_id=None)
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_travel(travel_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Travel not found")
    return TravelRecord(**doc)


@router.delete("/{travel_id}")
async def delete_travel_route(travel_id: str, request: Request) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/travels/{travel_id}", user_id=None)
    deleted = await delete_travel(travel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Travel not found")
    return {"deleted": True}
