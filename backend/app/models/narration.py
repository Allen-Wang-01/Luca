# Narration script contract, mirrored by hand in frontend/src/narration/types.ts.
# `target_id` must be a block, row, or cell id that exists in the report the script was
# generated from (see docs/schema.md for the id rules) - the frontend sync engine
# scrolls to / highlights whatever it points at.
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.report import FinancialReport


class NarrationLine(BaseModel):
    text: str
    target_id: str
    # Web pages the line draws on beyond the report itself. Only URLs that actually came
    # back from this run's web searches survive validation.
    sources: list[str] = Field(default_factory=list)


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


class LLMNarrationScript(BaseModel):
    # What the model's final structured output is parsed into. Its target_ids and
    # source_urls are unchecked until narration_validator runs.
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


class NarrationRequest(BaseModel):
    report: FinancialReport


class NarrationResponse(BaseModel):
    lines: list[NarrationLine] = Field(default_factory=list)
    trace: NarrationTrace
