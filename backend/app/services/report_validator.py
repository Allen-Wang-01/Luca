# Post-parse arithmetic consistency checks. Kept independent from the LLM prompt so
# validation rules can evolve without touching parsing. Flags mutate rows in place.
from app.models.report import FinancialReport, Flag, Row, TableBlock

_TOLERANCE = 1.0  # absolute, in the table's own unit (usually millions) - rounding slack

# Each rule: (minuend label, subtrahend label, result label) meaning
# minuend - subtrahend ≈ result. Labels are matched by substring, case-insensitive.
_DIFFERENCE_RULES = [
    ("revenue", "cost of revenue", "gross profit"),
]

# Each rule: (part_a label, part_b label, total label) meaning part_a + part_b ≈ total.
_SUM_RULES = [
    ("total liabilities", "total equity", "total assets"),
    ("total liabilities", "stockholders equity", "total assets"),
]


def validate(report: FinancialReport) -> None:
    for block in report.blocks:
        if isinstance(block, TableBlock):
            _check_table(block)


def _check_table(table: TableBlock) -> None:
    rows_by_label = {row.label.lower(): row for row in table.rows}

    def find(needle: str) -> Row | None:
        for label, row in rows_by_label.items():
            if needle in label:
                return row
        return None

    for minuend_label, subtrahend_label, result_label in _DIFFERENCE_RULES:
        minuend, subtrahend, result = (
            find(minuend_label),
            find(subtrahend_label),
            find(result_label),
        )
        if minuend and subtrahend and result:
            _check_relationship(
                result,
                lambda a, b: a - b,
                minuend,
                subtrahend,
                f"{minuend.label} - {subtrahend.label} should equal {result.label}",
            )

    for a_label, b_label, total_label in _SUM_RULES:
        a, b, total = find(a_label), find(b_label), find(total_label)
        if a and b and total:
            _check_relationship(
                total,
                lambda x, y: x + y,
                a,
                b,
                f"{a.label} + {b.label} should equal {total.label}",
            )


def _check_relationship(result_row, op, a: Row, b: Row, message: str) -> None:
    for a_cell in a.cells:
        b_cell = next((c for c in b.cells if c.col_id == a_cell.col_id), None)
        result_cell = next(
            (c for c in result_row.cells if c.col_id == a_cell.col_id), None
        )
        if not b_cell or not result_cell:
            continue
        if a_cell.value is None or b_cell.value is None or result_cell.value is None:
            continue
        expected = op(a_cell.value, b_cell.value)
        if abs(expected - result_cell.value) > _TOLERANCE:
            result_row.flags.append(
                Flag(
                    severity="warning",
                    code="arithmetic_mismatch",
                    message=f"{message} (expected {expected:g}, got {result_cell.value:g})",
                )
            )
