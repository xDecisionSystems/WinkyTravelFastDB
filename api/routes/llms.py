from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from services.rate_limit import enforce_rate_limit


router = APIRouter(tags=["llms"])

_ROOT_DIR = Path(__file__).resolve().parents[2]
_LLMS_FILE = _ROOT_DIR / "llms.txt"


def _read_llms_text() -> str:
    if not _LLMS_FILE.exists():
        raise HTTPException(status_code=404, detail="llms.txt not found")
    if not _LLMS_FILE.is_file():
        raise HTTPException(status_code=500, detail="llms.txt path is not a file")
    try:
        return _LLMS_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read llms.txt: {exc}") from exc


@router.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt(request: Request) -> str:
    await enforce_rate_limit(request=request, endpoint="/llms.txt")
    return _read_llms_text()


@router.get("/llm.txt", response_class=PlainTextResponse)
async def llm_txt_alias(request: Request) -> str:
    await enforce_rate_limit(request=request, endpoint="/llm.txt")
    return _read_llms_text()
