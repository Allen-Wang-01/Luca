from datetime import datetime, timezone

import pytest

from app.models.report import (
    Cell,
    Column,
    FinancialReport,
    Flag,
    ParagraphBlock,
    ReportMeta,
    Row,
    Section,
    TableBlock,
)


def _cell(row_id: str, col_id: str, value: float | None, raw_text: str) -> Cell:
    return Cell(id=f"{row_id}_{col_id}", col_id=col_id, value=value, raw_text=raw_text, value_type="number")


@pytest.fixture
def report() -> FinancialReport:
    """A small report shaped like real parser output: a heading, an income table with a
    current and prior-year column (in millions), and an outlook paragraph whose figure
    only appears in prose."""
    table_id = "t_income"
    rows = [
        Row(
            id=f"{table_id}__r0",
            label="Revenue",
            cells=[_cell(f"{table_id}__r0", "q2", 200, "200"), _cell(f"{table_id}__r0", "q2_ly", 100, "100")],
        ),
        Row(
            id=f"{table_id}__r1",
            label="Gross profit",
            cells=[_cell(f"{table_id}__r1", "q2", 150, "150"), _cell(f"{table_id}__r1", "q2_ly", 0, "0")],
        ),
        Row(
            id=f"{table_id}__r2",
            label="Other",
            cells=[_cell(f"{table_id}__r2", "q2", None, "n/m")],
            flags=[Flag(severity="warning", code="arithmetic_mismatch", message="Other looks wrong")],
        ),
    ]
    return FinancialReport(
        meta=ReportMeta(
            company_name="Acme Corp",
            ticker="ACME",
            report_type="10-Q",
            fiscal_period="Q2",
            currency="USD",
            unit_scale="millions",
            source_filename="report.pdf",
            parsed_at=datetime.now(timezone.utc),
        ),
        sections=[Section(id="sec_results", title="Results", block_ids=["p_overview", table_id])],
        blocks=[
            ParagraphBlock(id="p_overview", style="heading", text="Quarterly results"),
            TableBlock(
                id=table_id,
                title="Income Statement",
                unit="USD millions",
                columns=[Column(id="q2", label="Q2 FY26"), Column(id="q2_ly", label="Q2 FY25")],
                rows=rows,
            ),
            ParagraphBlock(
                id="p_outlook",
                style="body",
                text="Revenue is expected to be $0.3 billion, plus or minus 2%.",
            ),
        ],
    )
