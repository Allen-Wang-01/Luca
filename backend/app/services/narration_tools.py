# Calculation tools the narration model can call. Operands are references into the
# report, never bare numbers, so figures don't pass through the model's own
# transcription: a table figure is referenced by cell id and looked up here; a figure
# that only appears in prose (e.g. "$3.2 billion" in a headline bullet) is referenced
# by paragraph id plus the figure exactly as written, and is only used after checking
# that it really appears verbatim in that paragraph. Results name their sources, so the
# model can target the same cell in its narration. Every result also gets an id of its
# own (`calc_1`, ...) that a later call can pass as an operand, so a figure that takes
# two steps (a margin on a subtotal the report doesn't print) never needs the model's
# own arithmetic for the first one. No I/O.
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

# How many figures `combine` adds up in one call.
MAX_TERMS = 8

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
    # One unit of the last printed digit, in actual units ("$3.2 billion" -> 0.1
    # billion). How far a sum of printed figures may be off through rounding alone.
    precision: float
    # The result of an earlier calculation rather than a figure printed in the report.
    computed: bool = False


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).lower()


def _precision(raw_text: str, value: float, absolute: float) -> float:
    match = _NUMBER_RE.search(raw_text)
    if match is None or value == 0:
        return 0.0
    decimals = len(match.group().partition(".")[2])
    return 10**-decimals * abs(absolute / value)


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
        # Results of the calculations made so far in this run, by calc id.
        self._results: dict[str, _Operand] = {}
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
                    absolute = cell.value * (1 if unscaled else scale)
                    self._cells[cell.id] = _Operand(
                        id=cell.id,
                        label=label,
                        raw_text=cell.raw_text,
                        value=cell.value,
                        absolute=absolute,
                        is_percent=is_percent,
                        from_text=False,
                        precision=_precision(cell.raw_text, cell.value, absolute),
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
        if ref_id in self._results:
            return self._results[ref_id], None
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

    def record(self, formula: str, value: float, absolute: float, operands: list[_Operand], is_percent: bool) -> str:
        """Keeps a calculation's result so a later call can use it as an operand.

        `value` is on the scale the calculation ran on (see `_resolve_all`) and
        `absolute` is the same result in actual units; for a percentage they are equal.
        """
        calc_id = f"calc_{len(self._results) + 1}"
        self._results[calc_id] = _Operand(
            id=calc_id,
            label=formula,
            raw_text=f"{value:g}%" if is_percent else _fmt(value),
            value=value,
            absolute=absolute,
            is_percent=is_percent,
            from_text=not is_percent and _in_actual_units(operands),
            precision=0.0 if is_percent else sum(operand.precision for operand in operands),
            computed=True,
        )
        return calc_id

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
                precision=_precision(quote, value, absolute),
            ),
            None,
        )


def _input(operand: _Operand) -> dict[str, Any]:
    return {"id": operand.id, "label": operand.label, "value": operand.value, "raw_text": operand.raw_text}


def _resolve_all(index: FigureIndex, references: list[Any]) -> tuple[list[_Operand], str | None]:
    operands: list[_Operand] = []
    for reference in references:
        operand, error = index.resolve(reference)
        if error:
            return [], error
        operands.append(operand)
    if len({operand.is_percent for operand in operands}) > 1:
        return [], "Can't combine a percentage with an amount."
    return operands, None


def _in_actual_units(operands: list[_Operand]) -> bool:
    # Table cells are calculated with as printed (all in the report's unit), which
    # keeps formulas readable. As soon as a prose figure is involved, every operand
    # switches to actual units, since "$3.2 billion" and a cell reading 12,387
    # (millions) are only comparable once scaled.
    return any(operand.from_text for operand in operands)


def _values(operands: list[_Operand]) -> list[float]:
    """The operands' values on a common scale."""
    if _in_actual_units(operands):
        return [operand.absolute for operand in operands]
    return [operand.value for operand in operands]


def _fmt(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e9:
        return f"{value / 1e9:,.2f} billion"
    if magnitude >= 1e6:
        return f"{value / 1e6:,.2f} million"
    return f"{value:g}"


def percent_change(index: FigureIndex, base: Any, current: Any) -> dict[str, Any]:
    operands, error = _resolve_all(index, [base, current])
    if error:
        return {"error": error}
    start, end = _values(operands)
    if start == 0:
        return {"error": f"Cannot compute percent change from zero ({operands[0].label})."}

    change = (end - start) / abs(start) * 100
    formula = f"({_fmt(end)} - {_fmt(start)}) / |{_fmt(start)}| = {change:+.1f}%"
    return {
        "calc_id": index.record(formula, change, change, operands, is_percent=True),
        "result_percent": round(change, 2),
        "formula": formula,
        "inputs": [_input(o) for o in operands],
    }


def ratio(index: FigureIndex, numerator: Any, denominator: Any) -> dict[str, Any]:
    operands, error = _resolve_all(index, [numerator, denominator])
    if error:
        return {"error": error}
    top, bottom = _values(operands)
    if bottom == 0:
        return {"error": f"Cannot divide by zero ({operands[1].label})."}

    value = top / bottom
    formula = f"{_fmt(top)} / {_fmt(bottom)} = {value * 100:.1f}%"
    return {
        # Kept as a percentage, so two ratios can go into `difference` for the change
        # in percentage points.
        "calc_id": index.record(formula, value * 100, value * 100, operands, is_percent=True),
        "result": round(value, 4),
        "result_percent": round(value * 100, 2),
        "formula": formula,
        "inputs": [_input(o) for o in operands],
    }


def difference(index: FigureIndex, minuend: Any, subtrahend: Any) -> dict[str, Any]:
    operands, error = _resolve_all(index, [minuend, subtrahend])
    if error:
        return {"error": error}
    a, b = _values(operands)

    value = a - b
    formula = f"{_fmt(a)} - {_fmt(b)} = {_fmt(value)}"
    absolute = operands[0].absolute - operands[1].absolute
    return {
        "calc_id": index.record(formula, value, absolute, operands, is_percent=operands[0].is_percent),
        "result": round(value, 4),
        "formula": formula,
        "inputs": [_input(o) for o in operands],
    }


def combine(index: FigureIndex, terms: Any) -> dict[str, Any]:
    if not isinstance(terms, list) or not 2 <= len(terms) <= MAX_TERMS:
        return {"error": f"`terms` must be a list of 2 to {MAX_TERMS} figures."}
    for term in terms:
        if not isinstance(term, dict) or term.get("sign") not in ("add", "subtract"):
            return {"error": f"Each term must be an object with a `figure` and a `sign` of 'add' or 'subtract', got {term!r}."}
    operands, error = _resolve_all(index, [term["figure"] for term in terms])
    if error:
        return {"error": error}

    signs = [1 if term["sign"] == "add" else -1 for term in terms]
    values = _values(operands)
    value = sum(sign * v for sign, v in zip(signs, values))
    absolute = sum(sign * operand.absolute for sign, operand in zip(signs, operands))
    # A figure the report prints as negative keeps its brackets, so the formula shows
    # that adding it lowers the total.
    shown = [f"({_fmt(v)})" if v < 0 else _fmt(v) for v in values]
    formula = shown[0] if signs[0] == 1 else f"-{shown[0]}"
    for sign, text in zip(signs[1:], shown[1:]):
        formula += f" {'+' if sign == 1 else '-'} {text}"
    formula += f" = {_fmt(value)}"
    return {
        "calc_id": index.record(formula, value, absolute, operands, is_percent=operands[0].is_percent),
        "result": round(value, 4),
        "formula": formula,
        "inputs": [_input(o) for o in operands],
    }


_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "percent_change": percent_change,
    "ratio": ratio,
    "difference": difference,
    "combine": combine,
}

_OPERAND_SCHEMA_DESCRIPTION = (
    "A figure from the report. Table figure: {id: <cell id>, quote: null}. Figure that "
    "only appears in paragraph text: {id: <paragraph id>, quote: <the figure exactly as "
    "written there, e.g. '$3.2 billion' or '12%'>}. The result of an earlier "
    "calculation: {id: <its calc_id>, quote: null}."
)


def operand_schema(description: str) -> dict[str, Any]:
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
            "properties": {key: operand_schema(desc) for key, desc in operands.items()},
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
    {
        "type": "function",
        "name": "combine",
        "description": (
            "Adds and subtracts several figures in one go, for a total the report doesn't "
            "print, e.g. cash plus short-term investments minus debt. Each figure is used "
            "with the sign it is printed with: one shown in brackets, like a cash outflow "
            "of (1,250), is already negative, so 'add' it to take it off the total."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "terms": {
                    "type": "array",
                    "description": f"2 to {MAX_TERMS} figures, in the order they should appear in the formula.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "figure": operand_schema("The figure."),
                            "sign": {"type": "string", "enum": ["add", "subtract"]},
                        },
                        "required": ["figure", "sign"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["terms"],
            "additionalProperties": False,
        },
    },
]


def call_tool(
    tools: dict[str, Callable[..., dict[str, Any]]], subject: Any, name: str, arguments_json: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Runs `tools[name](subject, **arguments)`. Returns (parsed arguments, output) -
    both go into the trace."""
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError:
        return {}, {"error": f"Arguments were not valid JSON: {arguments_json!r}"}
    if not isinstance(arguments, dict):
        return {}, {"error": "Arguments must be a JSON object."}

    tool = tools.get(name)
    if tool is None:
        return arguments, {"error": f"Unknown tool '{name}'."}
    try:
        return arguments, tool(subject, **arguments)
    except TypeError as exc:  # wrong/missing argument names
        return arguments, {"error": f"Bad arguments for {name}: {exc}"}


def execute_tool(index: FigureIndex, name: str, arguments_json: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Runs one calculation tool call."""
    return call_tool(_TOOLS, index, name, arguments_json)
