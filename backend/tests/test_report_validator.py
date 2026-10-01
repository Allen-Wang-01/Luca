from app.models.report import Cell, Column, Row, TableBlock
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
