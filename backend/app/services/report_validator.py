# Post-parse arithmetic consistency checks. Kept independent from the LLM prompt so
# validation rules can evolve without touching parsing. Flags mutate rows in place.
import re

from app.models.report import FinancialReport, Flag, Row, TableBlock

_TOLERANCE = 1.0  # absolute, in the table's own unit (usually millions) - rounding slack

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Each rule: (minuend label, subtrahend label, result label) meaning
# minuend - subtrahend ≈ result. Labels are matched case-insensitively, ignoring
# punctuation: an exact match wins, otherwise a substring match (see _find_row).
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


def revalidate(report: FinancialReport) -> None:
    """Clears existing flags and validates again with the current rules.

    For reports saved to disk earlier: their flags come from whatever validator version
    parsed them, and validation is local and free, so re-running it beats trusting
    stale flags (e.g. a since-fixed false positive).
    """
    for block in report.blocks:
        if isinstance(block, TableBlock):
            block.flags = []
            for row in block.rows:
                row.flags = []
    validate(report)


def _normalize(label: str) -> str:
    return _NON_ALNUM_RE.sub(" ", label.lower()).strip()


def _find_row(rows: list[Row], needle: str, rule_labels: tuple[str, ...], taken: set[str]) -> Row | None:
    # A bare substring match is too loose on its own: in a table with no plain
    # "Revenue" row, "revenue" would match "GAAP cost of revenue", and the rule would
    # end up comparing a row against itself. So a row that also mentions another of
    # the rule's labels is off-limits (looking for "revenue" skips anything with "cost
    # of revenue"; looking for "stockholders equity" skips "Total liabilities and
    # stockholders' equity"), rows already matched by the rule are excluded, and an
    # exact label match beats a substring one.
    other_labels = [label for label in rule_labels if label != needle and label not in needle]
    candidates = [
        row
        for row in rows
        if row.id not in taken and not any(label in _normalize(row.label) for label in other_labels)
    ]
    exact = next((row for row in candidates if _normalize(row.label) == needle), None)
    if exact:
        return exact
    return next((row for row in candidates if needle in _normalize(row.label)), None)


def _find_rule_rows(table: TableBlock, rule_labels: tuple[str, ...]) -> list[Row] | None:
    """All of a rule's rows, as distinct rows, or None if any is missing."""
    found: list[Row] = []
    for needle in rule_labels:
        row = _find_row(table.rows, needle, rule_labels, {r.id for r in found})
        if row is None:
            return None
        found.append(row)
    return found


def _check_table(table: TableBlock) -> None:
    for rule in _DIFFERENCE_RULES:
        rows = _find_rule_rows(table, rule)
        if rows:
            minuend, subtrahend, result = rows
            _check_relationship(
                result,
                lambda a, b: a - b,
                minuend,
                subtrahend,
                f"{minuend.label} - {subtrahend.label} should equal {result.label}",
            )

    for rule in _SUM_RULES:
        rows = _find_rule_rows(table, rule)
        if rows:
            a, b, total = rows
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
