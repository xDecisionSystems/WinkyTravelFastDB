from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.dev_logs import router as dev_logs_router
from api.routes.health import router as health_router
from api.routes.llms import router as llms_router
from api.routes.places import router as places_router
from api.routes.users import router as users_router
from config.settings import settings
from services.postgres import close, connect


@asynccontextmanager
async def lifespan(_: FastAPI):
    await connect()
    try:
        yield
    finally:
        await close()


app = FastAPI(
    title="Winky Travel FastDB",
    version="0.1.0",
    lifespan=lifespan,
)

# TODO: Replace wildcard CORS with explicit frontend origin allowlist.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(llms_router)
app.include_router(users_router)
app.include_router(places_router)
app.include_router(dev_logs_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
