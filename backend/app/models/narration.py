# Narration script contract, mirrored by hand in frontend/src/narration/types.ts.
# `target_id` must be a block, row, or cell id that exists in the report the script was
# generated from (see docs/schema.md for the id rules) - the frontend sync engine
# scrolls to / highlights whatever it points at.
from typing import Any

from pydantic import BaseModel, Field

from app.models.report import FinancialReport


class NarrationLine(BaseModel):
    text: str
    target_id: str


class LLMNarrationScript(BaseModel):
    # What the model's final structured output is parsed into. Same shape as the
    # public script, but its target_ids are unchecked until narration_validator runs.
    lines: list[NarrationLine]


class ToolCallTrace(BaseModel):
    name: str
    arguments: dict[str, Any]
    output: dict[str, Any]


class AgentTurn(BaseModel):
    turn: int
    tool_calls: list[ToolCallTrace]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int


class NarrationTrace(BaseModel):
    turns: list[AgentTurn]
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    total_duration_ms: int
    # How many lines pointed at an id that doesn't exist and had to be re-targeted.
    repaired_target_ids: int


class NarrationRequest(BaseModel):
    report: FinancialReport


class NarrationResponse(BaseModel):
    lines: list[NarrationLine] = Field(default_factory=list)
    trace: NarrationTrace
