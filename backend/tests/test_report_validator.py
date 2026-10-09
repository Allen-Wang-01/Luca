from app.models.report import Cell, Column, Row, SumTerm, TableBlock
from app.services.report_validator import validate


def _cell(col_id: str, value: float) -> Cell:
    return Cell(id=f"c_{col_id}", col_id=col_id, value=value, raw_text=str(value), value_type="number")


def _income_statement_report(revenue, cost, gross_profit):
    return _report(
        [
            Row(id="r0", label="Revenue", cells=[_cell("col1", revenue)]),
            Row(id="r1", label="Cost of revenue", cells=[_cell("col1", cost)]),
            Row(id="r2", label="Gross profit", cells=[_cell("col1", gross_profit)]),
        ]
    )


def _report(rows):
    from app.models.report import FinancialReport, ReportMeta
    from datetime import datetime, timezone

    table = TableBlock(
        id="t_income_statement",
        title="Income Statement",
        columns=[Column(id="col0", label="Metric"), Column(id="col1", label="Q2")],
        rows=rows,
    )
    return FinancialReport(
        meta=ReportMeta(
            company_name="Acme",
            report_type="10-Q",
            fiscal_period="Q2",
            currency="USD",
            unit_scale="millions",
            source_filename="x.pdf",
            parsed_at=datetime.now(timezone.utc),
        ),
        sections=[],
        blocks=[table],
    )


def test_consistent_arithmetic_gets_no_flags():
    report = _income_statement_report(revenue=100, cost=40, gross_profit=60)

    validate(report)

    for row in report.blocks[0].rows:
        assert row.flags == []


def test_mismatched_arithmetic_flags_the_result_row():
    report = _income_statement_report(revenue=100, cost=40, gross_profit=999)

    validate(report)

    gross_profit_row = report.blocks[0].rows[2]
    assert len(gross_profit_row.flags) == 1
    assert gross_profit_row.flags[0].code == "arithmetic_mismatch"


def test_rounding_within_tolerance_does_not_flag():
    report = _income_statement_report(revenue=100.4, cost=40, gross_profit=60)

    validate(report)

    assert report.blocks[0].rows[2].flags == []


def test_revenue_does_not_match_cost_of_revenue_row():
    # A GAAP/non-GAAP reconciliation table: no plain revenue row, so the revenue rule
    # must not apply at all (it used to compare "GAAP cost of revenue" to itself).
    report = _report(
        [
            Row(id="r0", label="GAAP cost of revenue", cells=[_cell("col1", 20)]),
            Row(id="r1", label="GAAP gross profit", cells=[_cell("col1", 61)]),
            Row(id="r2", label="Non-GAAP cost of revenue", cells=[_cell("col1", 19)]),
            Row(id="r3", label="Non-GAAP gross profit", cells=[_cell("col1", 62)]),
        ]
    )

    validate(report)

    assert all(row.flags == [] for row in report.blocks[0].rows)


def test_exact_label_match_beats_substring_match():
    # "Total revenue" contains "revenue" too, but the exact "Revenue" row is the one
    # the rule means - and it's consistent, so nothing should be flagged.
    report = _report(
        [
            Row(id="r0", label="Total revenue growth", cells=[_cell("col1", 999)]),
            Row(id="r1", label="Revenue", cells=[_cell("col1", 100)]),
            Row(id="r2", label="Cost of revenue", cells=[_cell("col1", 40)]),
            Row(id="r3", label="Gross profit", cells=[_cell("col1", 60)]),
        ]
    )

    validate(report)

    assert all(row.flags == [] for row in report.blocks[0].rows)


def test_combined_liabilities_and_equity_row_is_not_used_as_equity():
    report = _report(
        [
            Row(id="r0", label="Total assets", cells=[_cell("col1", 300)]),
            Row(id="r1", label="Total liabilities", cells=[_cell("col1", 100)]),
            Row(id="r2", label="Total liabilities and stockholders' equity", cells=[_cell("col1", 300)]),
            Row(id="r3", label="Total stockholders' equity", cells=[_cell("col1", 200)]),
        ]
    )

    validate(report)

    assert all(row.flags == [] for row in report.blocks[0].rows)


def test_balance_sheet_mismatch_is_still_flagged():
    report = _report(
        [
            Row(id="r0", label="Total assets", cells=[_cell("col1", 999)]),
            Row(id="r1", label="Total liabilities", cells=[_cell("col1", 100)]),
            Row(id="r2", label="Total stockholders' equity", cells=[_cell("col1", 200)]),
        ]
    )

    validate(report)

    assert report.blocks[0].rows[0].flags[0].code == "arithmetic_mismatch"


COLUMNS = ("q", "q_ly", "ytd")


def _figures(row_id, values):
    return [
        Cell(id=f"{row_id}_{col_id}", col_id=col_id, value=value, raw_text="—" if value is None else f"{value:,}", value_type="number")
        for col_id, value in zip(COLUMNS, values)
    ]


def _statement(sales, costs, margin, columns=COLUMNS, sum_of=(("r0", "add"), ("r1", "subtract"))):
    """Three rows whose labels match none of the label rules, the last one declared as
    the first less the second."""
    terms = [SumTerm(row_id=row_id, sign=sign) for row_id, sign in sum_of]
    report = _report(
        [
            Row(id="r0", label="Net sales", cells=_figures("r0", sales)),
            Row(id="r1", label="Total cost of sales", cells=_figures("r1", costs)),
            Row(id="r2", label="Margin", cells=_figures("r2", margin), sum_of=terms),
        ]
    )
    report.blocks[0].columns = [Column(id=col_id, label=col_id) for col_id in columns]
    return report


def test_a_declared_sum_that_holds_gets_no_flags():
    report = _statement(sales=(300, 250, 900), costs=(120, 110, 380), margin=(180, 140, 520))

    validate(report)

    assert all(row.flags == [] for row in report.blocks[0].rows)


def test_a_figure_that_breaks_a_declared_sum_in_one_column_is_flagged():
    report = _statement(sales=(300, 250, 900), costs=(120, 110, 380), margin=(180, 104, 520))

    validate(report)

    flags = report.blocks[0].rows[2].flags
    assert [flag.code for flag in flags] == ["arithmetic_mismatch"]
    assert flags[0].message == "Margin should equal Net sales - Total cost of sales in 'q_ly' (expected 140, got 104)"


def test_a_declared_sum_that_fails_everywhere_is_a_wrong_relationship_not_a_flag():
    # Declared as sales plus costs: off in every column, which a misread figure never is.
    report = _statement(
        sales=(300, 250, 900), costs=(120, 110, 380), margin=(180, 140, 520), sum_of=(("r0", "add"), ("r1", "add"))
    )

    validate(report)

    assert report.blocks[0].rows[2].flags == []


def test_a_failed_sum_with_one_column_to_check_is_unconfirmed():
    report = _statement(sales=(300,), costs=(120,), margin=(999,), columns=("q",))

    validate(report)

    assert [flag.code for flag in report.blocks[0].rows[2].flags] == ["unconfirmed_sum"]


def test_declared_sums_allow_for_rounding_and_read_a_dash_as_zero():
    # 0.5 off per printed figure is rounding; a dash in a column of figures is nothing.
    report = _statement(sales=(300, 250, 900), costs=(120, None, 380), margin=(181, 250, 520))

    validate(report)

    assert report.blocks[0].rows[2].flags == []


def test_columns_with_the_same_heading_are_flagged_on_the_table(statement):
    table = statement.blocks[0]
    validate(statement)
    assert table.flags == []  # same dates, but under different group headers

    table.column_groups = []
    validate(statement)

    assert [flag.code for flag in table.flags] == ["ambiguous_columns"]
    assert "'q' and 'ytd' are both headed 'June 30, 2031'" in table.flags[0].message
    assert all(row.flags == [] for row in table.rows)


def test_label_rules_are_not_used_once_a_table_declares_its_sums():
    # The label rules would compare "Revenue" with "Cost of revenue" here and flag
    # "Gross profit"; the table says how its rows add up, so they stay out of it.
    report = _report(
        [
            Row(id="r0", label="Revenue", cells=[_cell("col1", 100)]),
            Row(id="r1", label="Cost of revenue", cells=[_cell("col1", 40)]),
            Row(id="r2", label="Gross profit", cells=[_cell("col1", 999)]),
            Row(id="r3", label="Other", cells=[_cell("col1", 5)]),
            Row(id="r4", label="Total", cells=[_cell("col1", 105)], sum_of=[SumTerm(row_id="r0", sign="add"), SumTerm(row_id="r3", sign="add")]),
        ]
    )

    validate(report)

    assert all(row.flags == [] for row in report.blocks[0].rows)
