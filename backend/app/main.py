from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logging import configure_logging
from app.routers.reports import router as reports_router

configure_logging()

app = FastAPI(title="Luca API")
app.include_router(reports_router)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

if settings.dev_samples_dir:
    from app.routers.dev_samples import router as dev_samples_router

    app.include_router(dev_samples_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
