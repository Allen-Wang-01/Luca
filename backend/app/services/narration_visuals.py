# Chart tools the narration model can call to illustrate a line. Like the calculation
# tools (narration_tools.py), every figure is a reference into the report - a cell id,
# or a paragraph id plus the figure as written there - so the model chooses the chart
# type, the labels and which figures go in, but never writes a value. Each chart is
# also checked against itself before it gets an id: a waterfall's steps must lead from
# its start to its end, a share bar's parts can't add up to more than the whole. A chart
# that fails is returned as an {"error": ...} tool output, which the model can read and
# correct, and never reaches the listener. No I/O.
from typing import Any, Callable

from app.models.narration import Visual, VisualItem
from app.services.narration_tools import FigureIndex, _Operand, call_tool, operand_schema

# A card is read in the few seconds its line takes to speak.
MAX_BARS = 8
MAX_PARTS = 6
MAX_STEPS = 8
# Per script. Every chart is a tool call, and a card on every other line stops being
# a highlight.
MAX_CHARTS = 8

_UNITS: list[tuple[float, str]] = [(1e9, "billions"), (1e6, "millions"), (1e3, "thousands")]


class ChartBuilder:
    """Holds the charts built during one narration run, by id."""

    def __init__(self, index: FigureIndex) -> None:
        self.index = index
        self.charts: dict[str, Visual] = {}

    def add(self, chart_type: str, title: str, unit: str | None, items: list[VisualItem]) -> dict[str, Any]:
        chart = Visual(id=f"chart_{len(self.charts) + 1}", type=chart_type, title=title.strip(), unit=unit, items=items)
        self.charts[chart.id] = chart
        return {
            "chart_id": chart.id,
            "type": chart.type,
            "unit": chart.unit,
            "items": [
                {"key": item.key, "label": item.label, "value": item.value, "raw_text": item.raw_text}
                for item in items
            ],
        }


def _resolve(builder: ChartBuilder, title: Any, entries: list[Any]) -> tuple[list[tuple[str, _Operand]], str | None]:
    """Looks up every entry's figure. Returns ([(label, operand)], error)."""
    if len(builder.charts) >= MAX_CHARTS:
        return [], f"Chart limit reached ({MAX_CHARTS}). Use the charts you already have."
    if not isinstance(title, str) or not title.strip():
        return [], "`title` must be a short, non-empty string."

    resolved: list[tuple[str, _Operand]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("label"), str) or not entry["label"].strip():
            return [], f"Each item must be an object with a non-empty `label` and a `figure`, got {entry!r}."
        operand, error = builder.index.resolve(entry.get("figure"))
        if error:
            return [], f"Item '{entry['label']}': {error}"
        if operand.computed:
            # A card shows where each figure sits in the report; a result has no such place.
            return [], f"Item '{entry['label']}': a chart only takes figures from the report, not calculation results."
        resolved.append((entry["label"].strip(), operand))

    if len({operand.is_percent for _, operand in resolved}) > 1:
        return [], "Can't put percentages and amounts in the same chart."
    return resolved, None


def _scale(operands: list[_Operand]) -> tuple[float, str | None]:
    """The (divisor, unit) the chart's values are shown in, from its largest figure."""
    if operands[0].is_percent:
        return 1, "percent"
    largest = max(abs(operand.absolute) for operand in operands)
    return next(((factor, unit) for factor, unit in _UNITS if largest >= factor), (1, None))


def _show(absolute: float, divisor: float, unit: str | None) -> str:
    text = f"{round(absolute / divisor, 4):,g}"
    # "billions" names the chart's scale; a single figure reads "48.5 billion".
    return f"{text}%" if unit == "percent" else f"{text} {unit.removesuffix('s')}" if unit else text


def _item(key: str, label: str, operand: _Operand, role: str, divisor: float, sign: int = 1) -> VisualItem:
    return VisualItem(
        key=key,
        label=label,
        value=round(sign * operand.absolute / divisor, 4),
        role=role,
        raw_text=operand.raw_text,
        source_id=operand.id,
    )


def bar_chart(builder: ChartBuilder, title: Any, items: Any) -> dict[str, Any]:
    if not isinstance(items, list) or not 2 <= len(items) <= MAX_BARS:
        return {"error": f"A bar chart needs 2 to {MAX_BARS} items."}
    resolved, error = _resolve(builder, title, items)
    if error:
        return {"error": error}

    divisor, unit = _scale([operand for _, operand in resolved])
    return builder.add(
        "bar",
        title,
        unit,
        [_item(f"i{n}", label, operand, "item", divisor) for n, (label, operand) in enumerate(resolved, start=1)],
    )


def share_bar(builder: ChartBuilder, title: Any, total: Any, parts: Any) -> dict[str, Any]:
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_PARTS:
        return {"error": f"A share bar needs 1 to {MAX_PARTS} parts."}
    resolved, error = _resolve(builder, title, [total, *parts])
    if error:
        return {"error": error}

    (total_label, whole), part_operands = resolved[0], resolved[1:]
    divisor, unit = _scale([operand for _, operand in resolved])
    if whole.is_percent:
        return {"error": "A share bar takes amounts, not percentages: pass the part and the whole it belongs to."}
    if whole.absolute <= 0:
        return {"error": f"The total must be positive, got {_show(whole.absolute, divisor, unit)}."}
    negative = next((label for label, operand in part_operands if operand.absolute < 0), None)
    if negative:
        return {"error": f"Part '{negative}' is negative, so it can't be drawn as a share of the total."}

    parts_sum = sum(operand.absolute for _, operand in part_operands)
    tolerance = sum(operand.precision for _, operand in resolved)
    if parts_sum > whole.absolute + tolerance:
        return {
            "error": (
                f"The parts add up to {_show(parts_sum, divisor, unit)}, more than the total of "
                f"{_show(whole.absolute, divisor, unit)}. Check that every part belongs to this total "
                "and that no part contains another."
            )
        }

    return builder.add(
        "share",
        title,
        unit,
        [
            *(_item(f"i{n}", label, operand, "item", divisor) for n, (label, operand) in enumerate(part_operands, start=1)),
            _item("total", total_label, whole, "total", divisor),
        ],
    )


def waterfall(builder: ChartBuilder, title: Any, start: Any, steps: Any, end: Any) -> dict[str, Any]:
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        return {"error": f"A waterfall needs 1 to {MAX_STEPS} steps."}
    operations = [step.get("operation") if isinstance(step, dict) else None for step in steps]
    if any(operation not in ("add", "subtract") for operation in operations):
        return {"error": "Each step needs an `operation`: 'add' or 'subtract'."}
    resolved, error = _resolve(builder, title, [start, *steps, end])
    if error:
        return {"error": error}

    (start_label, first), step_operands, (end_label, last) = resolved[0], resolved[1:-1], resolved[-1]
    signs = [1 if operation == "add" else -1 for operation in operations]
    divisor, unit = _scale([operand for _, operand in resolved])

    reached = first.absolute + sum(sign * operand.absolute for sign, (_, operand) in zip(signs, step_operands))
    tolerance = sum(operand.precision for _, operand in resolved)
    if abs(reached - last.absolute) > tolerance:
        return {
            "error": (
                f"The steps don't lead from the start to the end: {_show(first.absolute, divisor, unit)} with "
                f"the steps applied gives {_show(reached, divisor, unit)}, but the end figure is "
                f"{_show(last.absolute, divisor, unit)}. A step is missing, or one has the wrong operation - "
                "a figure printed as negative, e.g. (120), is already negative, so 'add' it to reduce the total."
            )
        }

    return builder.add(
        "waterfall",
        title,
        unit,
        [
            _item("start", start_label, first, "start", divisor),
            *(
                _item(f"i{n}", label, operand, "item", divisor, sign)
                for n, (sign, (label, operand)) in enumerate(zip(signs, step_operands), start=1)
            ),
            _item("end", end_label, last, "end", divisor),
        ],
    )


_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "bar_chart": bar_chart,
    "share_bar": share_bar,
    "waterfall": waterfall,
}

TOOL_NAMES = frozenset(_TOOLS)

_TITLE_SCHEMA = {"type": "string", "description": "Short title shown above the chart, e.g. 'Revenue by quarter'."}


def _entry_schema(description: str, with_operation: bool = False) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "label": {"type": "string", "description": "Short label shown next to the figure, e.g. 'Q3 2024'."},
        "figure": operand_schema("The figure to draw."),
    }
    if with_operation:
        properties["operation"] = {
            "type": "string",
            "enum": ["add", "subtract"],
            "description": (
                "How the figure, with the sign it is printed with, changes the running total. "
                "A cost printed as 400 is subtracted; an adjustment printed as (120) is negative "
                "already, so it is added."
            ),
        }
    return {
        "type": "object",
        "description": description,
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _chart_tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    properties = {"title": _TITLE_SCHEMA, **properties}
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _chart_tool(
        "bar_chart",
        f"Bars side by side: one metric across periods (revenue in each of the last three quarters), or "
        f"several items against each other (each region's sales). 2 to {MAX_BARS} items, all amounts or "
        "all percentages, in the order they should appear.",
        {"items": {"type": "array", "items": _entry_schema("One bar.")}},
    ),
    _chart_tool(
        "share_bar",
        f"One bar split into parts of a whole, e.g. how much of total revenue each segment brought in. "
        f"1 to {MAX_PARTS} parts; whatever they don't cover is drawn as an unlabelled remainder. The "
        "parts can't add up to more than the total.",
        {
            "total": _entry_schema("The whole the parts belong to."),
            "parts": {"type": "array", "items": _entry_schema("One part of the total.")},
        },
    ),
    _chart_tool(
        "waterfall",
        f"A bridge from one figure to another through the items in between, e.g. from revenue through "
        f"each cost down to operating income, or from a reported profit through each adjustment to the "
        f"adjusted one. 1 to {MAX_STEPS} steps. The start with every step applied must equal the end, "
        "so include every step the report lists between them.",
        {
            "start": _entry_schema("The figure the bridge starts from."),
            "steps": {"type": "array", "items": _entry_schema("One item added or subtracted.", with_operation=True)},
            "end": _entry_schema("The figure the bridge arrives at."),
        },
    ),
]


def execute_tool(builder: ChartBuilder, name: str, arguments_json: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Runs one chart tool call. Returns (parsed arguments, output) for the trace."""
    return call_tool(_TOOLS, builder, name, arguments_json)
