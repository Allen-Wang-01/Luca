import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.narration import NarrationLine, NarrationTrace
from app.services import narration_agent
from app.services.narration_validator import NarrationQualityError

client = TestClient(app)

EMPTY_TRACE = NarrationTrace(
    turns=[], total_input_tokens=0, total_output_tokens=0, total_cost_usd=0, total_duration_ms=0, repaired_target_ids=0
)


def test_returns_lines_and_trace(report, monkeypatch):
    received = {}

    def fake_generate(report_arg):
        received["company"] = report_arg.meta.company_name
        return [NarrationLine(text="Hello.", target_id="p_overview")], EMPTY_TRACE

    monkeypatch.setattr(narration_agent, "generate_narration", fake_generate)

    response = client.post("/api/reports/narration", json={"report": report.model_dump(mode="json")})

    assert response.status_code == 200
    assert response.json()["lines"] == [
        {
            "text": "Hello.",
            "target_id": "p_overview",
            "sources": [],
            "visual": None,
            "figures": [],
            "calculations": [],
        }
    ]
    assert "turns" in response.json()["trace"]
    assert received["company"] == "Acme Corp"


def test_quality_failure_is_a_502(report, monkeypatch):
    def failing_generate(report_arg):
        raise NarrationQualityError("nope")

    monkeypatch.setattr(narration_agent, "generate_narration", failing_generate)

    response = client.post("/api/reports/narration", json={"report": report.model_dump(mode="json")})

    assert response.status_code == 502


def _stream_events(response):
    return [json.loads(line[len("data: ") :]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_stream_sends_the_runs_events_and_ends_with_the_result(report, monkeypatch):
    def fake_generate(report_arg, on_event):
        on_event({"type": "turn_started", "turn": 1, "purpose": "draft"})
        return [NarrationLine(text="Hello.", target_id="p_overview")], EMPTY_TRACE

    monkeypatch.setattr(narration_agent, "generate_narration", fake_generate)

    response = client.post("/api/reports/narration/stream", json={"report": report.model_dump(mode="json")})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _stream_events(response)
    assert [event["type"] for event in events] == ["turn_started", "result"]
    assert events[-1]["narration"]["lines"][0]["text"] == "Hello."
    assert "turns" in events[-1]["narration"]["trace"]


def test_stream_reports_a_failed_run_as_an_error_event(report, monkeypatch):
    def failing_generate(report_arg, on_event):
        raise NarrationQualityError("nope")

    monkeypatch.setattr(narration_agent, "generate_narration", failing_generate)

    response = client.post("/api/reports/narration/stream", json={"report": report.model_dump(mode="json")})

    assert _stream_events(response) == [{"type": "error", "detail": "Narration generation failed: nope"}]


def test_stream_rejects_empty_report(report):
    body = report.model_dump(mode="json")
    body["blocks"] = []

    response = client.post("/api/reports/narration/stream", json={"report": body})

    assert response.status_code == 422


def test_rejects_empty_report(report):
    body = report.model_dump(mode="json")
    body["blocks"] = []

    response = client.post("/api/reports/narration", json={"report": body})

    assert response.status_code == 422
