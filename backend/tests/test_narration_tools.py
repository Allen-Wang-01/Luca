import json

from app.services.narration_tools import FigureIndex, TOOL_DEFINITIONS, execute_tool


def cell(cell_id):
    return {"id": cell_id, "quote": None}


def quoted(paragraph_id, quote):
    return {"id": paragraph_id, "quote": quote}


def _run(report, name, **arguments):
    _, output = execute_tool(FigureIndex(report), name, json.dumps(arguments))
    return output


def test_percent_change_looks_up_values_by_cell_id(report):
    output = _run(report, "percent_change", base=cell("t_income__r0_q2_ly"), current=cell("t_income__r0_q2"))

    assert output["result_percent"] == 100.0
    assert [i["label"] for i in output["inputs"]] == ["Revenue · Q2 FY25", "Revenue · Q2 FY26"]


def test_ratio_returns_fraction_and_percent(report):
    output = _run(report, "ratio", numerator=cell("t_income__r1_q2"), denominator=cell("t_income__r0_q2"))

    assert output["result"] == 0.75
    assert output["result_percent"] == 75.0


def test_difference(report):
    output = _run(report, "difference", minuend=cell("t_income__r0_q2"), subtrahend=cell("t_income__r0_q2_ly"))

    assert output["result"] == 100


def test_quoted_prose_figure_is_scaled_to_match_table_units(report):
    # "$0.3 billion" of guidance vs. a table cell of 200 (millions): +50%, not a
    # nonsensical comparison of 0.3 against 200.
    output = _run(
        report,
        "percent_change",
        base=cell("t_income__r0_q2"),
        current=quoted("p_outlook", "$0.3 billion"),
    )

    assert output["result_percent"] == 50.0
    assert output["inputs"][1]["raw_text"] == "$0.3 billion"


def test_quote_must_appear_verbatim_in_the_paragraph(report):
    output = _run(
        report,
        "percent_change",
        base=cell("t_income__r0_q2"),
        current=quoted("p_outlook", "$0.4 billion"),
    )

    assert "does not appear verbatim" in output["error"]


def test_quote_must_contain_exactly_one_figure(report):
    output = _run(
        report,
        "ratio",
        numerator=quoted("p_outlook", "$0.3 billion, plus or minus 2%"),
        denominator=cell("t_income__r0_q2"),
    )

    assert "exactly one figure" in output["error"]


def test_quote_is_only_for_paragraphs(report):
    output = _run(report, "difference", minuend=quoted("t_income__r0_q2", "200"), subtrahend=cell("t_income__r0_q2"))

    assert "not a paragraph id" in output["error"]


def test_paragraph_without_quote_explains_the_fix(report):
    output = _run(report, "difference", minuend=cell("p_outlook"), subtrahend=cell("t_income__r0_q2"))

    assert "also pass `quote`" in output["error"]


def test_percentage_and_amount_cannot_be_combined(report):
    output = _run(report, "difference", minuend=quoted("p_outlook", "2%"), subtrahend=cell("t_income__r0_q2"))

    assert "percentage" in output["error"]


def test_row_id_instead_of_cell_id_explains_the_fix(report):
    output = _run(report, "percent_change", base=cell("t_income__r0"), current=cell("t_income__r0_q2"))

    assert "row id" in output["error"]


def test_unknown_cell_and_missing_value_are_errors_not_exceptions(report):
    assert "Unknown id" in _run(report, "difference", minuend=cell("nope"), subtrahend=cell("t_income__r0_q2"))["error"]
    assert "no numeric value" in _run(
        report, "difference", minuend=cell("t_income__r2_q2"), subtrahend=cell("t_income__r0_q2")
    )["error"]


def test_division_by_zero_is_an_error(report):
    assert "zero" in _run(
        report, "percent_change", base=cell("t_income__r1_q2_ly"), current=cell("t_income__r1_q2")
    )["error"]
    assert "zero" in _run(
        report, "ratio", numerator=cell("t_income__r0_q2"), denominator=cell("t_income__r1_q2_ly")
    )["error"]


def term(figure, sign="add"):
    return {"figure": figure, "sign": sign}


def test_combine_adds_and_subtracts_several_figures(report):
    output = _run(
        report,
        "combine",
        terms=[
            term(cell("t_income__r0_q2")),
            term(cell("t_income__r0_q2_ly")),
            term(cell("t_income__r1_q2"), "subtract"),
        ],
    )

    assert output["result"] == 150
    assert output["formula"] == "200 + 100 - 150 = 150"
    assert len(output["inputs"]) == 3


def test_combine_puts_table_and_prose_figures_on_one_scale(report):
    output = _run(
        report, "combine", terms=[term(quoted("p_outlook", "$0.3 billion")), term(cell("t_income__r0_q2"), "subtract")]
    )

    assert output["result"] == 100_000_000
    assert output["formula"] == "300.00 million - 200.00 million = 100.00 million"


def test_combine_rejects_bad_terms(report):
    revenue = term(cell("t_income__r0_q2"))

    assert "2 to" in _run(report, "combine", terms=[revenue])["error"]
    assert "sign" in _run(report, "combine", terms=[revenue, {"figure": cell("t_income__r0_q2_ly"), "sign": "plus"}])["error"]
    assert "Unknown id" in _run(report, "combine", terms=[revenue, term(cell("nope"))])["error"]
    assert "percentage" in _run(report, "combine", terms=[revenue, term(quoted("p_outlook", "2%"))])["error"]


def test_a_result_can_be_used_in_a_later_calculation(report):
    index = FigureIndex(report)
    arguments = {"minuend": cell("t_income__r0_q2"), "subtrahend": cell("t_income__r1_q2")}
    _, cost = execute_tool(index, "difference", json.dumps(arguments))

    _, share = execute_tool(
        index, "ratio", json.dumps({"numerator": cell(cost["calc_id"]), "denominator": cell("t_income__r0_q2")})
    )

    assert cost["calc_id"] == "calc_1"
    assert share["result_percent"] == 25.0
    assert share["inputs"][0]["id"] == "calc_1"


def test_a_result_keeps_its_scale_when_mixed_with_a_prose_figure(report):
    index = FigureIndex(report)
    arguments = {"minuend": cell("t_income__r0_q2"), "subtrahend": cell("t_income__r0_q2_ly")}
    _, added = execute_tool(index, "difference", json.dumps(arguments))  # 100 (millions)

    _, output = execute_tool(
        index,
        "ratio",
        json.dumps({"numerator": cell(added["calc_id"]), "denominator": quoted("p_outlook", "$0.3 billion")}),
    )

    assert output["result_percent"] == 33.33


def test_two_ratios_give_a_change_in_percentage_points(report):
    index = FigureIndex(report)
    margin = {"numerator": cell("t_income__r1_q2"), "denominator": cell("t_income__r0_q2")}  # 75%
    half = {"numerator": cell("t_income__r0_q2_ly"), "denominator": cell("t_income__r0_q2")}  # 50%
    _, first = execute_tool(index, "ratio", json.dumps(margin))
    _, second = execute_tool(index, "ratio", json.dumps(half))

    _, change = execute_tool(
        index, "difference", json.dumps({"minuend": cell(first["calc_id"]), "subtrahend": cell(second["calc_id"])})
    )
    _, mixed = execute_tool(
        index, "difference", json.dumps({"minuend": cell(first["calc_id"]), "subtrahend": cell("t_income__r0_q2")})
    )

    assert change["result"] == 25
    assert "percentage" in mixed["error"]


def test_a_failed_calculation_gets_no_id(report):
    index = FigureIndex(report)
    execute_tool(index, "difference", json.dumps({"minuend": cell("nope"), "subtrahend": cell("t_income__r0_q2")}))

    arguments = {"minuend": cell("t_income__r0_q2"), "subtrahend": cell("t_income__r0_q2_ly")}
    assert execute_tool(index, "difference", json.dumps(arguments))[1]["calc_id"] == "calc_1"


def test_malformed_calls_are_errors(report):
    index = FigureIndex(report)

    assert "error" in execute_tool(index, "percent_change", "not json")[1]
    assert "error" in execute_tool(index, "no_such_tool", "{}")[1]
    assert "error" in execute_tool(index, "ratio", json.dumps({"wrong": "args"}))[1]
    assert "error" in execute_tool(index, "ratio", json.dumps({"numerator": "t_income__r0_q2", "denominator": "x"}))[1]


def test_every_defined_tool_is_executable(report):
    index = FigureIndex(report)
    for definition in TOOL_DEFINITIONS:
        _, output = execute_tool(index, definition["name"], "{}")
        assert "Unknown tool" not in output.get("error", "")
