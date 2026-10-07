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
    raw_text: str  # the figure as printed in the report
    source_id: str  # the cell or paragraph it was read from


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


class NarrationLine(BaseModel):
    text: str
    target_id: str
    # Web pages the line draws on beyond the report itself. Only URLs that actually came
    # back from this run's web searches survive validation.
    sources: list[str] = Field(default_factory=list)
    # Consecutive lines may carry the same chart with a different emphasis.
    visual: LineVisual | None = None


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
    tool_calls: list[ToolCallTrace]
    web_searches: list[WebSearchTrace] = Field(default_factory=list)
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
    reason: Literal["unknown_chart", "unknown_emphasis"]
    detail: str


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


class NarrationRequest(BaseModel):
    report: FinancialReport


class NarrationResponse(BaseModel):
    lines: list[NarrationLine] = Field(default_factory=list)
    trace: NarrationTrace
