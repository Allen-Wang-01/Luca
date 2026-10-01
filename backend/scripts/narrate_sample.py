# Manual end-to-end narration run against the real API. Costs real money per run (one
# model call per agent turn), so this is not part of the automated test suite - run it
# by hand to judge narration quality and targeting on a real parsed report.
#
# Usage: python scripts/narrate_sample.py path/to/parsed_report.json
# (the JSON is what scripts/parse_sample.py prints)
#
# The result is saved next to the input as `<name>.narration.json` - every run costs
# money and the output differs run to run, so it's kept for later inspection rather
# than only printed. The per-turn agent log still goes to stderr.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging
from app.models.report import FinancialReport, TableBlock
from app.services import narration_agent, report_validator


def _revalidate(report: FinancialReport) -> None:
    # The saved JSON carries flags from whatever validator version parsed it. Validation
    # is local and free, so re-run the current rules rather than trusting stale flags -
    # otherwise a since-fixed false positive would still be narrated to the listener.
    for block in report.blocks:
        if isinstance(block, TableBlock):
            block.flags = []
            for row in block.rows:
                row.flags = []
    report_validator.validate(report)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/narrate_sample.py path/to/parsed_report.json", file=sys.stderr)
        sys.exit(1)

    configure_logging()
    report_path = Path(sys.argv[1])
    report = FinancialReport.model_validate(json.loads(report_path.read_text()))
    _revalidate(report)

    lines, trace = narration_agent.generate_narration(report)

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
    print(
        f"\n{len(lines)} lines, {len(trace.turns)} turns, "
        f"{sum(len(t.tool_calls) for t in trace.turns)} calculations, "
        f"${trace.total_cost_usd:.4f}, {trace.total_duration_ms / 1000:.1f}s "
        f"-> saved to {output_path}"
    )


if __name__ == "__main__":
    main()
