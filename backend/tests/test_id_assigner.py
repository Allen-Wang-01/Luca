from app.models.llm_report import (
    LLMCell,
    LLMFinancialReport,
    LLMParagraphBlock,
    LLMReportMeta,
    LLMRow,
    LLMSection,
    LLMTableBlock,
)
from app.models.report import Column
from app.services.id_assigner import assign_ids

META = LLMReportMeta(
    company_name="Acme Corp",
    report_type="10-Q",
    fiscal_period="Q2",
    currency="USD",
    unit_scale="millions",
)


def _table(slug: str) -> LLMTableBlock:
    return LLMTableBlock(
        slug=slug,
        title="A table",
        columns=[Column(id="col0", label="Metric"), Column(id="col1", label="Q2")],
        rows=[
            LLMRow(
                label="Revenue",
                cells=[LLMCell(col_id="col1", value=100, raw_text="100", value_type="number")],
            ),
        ],
    )


def test_block_ids_get_type_prefix():
    llm_report = LLMFinancialReport(
        meta=META,
        sections=[],
        blocks=[LLMParagraphBlock(slug="overview", style="heading", text="Overview"), _table("income_statement")],
    )

    report = assign_ids(llm_report, source_filename="report.pdf")

    assert report.blocks[0].id == "p_overview"
    assert report.blocks[1].id == "t_income_statement"


def test_colliding_slugs_get_unique_ids():
    llm_report = LLMFinancialReport(
        meta=META,
        sections=[],
        blocks=[_table("income_statement"), _table("income_statement")],
    )

    report = assign_ids(llm_report, source_filename="report.pdf")

    ids = [b.id for b in report.blocks]
    assert ids == ["t_income_statement", "t_income_statement_2"]
    assert len(set(ids)) == len(ids)


def test_row_and_cell_ids_derive_from_block_id():
    llm_report = LLMFinancialReport(meta=META, sections=[], blocks=[_table("income_statement")])

    report = assign_ids(llm_report, source_filename="report.pdf")

    table = report.blocks[0]
    row = table.rows[0]
    assert row.id == "t_income_statement__r0"
    assert row.cells[0].id == "t_income_statement__r0_col1"


def test_section_block_slugs_resolve_to_final_ids():
    llm_report = LLMFinancialReport(
        meta=META,
        sections=[LLMSection(slug="overview_section", title="Overview", block_slugs=["income_statement"])],
        blocks=[_table("income_statement")],
    )

    report = assign_ids(llm_report, source_filename="report.pdf")

    assert report.sections[0].block_ids == ["t_income_statement"]
