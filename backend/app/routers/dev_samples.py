# Local development only - registered by app/main.py when DEV_SAMPLES_DIR is set.
# Serves a saved run (a parsed report plus the narration scripts/narrate_sample.py
# generated for it) so the frontend can be previewed with real model output without
# making any API calls.
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.models.narration import NarrationResponse
from app.models.report import FinancialReport
from app.services import report_validator

router = APIRouter(prefix="/api/dev/samples")

# Sample names map straight to file names, so only allow plain names - no path
# separators or dots that could reach outside the samples directory.
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class DevSample(BaseModel):
    report: FinancialReport
    narration: NarrationResponse


def _read(path: Path, model: type[BaseModel]) -> BaseModel:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample file not found: {path.name}")
    try:
        return model.model_validate(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"{path.name} is not a valid {model.__name__}: {exc}") from exc


@router.get("/{name}", response_model=DevSample)
def get_sample(name: str, version: str | None = None) -> DevSample:
    """`version` picks a backed-up narration, `{name}.narration.{version}.json`, instead
    of the latest `{name}.narration.json` - handy for comparing runs side by side."""
    for value in (name, version):
        if value is not None and not _NAME_RE.match(value):
            raise HTTPException(
                status_code=400, detail="Sample names and versions may only contain letters, digits, '_' and '-'."
            )

    directory = Path(settings.dev_samples_dir or "")
    narration_file = f"{name}.narration.{version}.json" if version else f"{name}.narration.json"
    report = _read(directory / f"{name}.json", FinancialReport)
    narration = _read(directory / narration_file, NarrationResponse)
    report_validator.revalidate(report)
    return DevSample(report=report, narration=narration)
