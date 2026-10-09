# Post-parse arithmetic consistency checks. Kept independent from the LLM prompt so
# validation rules can evolve without touching parsing. Flags mutate rows in place.
#
# The parser says which rows each total is made of (Row.sum_of); this module only does
# the arithmetic, so nothing here depends on what a company calls its rows. Flag codes:
# - "arithmetic_mismatch": a total doesn't add up in some columns but does in others,
#   or (tables without sum_of) a label rule failed. The figure is suspect, and the
#   narration says so to the listener.
# - "unconfirmed_sum": a total doesn't add up in a table with a single column to check.
#   Shown on the page only.
import re

from app.core.logging import get_logger
from app.models.report import Cell, FinancialReport, Flag, Row, TableBlock
from app.services import report_labels

logger = get_logger(__name__)

_TOLERANCE = 1.0  # absolute, in the table's own unit (usually millions) - rounding slack

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
# How statements print "nothing" in a column of figures.
_DASHES = frozenset({"-", "–", "—", ""})

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
    if any(row.sum_of for row in table.rows):
        _check_declared_sums(table)
    else:
        # A table parsed before totals named their parts: all there is to go on is
        # what the rows are called.
        _check_label_rules(table)


def _last_digit(cell: Cell) -> float:
    """One unit of the cell's last printed digit: 1 for "1,250", 0.01 for "2.03"."""
    match = _NUMBER_RE.search(cell.raw_text)
    return 10 ** -len(match.group().partition(".")[2]) if match else 1.0


def _term_cell(row: Row, col_id: str) -> Cell | None:
    """The row's figure in that column, with a dash read as zero. None if the column
    holds nothing that can be added up."""
    cell = next((c for c in row.cells if c.col_id == col_id), None)
    if cell is None or cell.value is not None:
        return cell
    return cell.model_copy(update={"value": 0.0}) if cell.raw_text.strip() in _DASHES else None


def _check_declared_sums(table: TableBlock) -> None:
    rows_by_id = {row.id: row for row in table.rows}
    column_labels = report_labels.column_labels(table)
    for total in table.rows:
        terms = [(rows_by_id.get(term.row_id), term.sign) for term in total.sum_of]
        if not terms or any(row is None for row, _ in terms):
            continue

        formula = " ".join(
            f"{'+' if sign == 'add' else '-'} {row.label}" for row, sign in terms
        ).removeprefix("+ ")
        checked = 0
        mismatches: list[str] = []
        for total_cell in total.cells:
            cells = [_term_cell(row, total_cell.col_id) for row, _ in terms]
            if total_cell.value is None or any(cell is None for cell in cells):
                continue
            checked += 1
            expected = sum(cell.value if sign == "add" else -cell.value for cell, (_, sign) in zip(cells, terms))
            # Every figure is rounded to its last printed digit, so each can be half a
            # unit off before the sum is.
            tolerance = 0.5 * sum(_last_digit(cell) for cell in [total_cell, *cells])
            if abs(expected - total_cell.value) > tolerance + 1e-9:
                column = column_labels.get(total_cell.col_id, total_cell.col_id)
                mismatches.append(
                    f"{total.label} should equal {formula} in '{column}' "
                    f"(expected {expected:g}, got {total_cell.value:g})"
                )

        if not mismatches:
            continue
        if checked == 1:
            # One column can't tell a misread figure from a relationship that was
            # never there.
            total.flags.append(Flag(severity="warning", code="unconfirmed_sum", message=mismatches[0]))
        elif len(mismatches) == checked:
            # A misread figure breaks the column it is in. Every column failing means
            # the rows don't add up this way at all: the relationship is wrong, not
            # the figures, and flagging it would cast doubt on correct numbers.
            logger.info("declared_sum_ignored row=%s formula=%r columns=%d", total.id, formula, checked)
        else:
            total.flags.extend(
                Flag(severity="warning", code="arithmetic_mismatch", message=message) for message in mismatches
            )


def _check_label_rules(table: TableBlock) -> None:
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
