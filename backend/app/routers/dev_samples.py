# Registered by app/main.py only when DEV_SAMPLES_DIR is set.
# Serves a saved run (a parsed report, the narration scripts/narrate_sample.py generated
# for it, and any speech clips scripts/synthesize_sample.py saved for that narration) so
# the frontend can show real model output without making any API calls: a preview while
# developing, and the demos on the start page where the directory is deployed.
import json
import re
import wave
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.models.narration import NarrationResponse
from app.models.report import FinancialReport
from app.services import report_validator, tts_client

router = APIRouter(prefix="/api/dev/samples")

# Sample names map straight to file names, so only allow plain names - no path
# separators or dots that could reach outside the samples directory.
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


_CLIP_RE = re.compile(r"^[0-9a-f]+\.wav$")


class DevAudioClip(BaseModel):
    url: str
    duration_ms: int


class DevSampleSummary(BaseModel):
    name: str
    company_name: str
    report_type: str
    fiscal_period: str


class DevSample(BaseModel):
    report: FinancialReport
    narration: NarrationResponse
    # One entry per narration line: the clip scripts/synthesize_sample.py saved for that
    # exact text, or None where there isn't one (the frontend then times the line itself).
    audio: list[DevAudioClip | None] = Field(default_factory=list)


def _saved_clip(name: str, text: str) -> DevAudioClip | None:
    filename = tts_client.clip_filename(text)
    path = Path(settings.dev_samples_dir or "") / f"{name}.audio" / filename
    if not path.is_file():
        return None
    try:
        with wave.open(str(path), "rb") as wav:
            duration_ms = round(wav.getnframes() / wav.getframerate() * 1000)
    except (wave.Error, EOFError):
        return None
    return DevAudioClip(url=f"{router.prefix}/{name}/audio/{filename}", duration_ms=duration_ms)


def _read(path: Path, model: type[BaseModel]) -> BaseModel:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample file not found: {path.name}")
    try:
        return model.model_validate(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"{path.name} is not a valid {model.__name__}: {exc}") from exc


@router.get("", response_model=list[DevSampleSummary])
def list_samples() -> list[DevSampleSummary]:
    """The saved runs that can be opened: every `{name}.json` with a `{name}.narration.json`
    next to it. A file that doesn't hold a report is left out rather than failing the list."""
    directory = Path(settings.dev_samples_dir or "")
    summaries: list[DevSampleSummary] = []
    for path in sorted(directory.glob("*.json")):
        name = path.stem
        if not _NAME_RE.match(name) or not (directory / f"{name}.narration.json").is_file():
            continue
        try:
            meta = FinancialReport.model_validate(json.loads(path.read_text())).meta
        except (json.JSONDecodeError, ValidationError):
            continue
        summaries.append(
            DevSampleSummary(
                name=name,
                company_name=meta.company_name,
                report_type=meta.report_type,
                fiscal_period=meta.fiscal_period,
            )
        )
    return summaries


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
    audio = [_saved_clip(name, line.text) for line in narration.lines]
    return DevSample(report=report, narration=narration, audio=audio)


@router.get("/{name}/audio/{filename}")
def get_sample_audio(name: str, filename: str) -> FileResponse:
    if not _NAME_RE.match(name) or not _CLIP_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid sample or clip name.")
    path = Path(settings.dev_samples_dir or "") / f"{name}.audio" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Audio clip not found: {filename}")
    return FileResponse(path, media_type="audio/wav")
