from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from config.settings import settings


_JWT_ALGORITHM = "HS256"
_google_request = google_requests.Request()


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str | None
    name: str | None


class AuthError(Exception):
    """Raised when a credential cannot be verified or decoded."""


def verify_google_id_token(token: str) -> GoogleProfile:
    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            _google_request,
            settings.google_client_id,
        )
    except (ValueError, GoogleAuthError) as exc:
        raise AuthError("Invalid Google ID token") from exc

    sub = claims.get("sub")
    if not sub:
        raise AuthError("Google ID token missing subject claim")

    return GoogleProfile(sub=str(sub), email=claims.get("email"), name=claims.get("name"))


def issue_session_jwt(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_JWT_ALGORITHM)


def decode_session_jwt(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired session token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Session token missing subject claim")
    return str(user_id)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Missing bearer token")
    return token


async def get_current_user_id(request: Request) -> str:
    try:
        token = _bearer_token(request)
        return decode_session_jwt(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
