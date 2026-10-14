# Manual end-to-end narration run against the real API. Costs real money per run (one
# model call per agent turn), so this is not part of the automated test suite - run it
# by hand to judge narration quality and targeting on a real parsed report.
#
# Usage: python scripts/narrate_sample.py path/to/parsed_report.json
# (the JSON is what scripts/parse_sample.py prints)
#
# The result is saved next to the input as `<name>.narration.json` - every run costs
# money and the output differs run to run, so it's kept for later inspection rather
# than only printed. The per-turn agent log, with the model's reasoning summaries, still
# goes to stderr.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging
from app.models.report import FinancialReport
from app.services import narration_agent, report_validator


def _show_thinking(event: dict) -> None:
    # Following the run is what streams its model calls and asks for the model's
    # reasoning summaries, so a saved script has them in its advisor's notes the way a
    # live run on the page does. They go to stderr with the rest of the log.
    if event["type"] == "thinking":
        print(f"[turn {event['turn']}] thinking: {event['text']}", file=sys.stderr)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/narrate_sample.py path/to/parsed_report.json", file=sys.stderr)
        sys.exit(1)

    configure_logging()
    report_path = Path(sys.argv[1])
    report = FinancialReport.model_validate(json.loads(report_path.read_text()))
    # Saved flags may be from an older validator - don't narrate a since-fixed false positive.
    report_validator.revalidate(report)

    lines, trace = narration_agent.generate_narration(report, on_event=_show_thinking)

    output_path = report_path.with_name(f"{report_path.stem}.narration.json")
    output_path.write_text(
        json.dumps(
            {"lines": [l.model_dump() for l in lines], "trace": trace.model_dump()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    for index, line in enumerate(lines, start=1):
        print(f"{index:>2}. [{line.target_id}] {line.text}")
        for url in line.sources:
            print(f"      source: {url}")
    for removed in trace.removed_sources:
        print(f"removed source ({removed.reason}), line {removed.line}: {removed.url}")
    for number, review_round in enumerate(trace.review.rounds, start=1):
        print(
            f"figure check, round {number}: {review_round.figures_confirmed} figures confirmed "
            f"in {review_round.lines} lines, {len(review_round.findings)} findings"
        )
        for calculation in review_round.calculations:
            print(f"      line {calculation.line} carries: {calculation.formula}")
        for finding in review_round.findings:
            kind = "must fix" if finding.must_fix else "advice"
            print(f"      line {finding.line} ({finding.check}, {kind}): {finding.detail}")
    for removed in trace.review.removed_lines:
        print(f"cut line: {removed.text}\n      {removed.detail}")
    print(
        f"\n{len(lines)} lines, {len(trace.turns)} turns, "
        f"{sum(len(t.tool_calls) for t in trace.turns)} calculations, "
        f"{trace.total_web_searches} web searches "
        f"({trace.dropped_source_urls} unverified and {trace.blocked_source_urls} blocked-site "
        f"source URLs dropped), "
        f"${trace.total_cost_usd:.4f}, {trace.total_duration_ms / 1000:.1f}s "
        f"-> saved to {output_path}"
    )


if __name__ == "__main__":
    main()
