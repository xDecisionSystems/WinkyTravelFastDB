from __future__ import annotations

from hmac import compare_digest

from fastapi import APIRouter, HTTPException, Query, Request

from config.settings import settings
from services.log_reader import read_log_tail, resolve_log_file
from services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/api/dev", tags=["dev"])


def _is_dev_environment() -> bool:
    return settings.environment.strip().lower() in {"development", "dev"}


def _require_master_api_key(request: Request) -> None:
    if not _is_dev_environment():
        raise HTTPException(status_code=403, detail="Dev log endpoint is disabled outside development")

    expected_key = settings.dev_master_api_key.strip()
    if not expected_key:
        raise HTTPException(status_code=503, detail="DEV_MASTER_API_KEY is not configured")

    provided_key = request.headers.get("x-master-api-key", "").strip()
    if not compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid master API key")


@router.get("/logs")
async def read_dev_log(
    request: Request,
    path: str = Query(min_length=1, description="Relative path under DEV_LOG_ROOT_DIR"),
    lines: int = Query(default=200, ge=1),
) -> dict[str, object]:
    _require_master_api_key(request)
    await enforce_rate_limit(
        request=request,
        endpoint="/api/dev/logs",
        user_id="coding-agent",
    )

    if lines > settings.dev_log_max_lines:
        raise HTTPException(
            status_code=400,
            detail=f"lines cannot exceed DEV_LOG_MAX_LINES ({settings.dev_log_max_lines})",
        )

    try:
        log_file = resolve_log_file(settings.dev_log_root_dir, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    if not log_file.is_file():
        raise HTTPException(status_code=400, detail="Requested path is not a file")

    try:
        content, truncated = read_log_tail(
            log_file,
            max_bytes=settings.dev_log_max_bytes,
            max_lines=lines,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied reading log file") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {exc}") from exc

    return {
        "path": str(log_file),
        "truncated": truncated,
        "max_bytes": settings.dev_log_max_bytes,
        "max_lines": lines,
        "content": content,
    }
