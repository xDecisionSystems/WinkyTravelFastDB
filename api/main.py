from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.activities import router as activities_router
from api.routes.dev_logs import router as dev_logs_router
from api.routes.health import router as health_router
from api.routes.hotels import router as hotels_router
from api.routes.llms import router as llms_router
from api.routes.places import router as places_router
from api.routes.schedule_items import router as schedule_items_router
from api.routes.settings import router as settings_router
from api.routes.transits import router as transits_router
from api.routes.travels import router as travels_router
from api.routes.trips import router as trips_router
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
app.include_router(trips_router)
app.include_router(activities_router)
app.include_router(travels_router)
app.include_router(hotels_router)
app.include_router(transits_router)
app.include_router(schedule_items_router)
app.include_router(settings_router)
app.include_router(dev_logs_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
