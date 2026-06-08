from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request

from config.settings import settings
from services.auth import (
    AuthError,
    get_current_user_id,
    issue_session_jwt,
    verify_google_id_token,
)
from services.models import (
    AuthResponse,
    DevLoginRequest,
    GoogleLoginRequest,
    UserRecord,
)
from services.postgres import get_user, upsert_dev_user, upsert_user_by_google_sub
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/google", response_model=AuthResponse)
async def google_login_route(payload: GoogleLoginRequest, request: Request) -> AuthResponse:
    await enforce_rate_limit(request=request, endpoint="/api/auth/google", user_id=None)
    try:
        profile = verify_google_id_token(payload.id_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    doc = await upsert_user_by_google_sub(google_sub=profile.sub, email=profile.email, name=profile.name)
    user = UserRecord(**doc)
    return AuthResponse(token=issue_session_jwt(user.user_id), user=user)


@router.post("/dev-login", response_model=AuthResponse)
async def dev_login_route(payload: DevLoginRequest, request: Request) -> AuthResponse:
    if not settings.dev_login_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    await enforce_rate_limit(request=request, endpoint="/api/auth/dev-login", user_id=None)

    if not settings.dev_login_master_key or not hmac.compare_digest(payload.master_key, settings.dev_login_master_key):
        raise HTTPException(status_code=401, detail="Invalid master key")

    email = payload.email or "dev@winkytravel.local"
    user_id = "dev:" + hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]
    doc = await upsert_dev_user(user_id=user_id, email=email, name=payload.name or "Dev User")
    user = UserRecord(**doc)
    return AuthResponse(token=issue_session_jwt(user.user_id), user=user)


@router.get("/me", response_model=UserRecord)
async def get_current_user_route(request: Request, user_id: str = Depends(get_current_user_id)) -> UserRecord:
    await enforce_rate_limit(request=request, endpoint="/api/auth/me", user_id=user_id)
    doc = await get_user(user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRecord(**doc)
