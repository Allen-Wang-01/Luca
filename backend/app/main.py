from fastapi import FastAPI

from app.core.logging import configure_logging
from app.routers.reports import router as reports_router

configure_logging()

app = FastAPI(title="Financial Agent API")
app.include_router(reports_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
