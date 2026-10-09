from app.models.llm_report import (
    LLMCell,
    LLMFinancialReport,
    LLMParagraphBlock,
    LLMReportMeta,
    LLMRow,
    LLMSumTerm,
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


def test_rows_keep_what_the_parser_says_they_measure():
    table = _table("income_statement")
    figures = table.rows[0].cells
    table.rows = [
        # A sub-heading has no figures, so it measures nothing whatever it was given.
        LLMRow(label="Per share:", cells=[], quantity="per_share", scale="actual"),
        LLMRow(label="Basic", cells=figures, quantity="per_share", scale="actual", group=" Per share: "),
        LLMRow(label="Revenue", cells=figures),
    ]

    rows = assign_ids(LLMFinancialReport(meta=META, sections=[], blocks=[table]), "report.pdf").blocks[0].rows

    assert (rows[0].quantity, rows[0].scale, rows[0].group) == (None, None, None)
    assert (rows[1].quantity, rows[1].scale, rows[1].group) == ("per_share", "actual", "Per share")
    assert (rows[2].quantity, rows[2].scale, rows[2].group) == (None, None, None)


def _summed_table(indexes=(0, 1, 2, 3), sum_of=((1, "add"), (2, "subtract"))):
    table = _table("income_statement")
    figures = table.rows[0].cells
    terms = [LLMSumTerm(index=index, sign=sign) for index, sign in sum_of]
    table.rows = [
        LLMRow(index=indexes[0], label="Results:", cells=[]),
        LLMRow(index=indexes[1], label="Sales", cells=figures),
        LLMRow(index=indexes[2], label="Costs", cells=figures),
        LLMRow(index=indexes[3], label="Margin", cells=figures, sum_of=terms),
    ]
    return assign_ids(LLMFinancialReport(meta=META, sections=[], blocks=[table]), "report.pdf").blocks[0]


def test_a_total_refers_to_its_parts_by_row_id():
    table = _summed_table()

    assert [(term.row_id, term.sign) for term in table.rows[3].sum_of] == [
        ("t_income_statement__r1", "add"),
        ("t_income_statement__r2", "subtract"),
    ]
    assert table.rows[1].sum_of == []


def test_sums_are_dropped_when_the_row_numbering_is_off():
    # The model skipped a number, so its references can't be trusted to mean the rows
    # they point at.
    assert _summed_table(indexes=(0, 1, 3, 4)).rows[3].sum_of == []


def test_a_sum_that_refers_to_an_impossible_row_is_dropped():
    for sum_of in (
        ((1, "add"), (9, "add")),  # no such row
        ((1, "add"), (3, "add")),  # the total itself
        ((0, "add"), (1, "add")),  # a sub-heading, which has no figures
        ((1, "add"), (1, "add")),  # the same row twice
    ):
        assert _summed_table(sum_of=sum_of).rows[3].sum_of == []


def test_section_block_slugs_resolve_to_final_ids():
    llm_report = LLMFinancialReport(
        meta=META,
        sections=[LLMSection(slug="overview_section", title="Overview", block_slugs=["income_statement"])],
        blocks=[_table("income_statement")],
    )

    report = assign_ids(llm_report, source_filename="report.pdf")

    assert report.sections[0].block_ids == ["t_income_statement"]
