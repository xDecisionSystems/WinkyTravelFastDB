from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from config.settings import settings
from services.models import PlaceAutocompleteRequest, PlaceDetailsRequest
from services.postgres import insert_usage_log
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/places", tags=["places"])


def _ensure_google_key() -> str:
    api_key = settings.google_maps_api_key.strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Google Places API key is not configured on the server",
        )
    return api_key


@router.post("/autocomplete")
async def autocomplete(payload: PlaceAutocompleteRequest, request: Request) -> dict[str, Any]:
    await enforce_rate_limit(
        request=request,
        endpoint="/api/places/autocomplete",
        user_id=payload.user_id,
    )
    api_key = _ensure_google_key()

    request_body: dict[str, Any] = {
        "input": payload.input,
    }
    if payload.session_token:
        request_body["sessionToken"] = payload.session_token
    if payload.language_code:
        request_body["languageCode"] = payload.language_code
    if payload.region_code:
        request_body["regionCode"] = payload.region_code

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "suggestions.placePrediction.placeId,"
            "suggestions.placePrediction.text.text,"
            "suggestions.placePrediction.structuredFormat.mainText.text,"
            "suggestions.placePrediction.structuredFormat.secondaryText.text"
        ),
    }

    url = f"{settings.google_places_base_url}/places:autocomplete"

    async with httpx.AsyncClient(timeout=settings.google_timeout_seconds) as client:
        response = await client.post(url, json=request_body, headers=headers)

    await insert_usage_log(
        user_id=payload.user_id,
        endpoint="places_autocomplete",
        status_code=response.status_code,
        request_summary={
            "input_len": len(payload.input),
            "session_token_present": bool(payload.session_token),
            "language_code": payload.language_code,
            "region_code": payload.region_code,
        },
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json() if response.content else {"error": "Upstream autocomplete failed"},
        )

    return response.json()


@router.post("/details")
async def place_details(payload: PlaceDetailsRequest, request: Request) -> dict[str, Any]:
    await enforce_rate_limit(
        request=request,
        endpoint="/api/places/details",
        user_id=payload.user_id,
    )
    api_key = _ensure_google_key()

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "id,displayName.text,formattedAddress,"
            "location,types,primaryType"
        ),
    }

    params: dict[str, str] = {}
    if payload.session_token:
        params["sessionToken"] = payload.session_token
    if payload.language_code:
        params["languageCode"] = payload.language_code

    url = f"{settings.google_places_base_url}/places/{payload.place_id}"

    async with httpx.AsyncClient(timeout=settings.google_timeout_seconds) as client:
        response = await client.get(url, params=params, headers=headers)

    await insert_usage_log(
        user_id=payload.user_id,
        endpoint="place_details",
        status_code=response.status_code,
        request_summary={
            "place_id": payload.place_id,
            "session_token_present": bool(payload.session_token),
            "language_code": payload.language_code,
        },
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.json() if response.content else {"error": "Upstream place details failed"},
        )

    return response.json()
