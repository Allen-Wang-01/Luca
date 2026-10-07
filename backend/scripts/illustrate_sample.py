# Adds hand-written charts to a saved narration, without calling any API. For
# previewing how charts look and behave against a script that already has speech: the
# lines' text is left untouched, so their saved audio clips still match.
#
# Usage: python scripts/illustrate_sample.py path/to/<name>.json path/to/charts.json
#          [--narration path/to/<name>.narration.json] [--version charts]
#
# charts.json holds the same tool calls the narration model would make, plus which
# lines show which chart:
#   {
#     "charts": [{"tool": "bar_chart", "arguments": {"title": ..., "items": [...]}}],
#     "lines": {"2": {"chart_id": "chart_1", "emphasis": "i2"}}
#   }
# The calls go through the real chart tools (app/services/narration_visuals.py) and the
# line references through the real validator, so a chart that doesn't hold up against
# the report is rejected here exactly as it would be in a real run. Charts get their ids
# in order (chart_1, chart_2, ...), counting only the ones that were accepted; each
# call's result is printed. The calls are added to the saved trace's first turn, so
# they show up in the "Advisor's notes" panel too.
#
# The result is saved as `<name>.narration.<version>.json`, which the dev sample
# endpoint serves at `?sample=<name>&version=<version>`.
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.narration import LLMNarrationLine, NarrationResponse, ToolCallTrace
from app.models.report import FinancialReport
from app.services import narration_validator, narration_visuals
from app.services.narration_tools import FigureIndex


def main() -> None:
    parser = argparse.ArgumentParser(description="Add hand-written charts to a saved narration.")
    parser.add_argument("report", type=Path, help="parsed report JSON")
    parser.add_argument("charts", type=Path, help="chart tool calls and line assignments")
    parser.add_argument("--narration", type=Path, help="default: <report name>.narration.json")
    parser.add_argument("--version", default="charts", help="suffix of the file to write")
    args = parser.parse_args()

    report = FinancialReport.model_validate(json.loads(args.report.read_text()))
    narration_path = args.narration or args.report.with_name(f"{args.report.stem}.narration.json")
    narration = NarrationResponse.model_validate(json.loads(narration_path.read_text()))
    spec = json.loads(args.charts.read_text())

    builder = narration_visuals.ChartBuilder(FigureIndex(report))
    calls: list[ToolCallTrace] = []
    for call in spec["charts"]:
        arguments, output = narration_visuals.execute_tool(builder, call["tool"], json.dumps(call["arguments"]))
        calls.append(ToolCallTrace(name=call["tool"], arguments=arguments, output=output))
        title = call["arguments"].get("title", "")
        if "error" in output:
            print(f"REJECTED {call['tool']} '{title}': {output['error']}")
        else:
            items = ", ".join(f"{item['key']}={item['label']} ({item['value']:g})" for item in output["items"])
            print(f"{output['chart_id']} {call['tool']} '{title}' [{output['unit']}]: {items}")

    assignments = spec.get("lines", {})
    requested = []
    for number, line in enumerate(narration.lines, start=1):
        assignment = assignments.get(str(number), {})
        requested.append(
            LLMNarrationLine(
                text=line.text,
                target_id=line.target_id,
                source_urls=line.sources,
                chart_id=assignment.get("chart_id"),
                chart_emphasis=assignment.get("emphasis"),
            )
        )
    lines, removed = narration_validator.attach_visuals(requested, builder.charts)

    trace = narration.trace
    if trace.turns:
        trace.turns[0].tool_calls.extend(calls)
    trace.removed_visuals = removed
    for entry in removed:
        print(f"removed ({entry.reason}), line {entry.line}: {entry.chart_id} - {entry.detail}")

    output_path = args.report.with_name(f"{args.report.stem}.narration.{args.version}.json")
    output_path.write_text(
        json.dumps(
            {"lines": [l.model_dump() for l in lines], "trace": trace.model_dump()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(
        f"\n{len(builder.charts)} charts on {sum(1 for l in lines if l.visual)} of {len(lines)} lines "
        f"-> saved to {output_path}"
    )


if __name__ == "__main__":
    main()
