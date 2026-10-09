# How a table's rows and columns are named wherever they are shown away from the table
# itself (a tool result, the text the narration model reads). On the page a row is told
# apart from another with the same label by the sub-heading above it, and a column by
# the group header over it; taken out of the table, the label has to carry that itself.
# The frontend does the same for its cards (frontend/src/narration/targetIndex.ts).
# Pure functions, no I/O.
from collections import Counter

from app.models.report import TableBlock


def _row_groups(table: TableBlock) -> dict[str, str | None]:
    """Row id -> the sub-heading the row belongs to. A total is usually printed back at
    the outer level, under no sub-heading of its own, so it takes the one its parts
    share: two "Total sales" rows closing two different breakdowns are told apart by
    what they add up."""
    own = {row.id: row.group for row in table.rows}
    groups: dict[str, str | None] = {}
    for row in table.rows:
        parts = {own.get(term.row_id) for term in row.sum_of}
        groups[row.id] = row.group or (parts.pop() if len(parts) == 1 else None)
    return groups


def row_labels(table: TableBlock) -> dict[str, str]:
    """Row id -> label, with the sub-heading in front where the label alone is shared
    by several rows of the table."""
    counts = Counter(row.label for row in table.rows if row.cells)
    groups = _row_groups(table)
    return {
        row.id: f"{groups[row.id]} · {row.label}" if groups[row.id] and counts[row.label] > 1 else row.label
        for row in table.rows
    }


def column_labels(table: TableBlock) -> dict[str, str]:
    """Column id -> label, with its group header in front if it has one."""
    group_by_col_id = {col_id: group.label for group in table.column_groups for col_id in group.col_ids}
    return {
        column.id: f"{group_by_col_id[column.id]} · {column.label}" if column.id in group_by_col_id else column.label
        for column in table.columns
    }
