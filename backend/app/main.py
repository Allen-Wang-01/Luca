from fastapi import FastAPI

from app.config import settings
from app.core.logging import configure_logging
from app.routers.reports import router as reports_router

configure_logging()

app = FastAPI(title="Financial Agent API")
app.include_router(reports_router)

if settings.dev_samples_dir:
    from app.routers.dev_samples import router as dev_samples_router

    app.include_router(dev_samples_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
