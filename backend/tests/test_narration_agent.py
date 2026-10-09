import json
from types import SimpleNamespace

import pytest

from app.models.narration import (
    FigureRef,
    LLMNarrationLine,
    LLMNarrationScript,
    LLMReview,
    LLMReviewIssue,
    NarrationLine,
)
from app.services import narration_agent
from app.services.narration_validator import NarrationQualityError


class _FakeItem:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def to_dict(self, **_kwargs):
        def dump(value):
            if isinstance(value, (_FakeItem, SimpleNamespace)):
                return {k: dump(v) for k, v in vars(value).items()}
            if isinstance(value, list):
                return [dump(v) for v in value]
            return value

        return dump(self)


def _web_search(query, urls):
    return _FakeItem(
        type="web_search_call",
        id=f"ws_{query}",
        status="completed",
        action=SimpleNamespace(type="search", query=query, queries=None, sources=[SimpleNamespace(type="url", url=u) for u in urls]),
    )


def _tool_call_response(*calls, searches=()):
    output = [_web_search(query, urls) for query, urls in searches] + [
        _FakeItem(type="function_call", call_id=f"call_{i}", name=name, arguments=json.dumps(args))
        for i, (name, args) in enumerate(calls)
    ]
    return SimpleNamespace(output=output, output_parsed=None, usage=SimpleNamespace(input_tokens=1000, output_tokens=50))


def _final_response(lines, searches=()):
    return SimpleNamespace(
        output=[_web_search(query, urls) for query, urls in searches] + [_FakeItem(type="message", content=[])],
        output_parsed=LLMNarrationScript(lines=lines),
        usage=SimpleNamespace(input_tokens=1200, output_tokens=800),
    )


class _FakeClient:
    """Stands in for the OpenAI client: returns scripted responses in order and records
    what each turn was called with."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.responses = self

    def parse(self, **kwargs):
        self.calls.append({**kwargs, "input": list(kwargs["input"])})
        return self._responses.pop(0)


def _line(text, target_id, source_urls=(), chart_id=None, chart_emphasis=None, figures=()):
    return LLMNarrationLine(
        text=text,
        target_id=target_id,
        source_urls=list(source_urls),
        figures=[FigureRef(**figure) for figure in figures],
        chart_id=chart_id,
        chart_emphasis=chart_emphasis,
    )


REVENUE_THIS_YEAR = {"id": "t_income__r0_q2", "quote": None}
REVENUE_LAST_YEAR = {"id": "t_income__r0_q2_ly", "quote": None}
REVENUE_GROWTH = ("percent_change", {"base": REVENUE_LAST_YEAR, "current": REVENUE_THIS_YEAR})
REVENUE_INCREASE = ("difference", {"minuend": REVENUE_THIS_YEAR, "subtrahend": REVENUE_LAST_YEAR})

GOOD_LINES = [
    _line("Revenue doubled.", "t_income__r0_q2"),
    _line("That's the headline.", "t_income"),
]


def _has_web_search(call):
    return any(tool.get("type") == "web_search" for tool in call["tools"])


def test_runs_tools_then_returns_script_with_trace(report):
    client = _FakeClient(
        [
            _tool_call_response(REVENUE_GROWTH),
            _final_response(GOOD_LINES),
        ]
    )

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert lines == [
        NarrationLine(text="Revenue doubled.", target_id="t_income__r0_q2"),
        NarrationLine(text="That's the headline.", target_id="t_income"),
    ]
    assert len(trace.turns) == 2
    assert trace.turns[0].tool_calls[0].output["result_percent"] == 100.0
    assert trace.total_input_tokens == 2200
    assert trace.repaired_target_ids == 0


def test_tool_results_are_fed_back_on_the_next_turn(report):
    client = _FakeClient(
        [
            _tool_call_response(REVENUE_INCREASE),
            _final_response(GOOD_LINES),
        ]
    )

    narration_agent.generate_narration(report, client=client)

    second_turn_input = client.calls[1]["input"]
    call_item = next(i for i in second_turn_input if i.get("type") == "function_call")
    output_item = next(i for i in second_turn_input if i.get("type") == "function_call_output")
    assert output_item["call_id"] == call_item["call_id"]
    assert json.loads(output_item["output"])["result"] == 100


def test_last_turn_forbids_tools(report, monkeypatch):
    monkeypatch.setattr(narration_agent, "MAX_TURNS", 3)
    calc = REVENUE_INCREASE
    client = _FakeClient([_tool_call_response(calc), _tool_call_response(calc), _final_response(GOOD_LINES)])

    narration_agent.generate_narration(report, client=client)

    assert [c["tool_choice"] for c in client.calls] == ["auto", "auto", "none"]
    assert not _has_web_search(client.calls[-1])


def test_never_finishing_raises(report, monkeypatch):
    monkeypatch.setattr(narration_agent, "MAX_TURNS", 2)
    calc = REVENUE_INCREASE
    client = _FakeClient([_tool_call_response(calc), _tool_call_response(calc)])

    with pytest.raises(NarrationQualityError):
        narration_agent.generate_narration(report, client=client)


def test_tool_budget_is_enforced(report, monkeypatch):
    monkeypatch.setattr(narration_agent, "MAX_TOOL_CALLS", 1)
    calc = REVENUE_INCREASE
    client = _FakeClient([_tool_call_response(calc, calc), _final_response(GOOD_LINES)])

    _, trace = narration_agent.generate_narration(report, client=client)

    outputs = [t.output for t in trace.turns[0].tool_calls]
    assert "result" in outputs[0]
    assert "budget exhausted" in outputs[1]["error"]


def test_invented_target_ids_are_repaired(report):
    lines_in = GOOD_LINES + [_line("Margins too.", "t_income__r1_bogus")]
    client = _FakeClient([_final_response(lines_in)])

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert lines[-1].target_id == "t_income__r1"
    assert trace.repaired_target_ids == 1


REVENUE_BARS = (
    "bar_chart",
    {
        "title": "Revenue",
        "items": [
            {"label": "Last year", "figure": REVENUE_LAST_YEAR},
            {"label": "This year", "figure": REVENUE_THIS_YEAR},
        ],
    },
)


def test_a_line_shows_the_chart_built_for_it(report):
    client = _FakeClient(
        [
            _tool_call_response(REVENUE_BARS),
            _final_response(
                [
                    _line("Revenue doubled.", "t_income__r0", chart_id="chart_1", chart_emphasis="i2"),
                    _line("That's the headline.", "t_income"),
                ]
            ),
        ]
    )

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert trace.turns[0].tool_calls[0].output["chart_id"] == "chart_1"
    assert lines[0].visual.emphasis == "i2"
    assert [item.value for item in lines[0].visual.chart.items] == [100, 200]
    assert lines[1].visual is None
    assert trace.removed_visuals == []


def test_a_chart_that_failed_its_checks_is_not_shown(report):
    # Two bars is the minimum, so this call is rejected and no chart_1 exists.
    one_bar = ("bar_chart", {"title": "Revenue", "items": [{"label": "This year", "figure": REVENUE_THIS_YEAR}]})
    client = _FakeClient(
        [
            _tool_call_response(one_bar),
            _final_response([_line("Revenue doubled.", "t_income__r0", chart_id="chart_1")]),
        ]
    )

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert "error" in trace.turns[0].tool_calls[0].output
    assert lines[0].text == "Revenue doubled."
    assert lines[0].visual is None
    assert [(r.line, r.chart_id, r.reason) for r in trace.removed_visuals] == [(1, "chart_1", "unknown_chart")]


def test_chart_tools_are_offered_alongside_the_calculation_tools(report):
    client = _FakeClient([_final_response(GOOD_LINES)])

    narration_agent.generate_narration(report, client=client)

    names = {tool.get("name") for tool in client.calls[0]["tools"]}
    assert {"percent_change", "bar_chart", "share_bar", "waterfall"} <= names


def test_report_is_rendered_into_the_first_turn(report):
    client = _FakeClient([_final_response(GOOD_LINES)])

    narration_agent.generate_narration(report, client=client)

    assert "[t_income__r0] Revenue" in client.calls[0]["input"][0]["content"]


def test_web_searches_are_traced(report):
    client = _FakeClient(
        [
            _tool_call_response(REVENUE_GROWTH, searches=[("acme q2 revenue jump", ["https://news.example/acme"])]),
            _final_response(GOOD_LINES),
        ]
    )

    _, trace = narration_agent.generate_narration(report, client=client)

    search = trace.turns[0].web_searches[0]
    assert (search.action, search.query, search.sources) == ("search", "acme q2 revenue jump", ["https://news.example/acme"])
    assert trace.total_web_searches == 1
    assert client.calls[0]["include"] == ["web_search_call.action.sources"]


def test_web_search_fee_is_added_to_turn_cost(report):
    plain = _FakeClient([_tool_call_response(REVENUE_GROWTH), _final_response(GOOD_LINES)])
    searched = _FakeClient(
        [
            _tool_call_response(REVENUE_GROWTH, searches=[("q1", ["https://a.example"]), ("q2", ["https://b.example"])]),
            _final_response(GOOD_LINES),
        ]
    )

    _, plain_trace = narration_agent.generate_narration(report, client=plain)
    _, searched_trace = narration_agent.generate_narration(report, client=searched)

    # Same token usage in both runs, so the difference is exactly two search fees.
    assert searched_trace.turns[0].cost_usd - plain_trace.turns[0].cost_usd == pytest.approx(0.02)


def test_only_urls_returned_by_searches_survive_as_sources(report):
    lines_in = [
        _line("Demand surged, per news coverage.", "t_income__r0", ["https://news.example/acme?utm_source=openai"]),
        _line("Analysts cheered.", "t_income", ["https://made-up.example/story"]),
    ]
    client = _FakeClient([_final_response(lines_in, searches=[("acme demand", ["https://news.example/acme"])])])

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert lines[0].sources == ["https://news.example/acme"]
    assert lines[1].sources == []
    assert trace.dropped_source_urls == 1
    assert [(r.line, r.url, r.reason) for r in trace.removed_sources] == [
        (2, "https://made-up.example/story", "unverified")
    ]


def test_blocked_site_sources_are_counted_in_the_trace(report):
    lines_in = [_line("People online were excited.", "t_income", ["https://www.reddit.com/r/stocks/1"])]
    client = _FakeClient([_final_response(lines_in, searches=[("acme", ["https://www.reddit.com/r/stocks/1"])])])

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert lines[0].sources == []
    assert (trace.dropped_source_urls, trace.blocked_source_urls) == (0, 1)


def test_search_tool_is_withdrawn_once_the_budget_is_used(report, monkeypatch):
    monkeypatch.setattr(narration_agent, "MAX_WEB_SEARCHES", 2)
    two_searches = [("q1", ["https://a.example"]), ("q2", ["https://b.example"])]
    client = _FakeClient(
        [
            _tool_call_response(REVENUE_GROWTH, searches=two_searches),
            _final_response(GOOD_LINES),
        ]
    )

    narration_agent.generate_narration(report, client=client)

    assert _has_web_search(client.calls[0]) and client.calls[0]["max_tool_calls"] == 2
    assert not _has_web_search(client.calls[1]) and "max_tool_calls" not in client.calls[1]


def test_search_sources_are_not_fed_back_as_input(report):
    client = _FakeClient(
        [
            _tool_call_response(REVENUE_GROWTH, searches=[("acme", ["https://news.example/acme"])]),
            _final_response(GOOD_LINES),
        ]
    )

    narration_agent.generate_narration(report, client=client)

    search_item = next(i for i in client.calls[1]["input"] if i.get("type") == "web_search_call")
    assert search_item["action"] == {"type": "search", "query": "acme", "queries": None}


def _review_response(*issues):
    return SimpleNamespace(
        output=[],
        output_parsed=LLMReview(issues=[LLMReviewIssue(line=line, problem=problem) for line, problem in issues]),
        usage=SimpleNamespace(input_tokens=400, output_tokens=20),
    )


def _revenue_line(text):
    return _line(text, "t_income__r0_q2", figures=[REVENUE_THIS_YEAR])


RIGHT = _revenue_line("Revenue was $200 million.")
WRONG = _revenue_line("Revenue was $150 million.")
CLOSING = _line("That's the headline.", "t_income")


def test_a_script_whose_figures_check_out_is_reviewed_once_and_left_alone(report):
    client = _FakeClient([_final_response([RIGHT, CLOSING]), _review_response()])

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert [line.text for line in lines] == ["Revenue was $200 million.", "That's the headline."]
    assert lines[0].figures == [FigureRef(**REVENUE_THIS_YEAR)]
    assert len(trace.turns) == 1
    review = trace.review
    assert [(r.lines, r.figures_confirmed, r.findings) for r in review.rounds] == [(2, 1, [])]
    assert review.removed_lines == []
    # The reviewer reads each line next to the label of what it cites, not the report.
    review_call = client.calls[1]
    assert review_call["text_format"] is LLMReview
    assert 'Line 1: "Revenue was $200 million."' in review_call["input"][0]["content"]
    assert "Revenue · Q2 FY26 = 200" in review_call["input"][0]["content"]
    assert "Line 2" not in review_call["input"][0]["content"]
    # Its call is part of what the run cost.
    assert trace.total_input_tokens == 1200 + 400
    assert review.reviewer_input_tokens == 400


def test_a_figure_that_does_not_match_is_sent_back_and_fixed(report):
    client = _FakeClient([_final_response([WRONG, CLOSING]), _review_response(), _final_response([RIGHT, CLOSING])])

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert [line.text for line in lines] == ["Revenue was $200 million.", "That's the headline."]
    assert [turn.purpose for turn in trace.turns] == ["draft", "correction"]
    correction = client.calls[2]
    assert correction["tool_choice"] == "none" and not _has_web_search(correction)
    request = correction["input"][-1]["content"]
    assert 'Line 1: "Revenue was $150 million."' in request
    assert "[MUST FIX] '$150 million' matches none of the figures the line cites" in request
    # The draft itself is in the conversation the correction continues.
    assert any(item.get("type") == "message" for item in correction["input"])
    review = trace.review
    assert [[f.check for f in r.findings] for r in review.rounds] == [["figure_mismatch"], []]
    assert review.removed_lines == []


def test_a_figure_still_wrong_after_every_correction_is_cut(report):
    draft = [RIGHT, WRONG, CLOSING]
    client = _FakeClient([_final_response(draft), _review_response(), _final_response(draft), _final_response(draft)])

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert [line.text for line in lines] == ["Revenue was $200 million.", "That's the headline."]
    assert [turn.purpose for turn in trace.turns] == ["draft", "correction", "correction"]
    assert "last pass" not in client.calls[2]["input"][-1]["content"]
    assert "last pass" in client.calls[3]["input"][-1]["content"]
    assert len(trace.review.rounds) == 3
    assert [removed.text for removed in trace.review.removed_lines] == ["Revenue was $150 million."]


def test_the_reviewers_advice_gets_one_correction_turn_and_never_cuts_a_line(report):
    script = [RIGHT, CLOSING]
    client = _FakeClient(
        [
            _final_response(script),
            _review_response((1, "The sentence presents last year's revenue as this year's."), (9, "No such line.")),
            _final_response(script),  # the agent looked again and kept its line
        ]
    )

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert [line.text for line in lines] == ["Revenue was $200 million.", "That's the headline."]
    assert "[CHECK] The sentence presents last year's revenue as this year's." in client.calls[2]["input"][-1]["content"]
    findings = trace.review.rounds[0].findings
    assert [(f.line, f.check, f.must_fix) for f in findings] == [(1, "reviewer", False)]
    assert len(trace.turns) == 2  # advice is not worth a second correction
    assert trace.review.removed_lines == []


def test_a_failed_review_call_does_not_cost_the_script(report):
    class _NoReviewer(_FakeClient):
        def parse(self, **kwargs):
            if kwargs["text_format"] is LLMReview:
                raise RuntimeError("review unavailable")
            return super().parse(**kwargs)

    lines, trace = narration_agent.generate_narration(report, client=_NoReviewer([_final_response([RIGHT, CLOSING])]))

    assert len(lines) == 2
    assert trace.review.reviewer_input_tokens is None
    assert trace.review.rounds[0].figures_confirmed == 1


def test_a_script_that_loses_most_of_its_lines_is_rejected(report):
    draft = [WRONG, _revenue_line("Up from $90 million."), CLOSING]
    client = _FakeClient([_final_response(draft), _review_response(), _final_response(draft), _final_response(draft)])

    with pytest.raises(NarrationQualityError, match="2 of 3"):
        narration_agent.generate_narration(report, client=client)
