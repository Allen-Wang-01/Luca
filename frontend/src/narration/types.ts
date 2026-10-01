// The narration script contract the sync engine consumes. Produced either by the
// backend's narration agent (POST /api/reports/narration) or, as a fallback when that
// fails, by buildStubScript - same shape either way, so the sync engine doesn't care
// which. Mirrors backend/app/models/narration.py.
export interface NarrationLine {
  text: string
  target_id: string
}

export type NarrationScript = NarrationLine[]

// What the agent did to produce a script - one entry per model call, with the
// calculation tools it ran in that turn. Shown in the "Advisor's notes" panel.
export interface ToolCallTrace {
  name: string
  arguments: Record<string, unknown>
  output: Record<string, unknown>
}

export interface AgentTurn {
  turn: number
  tool_calls: ToolCallTrace[]
  input_tokens: number
  output_tokens: number
  cost_usd: number
  duration_ms: number
}

export interface NarrationTrace {
  turns: AgentTurn[]
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
  total_duration_ms: number
  repaired_target_ids: number
}

export interface NarrationResponse {
  lines: NarrationScript
  trace: NarrationTrace
}
