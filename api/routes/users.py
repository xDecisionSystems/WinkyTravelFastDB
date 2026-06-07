from fastapi import APIRouter, HTTPException, Request

from services.models import UserRecord, UserUpsertRequest
from services.postgres import get_user, upsert_user
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/upsert", response_model=UserRecord)
async def upsert_user_route(payload: UserUpsertRequest, request: Request) -> UserRecord:
    await enforce_rate_limit(
        request=request,
        endpoint="/api/users/upsert",
        user_id=payload.user_id,
    )
    doc = await upsert_user(
        user_id=payload.user_id,
        email=payload.email,
        name=payload.name,
    )
    return UserRecord(**doc)


@router.get("/{user_id}", response_model=UserRecord)
async def get_user_route(user_id: str, request: Request) -> UserRecord:
    await enforce_rate_limit(
        request=request,
        endpoint="/api/users/{user_id}",
        user_id=user_id,
    )
    doc = await get_user(user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRecord(**doc)
