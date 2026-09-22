import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.main import app
from app.models.llm_report import (
    LLMCell,
    LLMFinancialReport,
    LLMReportMeta,
    LLMRow,
    LLMSection,
    LLMTableBlock,
)
from app.models.report import Column
from app.services import llm_client, pdf_gatekeeper

client = TestClient(app)


def _financial_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 800, "CONDENSED CONSOLIDATED STATEMENTS OF INCOME")
    pdf.drawString(72, 780, "Total revenue, net income, gross margin, balance sheet.")
    pdf.save()
    return buffer.getvalue()


def _unrelated_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 800, "Grocery list: milk, eggs, bread.")
    pdf.save()
    return buffer.getvalue()


@pytest.fixture
def stub_llm(monkeypatch):
    canned = LLMFinancialReport(
        meta=LLMReportMeta(
            company_name="Acme Corp",
            report_type="10-Q",
            fiscal_period="Q2",
            currency="USD",
            unit_scale="millions",
        ),
        sections=[LLMSection(slug="income_statement", title="Income Statement", block_slugs=["income_statement"])],
        blocks=[
            LLMTableBlock(
                slug="income_statement",
                title="Income Statement",
                columns=[Column(id="col0", label="Metric"), Column(id="col1", label="Q2")],
                rows=[
                    LLMRow(
                        label="Revenue",
                        cells=[LLMCell(col_id="col1", value=100, raw_text="100", value_type="number")],
                    )
                ],
            )
        ],
    )
    monkeypatch.setattr(llm_client, "parse_report", lambda pdf_bytes, filename: canned)
    return canned


def test_parse_returns_financial_report(stub_llm):
    response = client.post(
        "/api/reports/parse",
        files={"file": ("report.pdf", _financial_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["company_name"] == "Acme Corp"
    assert body["blocks"][0]["id"] == "t_income_statement"


def test_rejects_non_pdf_content_type(stub_llm):
    response = client.post(
        "/api/reports/parse",
        files={"file": ("report.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400


def test_rejects_pdf_that_does_not_look_financial(stub_llm):
    response = client.post(
        "/api/reports/parse",
        files={"file": ("report.pdf", _unrelated_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 422


def test_rejects_empty_pdf(stub_llm):
    response = client.post(
        "/api/reports/parse",
        files={"file": ("report.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 422


def test_rejects_oversized_pdf(stub_llm, monkeypatch):
    monkeypatch.setattr(pdf_gatekeeper, "MAX_PDF_SIZE_BYTES", 10)

    response = client.post(
        "/api/reports/parse",
        files={"file": ("report.pdf", _financial_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 422
