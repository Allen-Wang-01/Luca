import json
from types import SimpleNamespace

import pytest

from app.models.narration import LLMNarrationScript, NarrationLine
from app.services import narration_agent
from app.services.narration_validator import NarrationQualityError


class _FakeItem:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def to_dict(self, **_kwargs):
        return dict(self.__dict__)


def _tool_call_response(*calls):
    output = [
        _FakeItem(type="function_call", call_id=f"call_{i}", name=name, arguments=json.dumps(args))
        for i, (name, args) in enumerate(calls)
    ]
    return SimpleNamespace(output=output, output_parsed=None, usage=SimpleNamespace(input_tokens=1000, output_tokens=50))


def _final_response(lines):
    return SimpleNamespace(
        output=[_FakeItem(type="message", content=[])],
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


REVENUE_THIS_YEAR = {"id": "t_income__r0_q2", "quote": None}
REVENUE_LAST_YEAR = {"id": "t_income__r0_q2_ly", "quote": None}
REVENUE_GROWTH = ("percent_change", {"base": REVENUE_LAST_YEAR, "current": REVENUE_THIS_YEAR})
REVENUE_INCREASE = ("difference", {"minuend": REVENUE_THIS_YEAR, "subtrahend": REVENUE_LAST_YEAR})

GOOD_LINES = [
    NarrationLine(text="Revenue doubled.", target_id="t_income__r0_q2"),
    NarrationLine(text="That's the headline.", target_id="t_income"),
]


def test_runs_tools_then_returns_script_with_trace(report):
    client = _FakeClient(
        [
            _tool_call_response(REVENUE_GROWTH),
            _final_response(GOOD_LINES),
        ]
    )

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert lines == GOOD_LINES
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
    lines_in = GOOD_LINES + [NarrationLine(text="Margins too.", target_id="t_income__r1_bogus")]
    client = _FakeClient([_final_response(lines_in)])

    lines, trace = narration_agent.generate_narration(report, client=client)

    assert lines[-1].target_id == "t_income__r1"
    assert trace.repaired_target_ids == 1


def test_report_is_rendered_into_the_first_turn(report):
    client = _FakeClient([_final_response(GOOD_LINES)])

    narration_agent.generate_narration(report, client=client)

    assert "[t_income__r0] Revenue" in client.calls[0]["input"][0]["content"]
