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
        {"text": "Hello.", "target_id": "p_overview", "sources": [], "visual": None}
    ]
    assert "turns" in response.json()["trace"]
    assert received["company"] == "Acme Corp"


def test_quality_failure_is_a_502(report, monkeypatch):
    def failing_generate(report_arg):
        raise NarrationQualityError("nope")

    monkeypatch.setattr(narration_agent, "generate_narration", failing_generate)

    response = client.post("/api/reports/narration", json={"report": report.model_dump(mode="json")})

    assert response.status_code == 502


def test_rejects_empty_report(report):
    body = report.model_dump(mode="json")
    body["blocks"] = []

    response = client.post("/api/reports/narration", json={"report": body})

    assert response.status_code == 422
