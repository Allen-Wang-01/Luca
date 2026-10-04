import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.models.narration import NarrationTrace
from app.models.report import Flag
from app.routers import dev_samples

# A bare app with just this router: app.main only registers it when DEV_SAMPLES_DIR is
# set, which depends on the developer's local .env.
_app = FastAPI()
_app.include_router(dev_samples.router)
client = TestClient(_app)

TRACE = NarrationTrace(
    turns=[], total_input_tokens=0, total_output_tokens=0, total_cost_usd=0, total_duration_ms=0, repaired_target_ids=0
)


@pytest.fixture
def samples_dir(tmp_path, monkeypatch, report):
    monkeypatch.setattr(settings, "dev_samples_dir", str(tmp_path))
    (tmp_path / "acme.json").write_text(report.model_dump_json())
    narration = {"lines": [{"text": "Hello.", "target_id": "p_overview", "sources": []}], "trace": TRACE.model_dump()}
    (tmp_path / "acme.narration.json").write_text(json.dumps(narration))
    return tmp_path


def test_serves_saved_report_and_narration(samples_dir):
    response = client.get("/api/dev/samples/acme")

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["meta"]["company_name"] == "Acme Corp"
    assert body["narration"]["lines"][0]["text"] == "Hello."


def test_saved_flags_are_replaced_by_current_validation(samples_dir, report):
    # The conftest report's "Other" row carries a flag no current rule produces.
    assert report.blocks[1].rows[2].flags

    body = client.get("/api/dev/samples/acme").json()

    assert body["report"]["blocks"][1]["rows"][2]["flags"] == []


def test_older_narration_files_without_newer_fields_still_load(samples_dir):
    # Files saved before sources/web search existed lack those fields entirely.
    old = {"lines": [{"text": "Hi.", "target_id": "p_overview"}], "trace": TRACE.model_dump(exclude={"total_web_searches", "dropped_source_urls", "blocked_source_urls"})}
    (samples_dir / "acme.narration.json").write_text(json.dumps(old))

    response = client.get("/api/dev/samples/acme")

    assert response.status_code == 200
    assert response.json()["narration"]["lines"][0]["sources"] == []


def test_version_selects_a_backed_up_narration(samples_dir):
    backup = {"lines": [{"text": "Older run.", "target_id": "p_overview"}], "trace": TRACE.model_dump()}
    (samples_dir / "acme.narration.v1.json").write_text(json.dumps(backup))

    body = client.get("/api/dev/samples/acme?version=v1").json()

    assert body["narration"]["lines"][0]["text"] == "Older run."
    assert client.get("/api/dev/samples/acme?version=../x").status_code == 400


def test_missing_sample_is_404(samples_dir):
    assert client.get("/api/dev/samples/nope").status_code == 404


def test_names_that_could_escape_the_directory_are_rejected(samples_dir):
    assert client.get("/api/dev/samples/acme.narration").status_code == 400
    assert client.get("/api/dev/samples/..%2Facme").status_code in (400, 404)


def test_unparseable_file_is_422(samples_dir):
    (samples_dir / "acme.narration.json").write_text("{not json")

    assert client.get("/api/dev/samples/acme").status_code == 422
