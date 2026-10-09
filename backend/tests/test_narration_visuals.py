import json

from app.services.narration_tools import FigureIndex
from app.services.narration_visuals import MAX_CHARTS, TOOL_DEFINITIONS, ChartBuilder, execute_tool

REVENUE = {"id": "t_income__r0_q2", "quote": None}  # 200 (millions)
REVENUE_LAST_YEAR = {"id": "t_income__r0_q2_ly", "quote": None}  # 100
GROSS_PROFIT = {"id": "t_income__r1_q2", "quote": None}  # 150
GUIDANCE = {"id": "p_outlook", "quote": "$0.3 billion"}


def entry(label, figure, operation=None):
    item = {"label": label, "figure": figure}
    return {**item, "operation": operation} if operation else item


def _run(builder, name, **arguments):
    _, output = execute_tool(builder, name, json.dumps(arguments))
    return output


def _builder(report):
    return ChartBuilder(FigureIndex(report))


def test_bar_chart_looks_up_values_and_keys_its_items(report):
    builder = _builder(report)

    output = _run(
        builder, "bar_chart", title="Revenue", items=[entry("Last year", REVENUE_LAST_YEAR), entry("This year", REVENUE)]
    )

    assert output["chart_id"] == "chart_1"
    assert output["unit"] == "millions"
    assert [(i["key"], i["label"], i["value"]) for i in output["items"]] == [
        ("i1", "Last year", 100),
        ("i2", "This year", 200),
    ]
    chart = builder.charts["chart_1"]
    assert chart.type == "bar"
    assert chart.items[1].source_id == "t_income__r0_q2"
    assert chart.items[1].raw_text == "200"


def test_a_chart_does_not_take_calculation_results(report):
    builder = _builder(report)
    result = builder.index.record("200 - 100 = 100", 100, 100e6, [], is_percent=False)

    output = _run(
        builder, "bar_chart", title="Revenue", items=[entry("Added", {"id": result, "quote": None}), entry("This year", REVENUE)]
    )

    assert "calculation results" in output["error"]
    assert builder.charts == {}


def test_table_and_prose_figures_share_one_scale(report):
    output = _run(
        _builder(report), "bar_chart", title="Revenue", items=[entry("This quarter", REVENUE), entry("Guidance", GUIDANCE)]
    )

    assert output["unit"] == "millions"
    assert [i["value"] for i in output["items"]] == [200, 300]


def test_share_bar_puts_the_total_last(report):
    builder = _builder(report)

    output = _run(
        builder, "share_bar", title="Margin", total=entry("Revenue", REVENUE), parts=[entry("Gross profit", GROSS_PROFIT)]
    )

    assert [(i["key"], i["value"]) for i in output["items"]] == [("i1", 150), ("total", 200)]
    assert [i.role for i in builder.charts[output["chart_id"]].items] == ["item", "total"]


def test_share_bar_parts_cannot_exceed_the_total(report):
    builder = _builder(report)

    output = _run(
        builder, "share_bar", title="Margin", total=entry("Gross profit", GROSS_PROFIT), parts=[entry("Revenue", REVENUE)]
    )

    assert "more than the total" in output["error"]
    assert builder.charts == {}


def test_waterfall_steps_are_signed_by_their_operation(report):
    builder = _builder(report)

    output = _run(
        builder,
        "waterfall",
        title="Bridge",
        start=entry("Guidance", GUIDANCE),
        steps=[entry("Less last year", REVENUE_LAST_YEAR, "subtract")],
        end=entry("Revenue", REVENUE),
    )

    assert [(i["key"], i["value"]) for i in output["items"]] == [("start", 300), ("i1", -100), ("end", 200)]
    assert [i.role for i in builder.charts[output["chart_id"]].items] == ["start", "item", "end"]


def test_waterfall_must_lead_from_start_to_end(report):
    builder = _builder(report)

    output = _run(
        builder,
        "waterfall",
        title="Bridge",
        start=entry("Revenue", REVENUE),
        steps=[entry("Less last year", REVENUE_LAST_YEAR, "subtract")],
        end=entry("Gross profit", GROSS_PROFIT),
    )

    assert "don't lead from the start to the end" in output["error"]
    assert builder.charts == {}


def test_rounding_of_a_prose_figure_is_tolerated(report):
    # "$0.3 billion" is only printed to the nearest 100 million, so 150 + 100 = 250
    # million is within what it could have been rounded from - but not 150 alone.
    builder = _builder(report)
    bridge = dict(title="Bridge", start=entry("Gross profit", GROSS_PROFIT), end=entry("Guidance", GUIDANCE))

    close = _run(builder, "waterfall", steps=[entry("Last year", REVENUE_LAST_YEAR, "add")], **bridge)
    far = _run(builder, "waterfall", steps=[entry("Nothing", {"id": "t_income__r1_q2_ly", "quote": None}, "add")], **bridge)

    assert "chart_id" in close
    assert "error" in far


def test_unresolvable_figure_names_the_item(report):
    builder = _builder(report)

    output = _run(
        builder, "bar_chart", title="Revenue", items=[entry("This year", REVENUE), entry("Mystery", {"id": "nope", "quote": None})]
    )

    assert "Mystery" in output["error"] and "Unknown id" in output["error"]
    assert builder.charts == {}


def test_percentages_and_amounts_cannot_share_a_chart(report):
    output = _run(
        _builder(report),
        "bar_chart",
        title="Mixed",
        items=[entry("Revenue", REVENUE), entry("Range", {"id": "p_outlook", "quote": "2%"})],
    )

    assert "percentages and amounts" in output["error"]


def test_malformed_calls_are_errors(report):
    builder = _builder(report)

    assert "error" in _run(builder, "bar_chart", title="One bar", items=[entry("This year", REVENUE)])
    assert "error" in _run(builder, "bar_chart", title="", items=[entry("A", REVENUE), entry("B", REVENUE)])
    assert "error" in _run(builder, "bar_chart", title="No label", items=[{"figure": REVENUE}, entry("B", REVENUE)])
    assert "error" in _run(
        builder,
        "waterfall",
        title="No operation",
        start=entry("A", REVENUE),
        steps=[entry("B", REVENUE)],
        end=entry("C", REVENUE),
    )
    assert "error" in execute_tool(builder, "bar_chart", "not json")[1]


def test_chart_count_is_capped(report):
    builder = _builder(report)
    bars = dict(title="Revenue", items=[entry("Last year", REVENUE_LAST_YEAR), entry("This year", REVENUE)])

    outputs = [_run(builder, "bar_chart", **bars) for _ in range(MAX_CHARTS + 1)]

    assert all("chart_id" in output for output in outputs[:-1])
    assert "limit" in outputs[-1]["error"]
    assert len(builder.charts) == MAX_CHARTS


def test_every_defined_tool_is_executable(report):
    builder = _builder(report)
    for definition in TOOL_DEFINITIONS:
        _, output = execute_tool(builder, definition["name"], "{}")
        assert "Unknown tool" not in output.get("error", "")
