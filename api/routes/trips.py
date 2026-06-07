from fastapi import APIRouter, HTTPException, Request

from services.models import (
    TripCreateRequest,
    TripRecord,
    TripShareCreateRequest,
    TripShareRecord,
    TripShareUpdateRequest,
    TripUpdateRequest,
)
from services.postgres import (
    create_trip,
    create_trip_share,
    delete_trip,
    delete_trip_share,
    get_trip,
    list_trip_shares,
    list_trips,
    update_trip,
    update_trip_share,
)
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.post("", response_model=TripRecord)
async def create_trip_route(payload: TripCreateRequest, request: Request) -> TripRecord:
    await enforce_rate_limit(request=request, endpoint="/api/trips", user_id=payload.owner_user_id)
    doc = await create_trip(
        owner_user_id=payload.owner_user_id,
        vacation_name=payload.vacation_name,
        location=payload.location,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return TripRecord(**doc)


@router.get("", response_model=list[TripRecord])
async def list_trips_route(owner_user_id: str, request: Request) -> list[TripRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/trips", user_id=owner_user_id)
    docs = await list_trips(owner_user_id)
    return [TripRecord(**doc) for doc in docs]


@router.get("/{trip_id}", response_model=TripRecord)
async def get_trip_route(trip_id: str, request: Request) -> TripRecord:
    await enforce_rate_limit(request=request, endpoint="/api/trips/{trip_id}", user_id=None)
    doc = await get_trip(trip_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return TripRecord(**doc)


@router.patch("/{trip_id}", response_model=TripRecord)
async def update_trip_route(trip_id: str, payload: TripUpdateRequest, request: Request) -> TripRecord:
    await enforce_rate_limit(request=request, endpoint="/api/trips/{trip_id}", user_id=None)
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_trip(trip_id, fields)
    if doc is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return TripRecord(**doc)


@router.delete("/{trip_id}")
async def delete_trip_route(trip_id: str, request: Request) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/trips/{trip_id}", user_id=None)
    deleted = await delete_trip(trip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {"deleted": True}


@router.post("/{trip_id}/shares", response_model=TripShareRecord)
async def create_trip_share_route(
    trip_id: str, payload: TripShareCreateRequest, request: Request
) -> TripShareRecord:
    await enforce_rate_limit(request=request, endpoint="/api/trips/{trip_id}/shares", user_id=payload.shared_by_user_id)
    if payload.trip_id != trip_id:
        raise HTTPException(status_code=400, detail="trip_id in path and body must match")
    doc = await create_trip_share(
        trip_id=payload.trip_id,
        shared_with_user_id=payload.shared_with_user_id,
        shared_by_user_id=payload.shared_by_user_id,
        can_view=payload.can_view,
        can_add=payload.can_add,
        can_delete=payload.can_delete,
        can_edit=payload.can_edit,
        can_owner=payload.can_owner,
    )
    return TripShareRecord(**doc)


@router.get("/{trip_id}/shares", response_model=list[TripShareRecord])
async def list_trip_shares_route(trip_id: str, request: Request) -> list[TripShareRecord]:
    await enforce_rate_limit(request=request, endpoint="/api/trips/{trip_id}/shares", user_id=None)
    docs = await list_trip_shares(trip_id)
    return [TripShareRecord(**doc) for doc in docs]


@router.patch("/{trip_id}/shares/{share_id}", response_model=TripShareRecord)
async def update_trip_share_route(
    trip_id: str, share_id: int, payload: TripShareUpdateRequest, request: Request
) -> TripShareRecord:
    await enforce_rate_limit(request=request, endpoint="/api/trips/{trip_id}/shares/{share_id}", user_id=None)
    fields = payload.model_dump(exclude_unset=True)
    doc = await update_trip_share(share_id, fields)
    if doc is None or doc["trip_id"] != trip_id:
        raise HTTPException(status_code=404, detail="Trip share not found")
    return TripShareRecord(**doc)


@router.delete("/{trip_id}/shares/{share_id}")
async def delete_trip_share_route(trip_id: str, share_id: int, request: Request) -> dict[str, bool]:
    await enforce_rate_limit(request=request, endpoint="/api/trips/{trip_id}/shares/{share_id}", user_id=None)
    deleted = await delete_trip_share(share_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trip share not found")
    return {"deleted": True}
