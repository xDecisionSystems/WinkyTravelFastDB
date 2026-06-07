from fastapi import APIRouter, Request

from config.settings import settings
from services.rate_limit import enforce_rate_limit


router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    await enforce_rate_limit(
        request=request,
        endpoint="/health",
    )
    return {
        "status": "ok",
        "service": settings.service_name,
        "environment": settings.environment,
    }
