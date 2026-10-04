import json
from types import SimpleNamespace

import pytest

from app.models.narration import LLMNarrationLine, LLMNarrationScript, NarrationLine
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


def _line(text, target_id, source_urls=()):
    return LLMNarrationLine(text=text, target_id=target_id, source_urls=list(source_urls))


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
