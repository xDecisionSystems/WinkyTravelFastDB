from fastapi import APIRouter, HTTPException, Request

from services.models import HotelCreateRequest, HotelRecord, HotelUpdateRequest
from services.postgres import create_hotel, delete_hotel, get_hotel, list_hotels, update_hotel
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/hotels", tags=["hotels"])


@router.post("", response_model=HotelRecord)
async def create_hotel_route(payload: HotelCreateRequest, request: Request) -> HotelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/hotels", user_id=payload.user_id)
    fields = payload.model_dump(exclude={"user_id"})
    doc = await create_hotel(user_id=payload.user_id, fields=fields)
    return HotelRecord(**doc)


@router.get("", response_model=list[HotelRecord])
async def list_hotels_route(request: Request, user_id: str, trip_id: str | None = None) -> list[HotelRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/hotels", user_id=user_id)
    docs = await list_hotels(user_id=user_id, trip_id=trip_id)
    return [HotelRecord(**doc) for doc in docs]


@router.get("/{hotel_id}", response_model=HotelRecord)
async def get_hotel_route(hotel_id: str, request: Request) -> HotelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/hotels/{hotel_id}", user_id=None)
    doc = await get_hotel(hotel_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return HotelRecord(**doc)


@router.patch("/{hotel_id}", response_model=HotelRecord)
async def update_hotel_route(hotel_id: str, payload: HotelUpdateRequest, request: Request) -> HotelRecord:
    await enforce_rate_limit(request=request, endpoint="/api/hotels/{hotel_id}", user_id=None)
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_hotel(hotel_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return HotelRecord(**doc)


@router.delete("/{hotel_id}")
async def delete_hotel_route(hotel_id: str, request: Request) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/hotels/{hotel_id}", user_id=None)
    deleted = await delete_hotel(hotel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return {"deleted": True}
