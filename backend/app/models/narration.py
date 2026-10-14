# Narration script contract, mirrored by hand in frontend/src/narration/types.ts.
# `target_id` must be a block, row, or cell id that exists in the report the script was
# generated from (see docs/schema.md for the id rules) - the frontend sync engine
# scrolls to / highlights whatever it points at.
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.report import FinancialReport


class VisualItem(BaseModel):
    key: str  # unique within its chart; what a line's `emphasis` refers to
    label: str
    # In the chart's `unit`. A waterfall step's value is signed: what it adds to the
    # running total.
    value: float
    # "item": a bar, a part of the whole, or a waterfall step. "total": the whole a
    # share bar's parts belong to. "start"/"end": a waterfall's opening and closing bars.
    role: Literal["item", "total", "start", "end"]
    raw_text: str  # the figure as printed in the report, or a calculated one written out
    source_id: str  # the cell or paragraph it was read from, or the calculation's id
    # Calculated from the report's figures rather than printed in it; the card says so.
    computed: bool = False


class Visual(BaseModel):
    # A small chart shown in a card while a line is spoken. Built by
    # narration_visuals.py from references into the report: the model picks the chart
    # type, the labels and which figures go in, but never writes a value.
    id: str
    # "bar": figures side by side. "share": parts of a whole. "waterfall": a starting
    # figure, the steps added to or taken from it, and the figure they arrive at.
    type: Literal["bar", "share", "waterfall"]
    title: str
    # The scale every item's value is in; None for figures shown as printed (e.g. per
    # share).
    unit: Literal["billions", "millions", "thousands", "percent"] | None
    items: list[VisualItem]


class LineVisual(BaseModel):
    chart: Visual
    # Key of the item this line is about - drawn in full while the rest is faded.
    emphasis: str | None = None


class FigureRef(BaseModel):
    # Where a figure a line states comes from - the same reference the calculation
    # tools take as an operand: a cell id, a paragraph id plus the figure as written
    # there, or the calc id of a result.
    id: str
    quote: str | None


class CalculationTerm(BaseModel):
    id: str
    quote: str | None
    # Only `combine` reads it; the other operations go by the order of their terms.
    sign: Literal["add", "subtract"]


class LineCalculation(BaseModel):
    # A calculation written next to the line that states its result, instead of a tool
    # call in an earlier turn: the model names the figures and the operation, and the
    # backend does the arithmetic (narration_tools.evaluate) and checks the number in
    # the text against it. For the figure that occurs to the model while it is writing
    # - "that is 3.6 points more" - where calling a tool would cost a whole turn.
    operation: Literal["difference", "combine", "percent_change", "ratio"]
    terms: list[CalculationTerm]


class NarrationLine(BaseModel):
    text: str
    target_id: str
    # Web pages the line draws on beyond the report itself. Only URLs that actually came
    # back from this run's web searches survive validation.
    sources: list[str] = Field(default_factory=list)
    # Consecutive lines may carry the same chart with a different emphasis.
    visual: LineVisual | None = None
    # What the line's figures were checked against (narration_figures.py). A calc id
    # only means something next to the trace of the run that made it.
    figures: list[FigureRef] = Field(default_factory=list)
    # Calculations the line carries itself; their results were checked like `figures`.
    calculations: list[LineCalculation] = Field(default_factory=list)


class LLMNarrationLine(BaseModel):
    # No defaults here: structured output requires every field, and the model must
    # explicitly give an empty list when a line uses no outside source.
    text: str
    target_id: str = Field(
        description=(
            "Id of the part of the report this line is about, copied exactly from the [brackets] "
            "in the report. Use the most specific one that fits: the cell id when one table "
            "value carries the line, the row id when the line compares a metric across "
            "columns, otherwise the block id."
        )
    )
    source_urls: list[str]
    figures: list[FigureRef] = Field(
        description=(
            "Where every figure this line states comes from - every amount and every "
            "percentage, each as one reference. A table figure: {id: <cell id>, quote: "
            "null}. A figure from paragraph text: {id: <paragraph id>, quote: <the figure "
            "exactly as written there>}. A figure you calculated: {id: <its calc_id>, "
            "quote: null}. Each stated figure is checked against these, so list the cell "
            "the sentence actually means - the right row and the right period. Empty for a "
            "line that states no figure, and nothing to list for a figure that came from "
            "a web page."
        )
    )
    calculations: list[LineCalculation] = Field(
        description=(
            "For a number this line states that is neither printed in the report nor the "
            "result of a tool call you already made: the calculation that gives it, which "
            "is then done for you and compared with what the line says. `terms` are "
            "references like those in `figures`, each with a `sign`. 'difference': [the "
            "figure to subtract from, the figure to subtract]. 'percent_change': [the "
            "earlier figure, the later one]. 'ratio': [numerator, denominator], giving a "
            "percentage. 'combine': 2 to 8 figures added or subtracted by their `sign`. "
            "`sign` only matters for 'combine'; give 'add' elsewhere. E.g. a line saying a "
            "margin widened by 2.4 points, where the two margins are calc_3 and calc_4: "
            "{operation: 'difference', terms: [{id: 'calc_3', quote: null, sign: 'add'}, "
            "{id: 'calc_4', quote: null, sign: 'add'}]}. Empty for most lines."
        )
    )
    chart_id: str | None = Field(
        description=(
            "Id of a chart to show while this line is spoken, exactly as returned by a "
            "chart tool. null for a line without a chart."
        )
    )
    chart_emphasis: str | None = Field(
        description=(
            "Key of the one item in that chart this line is about, exactly as returned by "
            "the chart tool. null when the line is about the chart as a whole."
        )
    )


class LLMLineEdit(BaseModel):
    line: int = Field(description="The number of the line to change, as numbered in the request.")
    action: Literal["replace", "remove"]
    replacement: LLMNarrationLine | None = Field(
        description="For 'replace': the whole line as it should now be, every field. null for 'remove'."
    )


class LLMScriptEdits(BaseModel):
    # What a correction turn returns: only the lines that change. Rewriting the whole
    # script to fix one line took as long as writing it, and gave every other line a
    # chance to come back different.
    edits: list[LLMLineEdit]


class LLMReviewIssue(BaseModel):
    line: int = Field(description="The number of the line, as given.")
    problem: str = Field(description="One sentence: what the line says, and what the figure it cites actually is.")


class LLMReview(BaseModel):
    # What the reviewer model returns. Empty when every line matches what it cites.
    issues: list[LLMReviewIssue]


class LLMNarrationScript(BaseModel):
    # What the model's final structured output is parsed into. Its target_ids,
    # source_urls and chart references are unchecked until narration_validator runs.
    lines: list[LLMNarrationLine]


class ToolCallTrace(BaseModel):
    name: str
    arguments: dict[str, Any]
    output: dict[str, Any]


class WebSearchTrace(BaseModel):
    action: str  # "search", "open_page", or "find_in_page"
    query: str | None
    sources: list[str]


class AgentTurn(BaseModel):
    turn: int
    # "draft": working towards the script. "correction": rewriting it after the review
    # (see NarrationReview) found something.
    purpose: Literal["draft", "correction"] = "draft"
    tool_calls: list[ToolCallTrace]
    web_searches: list[WebSearchTrace] = Field(default_factory=list)
    # The model's own summaries of its reasoning in this turn, in order. Only asked for
    # when a run is being followed live, so empty otherwise.
    thinking: list[str] = Field(default_factory=list)
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int


class RemovedSource(BaseModel):
    # A URL the model cited that didn't make it to the listener.
    line: int  # 1-based position of the line in the final script
    url: str
    # "unverified": not returned by any web search in this run.
    # "blocked": on a blocked site (narration_validator.BLOCKED_SOURCE_DOMAINS).
    reason: Literal["unverified", "blocked"]


class RemovedVisual(BaseModel):
    # A chart reference on a line that didn't hold up. The line itself stays.
    line: int  # 1-based position of the line in the final script
    chart_id: str
    # "unknown_chart": no chart tool call produced this id (a chart that failed its
    # checks never gets one), so the line is shown without a chart.
    # "unknown_emphasis": the chart exists but has no item with that key, so it is shown
    # with nothing emphasized.
    # "reappeared": the chart came back after a line without it; it is only shown for
    # its first run of lines.
    # "emphasis_moved": the line highlights the figure of a different item of the
    # chart than it emphasized, so the emphasis was moved to that item.
    # "emphasis_dropped": the emphasized item is not a figure the line highlights or
    # cites, so the chart is shown with nothing emphasized.
    reason: Literal["unknown_chart", "unknown_emphasis", "reappeared", "emphasis_moved", "emphasis_dropped"]
    detail: str


class ReviewFinding(BaseModel):
    line: int  # 1-based position in the script as it stood in that round
    text: str  # the line as it stood
    # "figure_mismatch": a figure the line states matches none of the figures it cites.
    # "unknown_reference": the line cites something that doesn't exist.
    # "isolated_cell": a cited cell shares neither a row nor a column with the others
    # cited from its table - the pattern of a figure taken from the wrong period.
    # "target_not_cited": the line highlights a cell that shares neither a row nor a
    # column with the cells it cites from that table.
    # "reviewer": the second model reading each line against the labels of what it cites.
    # "calculation_error": a calculation the line carries couldn't be done.
    check: Literal[
        "figure_mismatch", "unknown_reference", "calculation_error", "isolated_cell", "target_not_cited", "reviewer"
    ]
    detail: str
    # True for what can be checked exactly: the line is cut if it is still there after
    # the corrections. False for a judgement that can be wrong: the model is asked to
    # look again, and the line stays either way.
    must_fix: bool


class LineCalculationResult(BaseModel):
    line: int
    formula: str  # as the backend worked it out, e.g. "50.1 - 46.5 = 3.6"


class ReviewRound(BaseModel):
    lines: int
    # Figures stated in the script that matched something their line cites.
    figures_confirmed: int
    findings: list[ReviewFinding]
    # The calculations lines carried themselves, as worked out here. One that failed
    # is a "calculation_error" finding instead.
    calculations: list[LineCalculationResult] = Field(default_factory=list)


class RemovedLine(BaseModel):
    text: str
    detail: str


class NarrationReview(BaseModel):
    # What checking the script against the report found, round by round: the first is
    # the model's draft, each later one the script after a correction turn.
    rounds: list[ReviewRound]
    # Lines cut because a must-fix finding survived every correction.
    removed_lines: list[RemovedLine] = Field(default_factory=list)
    # The reviewer's own model call; None if it didn't run or failed.
    reviewer_input_tokens: int | None = None
    reviewer_output_tokens: int | None = None
    reviewer_cost_usd: float | None = None
    reviewer_duration_ms: int | None = None


class NarrationTrace(BaseModel):
    turns: list[AgentTurn]
    total_input_tokens: int
    total_output_tokens: int
    # Tokens plus the per-call web search fee (app/core/pricing.py).
    total_cost_usd: float
    total_duration_ms: int
    total_web_searches: int = 0
    # How many lines pointed at an id that doesn't exist and had to be re-targeted.
    repaired_target_ids: int
    # How many cited URLs were dropped for not coming from any web search in this run.
    dropped_source_urls: int = 0
    # How many cited URLs were dropped for being on a blocked site (forums, social media,
    # video - see narration_validator.BLOCKED_SOURCE_DOMAINS).
    blocked_source_urls: int = 0
    # The URLs behind the two counts above, so a line that names a publication but shows
    # no link can be traced back to what the model tried to cite.
    removed_sources: list[RemovedSource] = Field(default_factory=list)
    # Chart references that were dropped or stripped of their emphasis. Charts that
    # failed their own checks show up as failed tool calls in `turns` instead.
    removed_visuals: list[RemovedVisual] = Field(default_factory=list)
    # None on runs saved before scripts were reviewed. Its model call is included in
    # the totals above.
    review: NarrationReview | None = None


class NarrationRequest(BaseModel):
    report: FinancialReport


class NarrationResponse(BaseModel):
    lines: list[NarrationLine] = Field(default_factory=list)
    trace: NarrationTrace
