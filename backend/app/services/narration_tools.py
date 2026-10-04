# Calculation tools the narration model can call. Operands are references into the
# report, never bare numbers, so figures don't pass through the model's own
# transcription: a table figure is referenced by cell id and looked up here; a figure
# that only appears in prose (e.g. "$3.2 billion" in a headline bullet) is referenced
# by paragraph id plus the figure exactly as written, and is only used after checking
# that it really appears verbatim in that paragraph. Results name their sources, so the
# model can target the same cell in its narration. Pure functions, no I/O.
#
# Errors are returned as {"error": ...} tool output rather than raised - the model
# reads them and can correct itself (e.g. a row id passed where a cell id belongs).
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from app.models.report import FinancialReport, ParagraphBlock, TableBlock

_UNIT_SCALE_FACTORS = {"actual": 1, "thousands": 1e3, "millions": 1e6, "billions": 1e9}
_SCALE_WORD_FACTORS = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SCALE_WORD_RE = re.compile(r"\b(thousand|million|billion|trillion)s?\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Operand:
    id: str
    label: str
    raw_text: str
    value: float  # as printed: a table cell in its table's unit, a quote in its own
    absolute: float  # in actual units, so table and prose figures can be combined
    is_percent: bool
    from_text: bool


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).lower()


def _parse_quote(quote: str) -> tuple[float, float, bool] | str:
    """(value as written, value in actual units, is_percent), or an error message."""
    numbers = _NUMBER_RE.findall(quote)
    if len(numbers) != 1:
        return f"Quote must contain exactly one figure (e.g. '$3.2 billion'), got {quote!r}."
    value = float(numbers[0].replace(",", ""))
    if "(" in quote and ")" in quote or re.search(r"-\s*\$?\d", quote):
        value = -value
    is_percent = "%" in quote or "percent" in quote.lower()
    scale_match = _SCALE_WORD_RE.search(quote)
    factor = _SCALE_WORD_FACTORS[scale_match.group(1).lower()] if scale_match else 1
    return value, value * factor, is_percent


class FigureIndex:
    def __init__(self, report: FinancialReport) -> None:
        scale = _UNIT_SCALE_FACTORS.get(report.meta.unit_scale, 1)
        self._cells: dict[str, _Operand] = {}
        self._empty_cells: dict[str, str] = {}
        self._row_ids: set[str] = set()
        self._paragraphs: dict[str, str] = {}
        for block in report.blocks:
            if isinstance(block, ParagraphBlock):
                self._paragraphs[block.id] = block.text
            if not isinstance(block, TableBlock):
                continue
            column_labels = {c.id: c.label for c in block.columns}
            for row in block.rows:
                self._row_ids.add(row.id)
                for cell in row.cells:
                    label = f"{row.label} · {column_labels.get(cell.col_id, cell.col_id)}"
                    if cell.value is None:
                        self._empty_cells[cell.id] = label
                        continue
                    is_percent = cell.value_type == "percent"
                    # Per-share figures (EPS, dividends) are printed as-is even in a
                    # "$ in millions" table, so the report's unit scale doesn't apply.
                    unscaled = is_percent or "per share" in row.label.lower()
                    self._cells[cell.id] = _Operand(
                        id=cell.id,
                        label=label,
                        raw_text=cell.raw_text,
                        value=cell.value,
                        absolute=cell.value * (1 if unscaled else scale),
                        is_percent=is_percent,
                        from_text=False,
                    )

    def resolve(self, operand: Any) -> tuple[_Operand | None, str | None]:
        if not isinstance(operand, dict) or not isinstance(operand.get("id"), str):
            return None, f"Operand must be an object with an `id`, got {operand!r}."
        ref_id: str = operand["id"]
        quote = operand.get("quote")
        if quote:
            return self._resolve_quote(ref_id, quote)

        if ref_id in self._cells:
            return self._cells[ref_id], None
        if ref_id in self._empty_cells:
            return None, f"Cell '{ref_id}' ({self._empty_cells[ref_id]}) has no numeric value."
        if ref_id in self._row_ids:
            return None, f"'{ref_id}' is a row id; pass a cell id ({ref_id}_{{col_id}})."
        if ref_id in self._paragraphs:
            return None, (
                f"'{ref_id}' is a paragraph; also pass `quote`: the figure exactly as written "
                "in its text, e.g. '$3.2 billion'."
            )
        return None, f"Unknown id '{ref_id}'."

    def _resolve_quote(self, paragraph_id: str, quote: str) -> tuple[_Operand | None, str | None]:
        text = self._paragraphs.get(paragraph_id)
        if text is None:
            return None, (
                f"`quote` is only for figures in paragraph text, and '{paragraph_id}' is not a "
                "paragraph id. For table figures, pass the cell id with quote=null."
            )
        if _normalize_text(quote) not in _normalize_text(text):
            return None, f"{quote!r} does not appear verbatim in paragraph '{paragraph_id}'."
        parsed = _parse_quote(quote)
        if isinstance(parsed, str):
            return None, parsed
        value, absolute, is_percent = parsed
        return (
            _Operand(
                id=paragraph_id,
                label=f"quoted from {paragraph_id}",
                raw_text=quote,
                value=value,
                absolute=absolute,
                is_percent=is_percent,
                from_text=True,
            ),
            None,
        )


def _input(operand: _Operand) -> dict[str, Any]:
    return {"id": operand.id, "label": operand.label, "value": operand.value, "raw_text": operand.raw_text}


def _resolve_pair(index: FigureIndex, a: Any, b: Any) -> tuple[tuple[float, float] | None, list[_Operand], str | None]:
    """Resolves both operands to values on a common scale.

    Two table cells are compared as printed (both in the report's unit), which keeps
    formulas readable. As soon as a prose figure is involved, both sides switch to
    actual units, since "$3.2 billion" and a cell reading 12,387 (millions) are only
    comparable once scaled.
    """
    first, error = index.resolve(a)
    if error:
        return None, [], error
    second, error = index.resolve(b)
    if error:
        return None, [], error
    if first.is_percent != second.is_percent:
        return None, [], "Can't combine a percentage with an amount."
    if first.from_text or second.from_text:
        return (first.absolute, second.absolute), [first, second], None
    return (first.value, second.value), [first, second], None


def _fmt(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e9:
        return f"{value / 1e9:,.2f} billion"
    if magnitude >= 1e6:
        return f"{value / 1e6:,.2f} million"
    return f"{value:g}"


def percent_change(index: FigureIndex, base: Any, current: Any) -> dict[str, Any]:
    values, operands, error = _resolve_pair(index, base, current)
    if error:
        return {"error": error}
    start, end = values
    if start == 0:
        return {"error": f"Cannot compute percent change from zero ({operands[0].label})."}

    change = (end - start) / abs(start) * 100
    return {
        "result_percent": round(change, 2),
        "formula": f"({_fmt(end)} - {_fmt(start)}) / |{_fmt(start)}| = {change:+.1f}%",
        "inputs": [_input(o) for o in operands],
    }


def ratio(index: FigureIndex, numerator: Any, denominator: Any) -> dict[str, Any]:
    values, operands, error = _resolve_pair(index, numerator, denominator)
    if error:
        return {"error": error}
    top, bottom = values
    if bottom == 0:
        return {"error": f"Cannot divide by zero ({operands[1].label})."}

    value = top / bottom
    return {
        "result": round(value, 4),
        "result_percent": round(value * 100, 2),
        "formula": f"{_fmt(top)} / {_fmt(bottom)} = {value * 100:.1f}%",
        "inputs": [_input(o) for o in operands],
    }


def difference(index: FigureIndex, minuend: Any, subtrahend: Any) -> dict[str, Any]:
    values, operands, error = _resolve_pair(index, minuend, subtrahend)
    if error:
        return {"error": error}
    a, b = values

    value = a - b
    return {
        "result": round(value, 4),
        "formula": f"{_fmt(a)} - {_fmt(b)} = {_fmt(value)}",
        "inputs": [_input(o) for o in operands],
    }


_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "percent_change": percent_change,
    "ratio": ratio,
    "difference": difference,
}

_OPERAND_SCHEMA_DESCRIPTION = (
    "A figure from the report. Table figure: {id: <cell id>, quote: null}. Figure that "
    "only appears in paragraph text: {id: <paragraph id>, quote: <the figure exactly as "
    "written there, e.g. '$3.2 billion' or '12%'>}."
)


def _operand_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "description": f"{description} {_OPERAND_SCHEMA_DESCRIPTION}",
        "properties": {
            "id": {"type": "string"},
            "quote": {"type": ["string", "null"]},
        },
        "required": ["id", "quote"],
        "additionalProperties": False,
    }


def _function_tool(name: str, description: str, operands: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {key: _operand_schema(desc) for key, desc in operands.items()},
            "required": list(operands),
            "additionalProperties": False,
        },
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _function_tool(
        "percent_change",
        "Percent change from one figure to another, e.g. year-over-year revenue growth, "
        "or the growth implied by next quarter's guidance. For changes in values that "
        "are already percentages (margins, rates), use `difference` instead to get the "
        "change in percentage points.",
        {"base": "The earlier/base figure.", "current": "The later figure."},
    ),
    _function_tool(
        "ratio",
        "One figure divided by another, e.g. gross margin (gross profit / revenue) or a "
        "segment's share of total revenue. Returns both the ratio and it as a percent.",
        {"numerator": "The numerator.", "denominator": "The denominator."},
    ),
    _function_tool(
        "difference",
        "minuend minus subtrahend, e.g. the absolute dollar increase in revenue, or the "
        "change in a margin in percentage points.",
        {"minuend": "The figure to subtract from.", "subtrahend": "The figure to subtract."},
    ),
]


def execute_tool(index: FigureIndex, name: str, arguments_json: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Runs one tool call. Returns (parsed arguments, output) - both go into the trace."""
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError:
        return {}, {"error": f"Arguments were not valid JSON: {arguments_json!r}"}
    if not isinstance(arguments, dict):
        return {}, {"error": "Arguments must be a JSON object."}

    tool = _TOOLS.get(name)
    if tool is None:
        return arguments, {"error": f"Unknown tool '{name}'."}
    try:
        return arguments, tool(index, **arguments)
    except TypeError as exc:  # wrong/missing argument names
        return arguments, {"error": f"Bad arguments for {name}: {exc}"}
