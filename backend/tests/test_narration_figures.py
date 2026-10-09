from app.models.narration import CalculationTerm, FigureRef, LineCalculation, LLMNarrationLine
from app.services.narration_figures import check_line, check_script, spoken_figures
from app.services.narration_tools import FigureIndex, execute_tool

SALES = "t_ops__r1_q"  # 300 (millions), this quarter
SALES_LAST_YEAR = "t_ops__r1_q_ly"  # 250
PROFIT = "t_ops__r4_q"  # 50
PROFIT_LAST_YEAR = "t_ops__r4_q_ly"  # 40
PER_SHARE = "t_ops__r6_q"  # 2.5, per share
SHARES = "t_ops__r8_q"  # 20,000 (thousands)


def _line(text, *cited, target_id="t_ops", source_urls=(), calculations=()):
    figures = [FigureRef(id=c, quote=None) if isinstance(c, str) else FigureRef(id=c[0], quote=c[1]) for c in cited]
    return LLMNarrationLine(
        text=text,
        target_id=target_id,
        source_urls=list(source_urls),
        figures=figures,
        calculations=list(calculations),
        chart_id=None,
        chart_emphasis=None,
    )


def _calculation(operation, *terms):
    """Terms are cell ids, or (cell id, "subtract") for a term `combine` takes off."""
    return LineCalculation(
        operation=operation,
        terms=[
            CalculationTerm(id=t, quote=None, sign="add") if isinstance(t, str) else CalculationTerm(id=t[0], quote=None, sign=t[1])
            for t in terms
        ],
    )


def _checks(line, index):
    findings, confirmed, _ = check_line(1, line, index)
    return [(finding.check, finding.must_fix) for finding in findings], confirmed


def test_only_marked_numbers_count_as_stated_figures():
    text = "In the first 9 months to June 30, 2031, sales of $1,250 million grew 12.5%, to about 3.2 billion units."

    assert [(f.text, f.value, f.step, f.loose_step, f.is_percent) for f in spoken_figures(text)] == [
        ("$1,250 million", 1_250_000_000, 1_000_000, 10_000_000, False),
        ("12.5%", 12.5, 0.1, 0.1, True),
        ("3.2 billion", 3_200_000_000, 100_000_000, 100_000_000, False),
    ]


def test_percentages_can_be_written_out():
    assert [f.value for f in spoken_figures("Up 12 percent, or 3.5 percentage points.")] == [12, 3.5]


def test_a_figure_said_with_its_cells_rounding_is_confirmed(statement):
    index = FigureIndex(statement)

    assert _checks(_line("Sales reached about $0.3 billion.", SALES), index) == ([], 1)
    assert _checks(_line("Sales reached $300 million, from $250 million.", SALES, SALES_LAST_YEAR), index) == ([], 2)


def test_loose_rounding_passes_only_when_it_is_a_small_share_of_the_figure(statement):
    statement.blocks[0].rows[1].cells[0].value = 294  # sales, in millions
    index = FigureIndex(statement)

    assert _checks(_line("Sales were nearly $300 million.", SALES), index) == ([], 1)  # 2% off
    assert _checks(_line("Sales were about $0.3 billion.", SALES), index) == ([], 1)
    assert _checks(_line("Sales were $280 million.", SALES), index)[0] == [("figure_mismatch", True)]
    assert _checks(_line("Sales were $294.6 million.", SALES), index)[0] == [("figure_mismatch", True)]
    # 2.5 a share said as "$2.80": close in dollars, but an eighth of the figure.
    assert _checks(_line("That is $2.80 a share.", PER_SHARE), index)[0] == [("figure_mismatch", True)]


def test_per_share_and_share_count_figures_are_read_in_their_own_scale(statement):
    line = _line("That is $2.50 a share, on 20 million shares.", PER_SHARE, SHARES)

    assert _checks(line, FigureIndex(statement)) == ([], 2)


def test_a_number_that_is_not_among_the_cited_figures_must_be_fixed(statement):
    # The mistake this exists for: last year's profit read out as this year's. The
    # number is a real figure of the report, just not the one the line cites.
    line = _line("Sales were $300 million, against a profit of $40 million.", SALES, PROFIT)

    findings, confirmed, _ = check_line(1, line, FigureIndex(statement))

    assert [(f.check, f.must_fix) for f in findings] == [("figure_mismatch", True)]
    assert "'$40 million' matches none of the figures the line cites" in findings[0].detail
    assert "Net income · Three Months Ended · June 30, 2031 (50)" in findings[0].detail
    assert confirmed == 1


def test_a_figure_with_nothing_cited_must_be_fixed(statement):
    assert _checks(_line("Sales grew 20%."), FigureIndex(statement)) == ([("figure_mismatch", True)], 0)


def test_a_calculated_figure_is_cited_by_its_calc_id(statement):
    index = FigureIndex(statement)
    growth = {"base": {"id": SALES_LAST_YEAR, "quote": None}, "current": {"id": SALES, "quote": None}}
    import json

    _, output = execute_tool(index, "percent_change", json.dumps(growth))  # +20%

    assert _checks(_line("Sales grew 20%.", output["calc_id"]), index) == ([], 1)
    assert _checks(_line("Sales grew 25%.", output["calc_id"]), index)[0] == [("figure_mismatch", True)]


def test_a_figure_quoted_from_prose_is_checked_too(report):
    index = FigureIndex(report)

    assert _checks(_line("Guidance is $0.3 billion.", ("p_outlook", "$0.3 billion"), target_id="p_outlook"), index) == ([], 1)
    assert _checks(_line("Give or take 3%.", ("p_outlook", "2%"), target_id="p_outlook"), index)[0] == [
        ("figure_mismatch", True)
    ]


def test_a_reference_that_names_nothing_must_be_fixed(statement):
    checks, _ = _checks(_line("Sales held up.", "t_ops__r99_q"), FigureIndex(statement))

    assert checks == [("unknown_reference", True)]


def test_figures_on_a_line_with_web_sources_are_not_held_to_the_report(statement):
    line = _line("Analysts had expected $310 million.", source_urls=["https://news.example/a"])

    assert _checks(line, FigureIndex(statement)) == ([], 0)


def test_a_made_up_source_does_not_excuse_a_figure(statement):
    # The link is removed from the script later for not coming from any search; the
    # figure it was meant to back must not be left standing without it.
    index = FigureIndex(statement)
    line = _line("Analysts had expected $310 million.", source_urls=["https://news.example/made-up"])
    searched = {"https://news.example/a?utm_source=x", "https://www.reddit.com/r/stocks/1"}

    findings, _, _ = check_line(1, line, index, seen_urls=searched)

    assert [(f.check, f.must_fix) for f in findings] == [("figure_mismatch", True)]
    assert "https://news.example/made-up" in findings[0].detail
    real = _line("Analysts had expected $310 million.", source_urls=["https://news.example/a"])
    assert check_line(1, real, index, seen_urls=searched)[0] == []
    forum = _line("Analysts had expected $310 million.", source_urls=["https://www.reddit.com/r/stocks/1"])
    assert [f.check for f in check_line(1, forum, index, seen_urls=searched)[0]] == ["figure_mismatch"]


def test_a_cell_off_the_row_and_column_of_the_others_is_questioned(statement):
    # This quarter's sales against last year's profit: both numbers match what is
    # cited, so only the shape of the citation gives it away.
    line = _line("Sales were $300 million, against a profit of $40 million.", SALES, PROFIT_LAST_YEAR)

    findings, confirmed, _ = check_line(1, line, FigureIndex(statement))

    assert [(f.check, f.must_fix) for f in findings] == [("isolated_cell", False)]
    assert confirmed == 2


def test_comparisons_along_a_row_or_down_a_column_are_not_questioned(statement):
    index = FigureIndex(statement)
    along_row = _line("Sales rose to $300 million from $250 million.", SALES, SALES_LAST_YEAR)
    down_column = _line("Sales of $300 million left a profit of $50 million.", SALES, PROFIT)
    both = _line(
        "Sales rose to $300 million from $250 million, and profit was $40 million a year ago.",
        SALES,
        SALES_LAST_YEAR,
        PROFIT_LAST_YEAR,
    )

    assert [_checks(line, index)[0] for line in (along_row, down_column, both)] == [[], [], []]


def test_a_highlighted_cell_the_line_does_not_cite_is_questioned(statement):
    index = FigureIndex(statement)
    # Highlights last year's sales while talking about this year's profit.
    line = _line("Profit was $50 million.", PROFIT, target_id=SALES_LAST_YEAR)

    assert _checks(line, index)[0] == [("target_not_cited", False)]
    assert _checks(_line("Profit was $50 million.", PROFIT, target_id=PROFIT), index)[0] == []
    # A highlight in the same period as what the line cites is a choice, not a slip: a
    # line about profit may well point at the sales it came from.
    assert _checks(_line("Profit was $50 million.", PROFIT, target_id=SALES), index)[0] == []
    # A row or block target takes in every cell under it.
    assert _checks(_line("Profit was $50 million.", PROFIT, target_id="t_ops__r1"), index)[0] == []


def test_script_findings_carry_their_line_number(statement):
    lines = [_line("Sales were $300 million.", SALES), _line("Profit was $45 million.", PROFIT)]

    review_round = check_script(lines, FigureIndex(statement))

    assert [(f.line, f.check, f.text) for f in review_round.findings] == [
        (2, "figure_mismatch", "Profit was $45 million.")
    ]
    assert (review_round.lines, review_round.figures_confirmed) == (2, 1)


def test_a_line_can_carry_the_calculation_behind_a_figure(statement):
    index = FigureIndex(statement)
    added = _line("Sales rose by $50 million.", calculations=[_calculation("difference", SALES, SALES_LAST_YEAR)])
    grew = _line("Sales grew 20%.", calculations=[_calculation("percent_change", SALES_LAST_YEAR, SALES)])
    margin = _line("Profit was 16.7% of sales.", calculations=[_calculation("ratio", PROFIT, SALES)])
    left = _line(
        "Sales less profit, both years: $460 million.",
        calculations=[_calculation("combine", SALES, SALES_LAST_YEAR, (PROFIT, "subtract"), (PROFIT_LAST_YEAR, "subtract"))],
    )

    assert [_checks(line, index) for line in (added, grew, margin, left)] == [([], 1)] * 4


def test_the_line_has_to_say_what_its_calculation_comes_to(statement):
    # The model's own arithmetic was off: the calculation is done here, and the line
    # doesn't match it.
    line = _line("Sales rose by $60 million.", calculations=[_calculation("difference", SALES, SALES_LAST_YEAR)])

    findings, confirmed, formulas = check_line(1, line, FigureIndex(statement))

    assert [(f.check, f.must_fix) for f in findings] == [("figure_mismatch", True)]
    assert "300 - 250 = 50" in findings[0].detail
    assert formulas == ["300 - 250 = 50"]


def test_a_calculation_that_cannot_be_done_must_be_fixed(statement):
    index = FigureIndex(statement)
    unknown = _line("Sales rose.", calculations=[_calculation("difference", SALES, "t_ops__r99_q")])
    mixed = _line("Sales rose.", calculations=[_calculation("difference", SALES, SHARES)])
    one_term = _line("Sales rose.", calculations=[_calculation("ratio", SALES)])

    assert [_checks(line, index)[0] for line in (unknown, mixed, one_term)] == [[("calculation_error", True)]] * 3
    findings, _, _ = check_line(1, mixed, index)
    assert "different kinds" in findings[0].detail


def test_a_lines_calculations_leave_no_results_behind(statement):
    # A script is checked once per round; results kept each time would shift the ids
    # of the calculations the model made with the tools.
    import json

    index = FigureIndex(statement)
    lines = [_line("Sales rose by $50 million.", calculations=[_calculation("difference", SALES, SALES_LAST_YEAR)])]

    first = check_script(lines, index)
    second = check_script(lines, index)
    growth = {"base": {"id": SALES_LAST_YEAR, "quote": None}, "current": {"id": SALES, "quote": None}}
    _, output = execute_tool(index, "percent_change", json.dumps(growth))

    assert [(c.line, c.formula) for c in first.calculations] == [(1, "300 - 250 = 50")]
    assert first == second
    assert output["calc_id"] == "calc_1"


def test_a_calculation_can_use_an_earlier_tool_result(statement):
    import json

    index = FigureIndex(statement)
    ratio = lambda top, bottom: json.dumps(  # noqa: E731
        {"numerator": {"id": top, "quote": None}, "denominator": {"id": bottom, "quote": None}}
    )
    this_year = execute_tool(index, "ratio", ratio(PROFIT, SALES))[1]["calc_id"]  # 16.67%
    last_year = execute_tool(index, "ratio", ratio(PROFIT_LAST_YEAR, SALES_LAST_YEAR))[1]["calc_id"]  # 16%
    line = _line(
        "That is 0.7 percentage points more than a year ago.",
        calculations=[_calculation("difference", this_year, last_year)],
    )

    assert _checks(line, index) == ([], 1)
