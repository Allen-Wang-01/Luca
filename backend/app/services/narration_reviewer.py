# A second reading of the narration script, by a model call of its own. The checks in
# narration_figures.py can tell that "$84.5 billion" is a figure the line cites; they
# can't tell that the sentence calls it this year's profit when the cited cell is last
# year's. That takes reading the sentence, so each line is laid out next to the full
# label of every figure it cites - row, sub-heading, column group, column - and a model
# that has seen nothing else is asked one question: does the sentence describe each
# figure as what its label says it is?
#
# It runs outside the agent's own conversation on purpose: the model that wrote a line
# tends to read it the way it meant it. And the input is only the script and the
# labels, not the report, so the call is small. Its findings are advice - they are sent
# back to the agent to look at again, and never remove a line by themselves.
import time
from typing import Any

from app.core.logging import get_logger
from app.core.pricing import calculate_cost
from app.models.narration import LLMNarrationLine, LLMReview, ReviewFinding
from app.services import llm_client, narration_figures
from app.services.narration_tools import FigureIndex, _Operand

logger = get_logger(__name__)

INSTRUCTIONS = """You are checking a spoken walkthrough of a company's financial \
report before it goes out. Each line below is followed by the figures it cites, each \
with its full label from the report: what the figure measures and the period or date \
it belongs to.

For each line, check one thing: does the sentence describe every cited figure as what \
its label says it is?
- The period: a figure labelled as last year's must not be presented as this year's, a \
year-to-date figure must not be presented as the quarter's, a prior balance-sheet date \
must not be presented as the latest one.
- The item: a figure labelled as one thing must not be presented as another - a cost \
as a sale, an operating profit as a net profit, one division's figure as another's.
- A comparison must compare like with like unless the sentence says otherwise: "sales \
were 500, against a profit of 80" should take both from the same period.

Report a line only when the sentence and a label clearly disagree. Do not report \
rounding ("about 12.4 billion" for 12,387 in millions is fine), wording, style, \
opinions, missing context, or anything you would need the report itself to judge. A \
calculated figure is shown with its formula; assume the arithmetic is right. Most \
lines are fine, and an empty list is the expected answer for a good script.
"""


def _describe(operand: _Operand) -> str:
    if operand.computed:
        return f"calculated: {operand.label}"
    if operand.from_text:
        return f"quoted from the report's text: {operand.raw_text}"
    return f"{operand.label} = {operand.raw_text}"


def render_for_review(lines: list[LLMNarrationLine], index: FigureIndex, unit_note: str) -> str | None:
    """The script as the reviewer reads it, or None if no line cites a figure."""
    parts: list[str] = []
    for number, line in enumerate(lines, start=1):
        operands, _ = narration_figures.resolve_figures(line, index)
        if not operands:
            continue
        cited = "\n".join(f"  - {_describe(operand)}" for operand in operands)
        parts.append(f'Line {number}: "{line.text}"\n  cites:\n{cited}')
    if not parts:
        return None
    return f"{unit_note}\n\n" + "\n\n".join(parts)


def review(
    lines: list[LLMNarrationLine], index: FigureIndex, unit_note: str, client: Any = None
) -> tuple[list[ReviewFinding], dict[str, Any] | None]:
    """Returns (findings, the call's usage) - usage is None when there was nothing to
    review or the call failed. A failed review costs the script a second opinion, not
    the script: the deterministic checks have already run."""
    prompt = render_for_review(lines, index, unit_note)
    if prompt is None:
        return [], None

    client = client or llm_client.client
    start = time.monotonic()
    try:
        response = client.responses.parse(
            model=llm_client.MODEL,
            instructions=INSTRUCTIONS,
            input=[{"role": "user", "content": prompt}],
            text_format=LLMReview,
        )
    except Exception:
        logger.exception("narration_review_failed")
        return [], None
    duration_ms = int((time.monotonic() - start) * 1000)

    parsed: LLMReview | None = response.output_parsed
    findings = [
        ReviewFinding(
            line=issue.line, text=lines[issue.line - 1].text, check="reviewer", detail=issue.problem, must_fix=False
        )
        for issue in (parsed.issues if parsed else [])
        if 1 <= issue.line <= len(lines)
    ]
    usage = response.usage
    cost = calculate_cost(llm_client.MODEL, usage.input_tokens, usage.output_tokens)
    logger.info(
        "narration_review lines=%d findings=%d input_tokens=%d output_tokens=%d cost_usd=%.6f duration_ms=%d",
        len(lines),
        len(findings),
        usage.input_tokens,
        usage.output_tokens,
        cost,
        duration_ms,
    )
    return findings, {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": cost,
        "duration_ms": duration_ms,
    }
