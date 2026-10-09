from datetime import datetime, timezone

import pytest

from app.models.report import (
    Cell,
    Column,
    ColumnGroup,
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
def statement() -> FinancialReport:
    """A statement as the parser marks one up: amounts in millions next to per-share
    amounts and a share count in thousands, labels repeated under different
    sub-headings, and two column groups over columns with the same labels."""
    table_id = "t_ops"

    def row(index, label, values=(), **marks):
        row_id = f"{table_id}__r{index}"
        cells = [_cell(row_id, col_id, value, f"{value:,}") for col_id, value in zip(("q", "q_ly", "ytd", "ytd_ly"), values)]
        return Row(id=row_id, label=label, cells=cells, **marks)

    money = {"quantity": "money", "scale": "millions"}
    rows = [
        row(0, "Sales:"),
        row(1, "Goods", (300, 250, 900, 800), group="Sales", **money),
        row(2, "Cost of sales:"),
        row(3, "Goods", (120, 110, 380, 350), group="Cost of sales", **money),
        row(4, "Net income", (50, 40, 160, 120), **money),
        row(5, "Earnings per share:"),
        row(6, "Basic", (2.5, 1.6, 8.0, 4.8), group="Earnings per share", quantity="per_share", scale="actual"),
        row(7, "Shares used in computing earnings per share:"),
        row(8, "Basic", (20_000, 25_000, 20_000, 25_000), group="Shares used", quantity="share_count", scale="thousands"),
    ]
    columns = [
        Column(id="q", label="June 30, 2031"),
        Column(id="q_ly", label="June 30, 2030"),
        Column(id="ytd", label="June 30, 2031"),
        Column(id="ytd_ly", label="June 30, 2030"),
    ]
    return FinancialReport(
        meta=ReportMeta(
            company_name="Acme Corp",
            report_type="10-Q",
            fiscal_period="Q2",
            currency="USD",
            unit_scale="millions",
            source_filename="report.pdf",
            parsed_at=datetime.now(timezone.utc),
        ),
        sections=[],
        blocks=[
            TableBlock(
                id=table_id,
                title="Statements of Operations",
                unit="In millions, except share data in thousands and per-share amounts",
                column_groups=[
                    ColumnGroup(label="Three Months Ended", col_ids=["q", "q_ly"]),
                    ColumnGroup(label="Six Months Ended", col_ids=["ytd", "ytd_ly"]),
                ],
                columns=columns,
                rows=rows,
            )
        ],
    )


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
