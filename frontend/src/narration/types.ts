// The narration script contract the sync engine consumes. Produced either by the
// backend's narration agent (POST /api/reports/narration) or, as a fallback when that
// fails, by buildStubScript - same shape either way, so the sync engine doesn't care
// which. Mirrors backend/app/models/narration.py.
export interface VisualItem {
  key: string // unique within its chart; what a line's `emphasis` refers to
  label: string
  // In the chart's `unit`. A waterfall step's value is signed: what it adds to the
  // running total.
  value: number
  // 'item': a bar, a part of the whole, or a waterfall step. 'total': the whole a share
  // bar's parts belong to. 'start'/'end': a waterfall's opening and closing bars.
  role: 'item' | 'total' | 'start' | 'end'
  raw_text: string // the figure as printed in the report
  source_id: string // the cell or paragraph it was read from
}

export type VisualUnit = 'billions' | 'millions' | 'thousands' | 'percent' | null

// A small chart shown in a card while a line is spoken. The backend builds it from
// references into the report, so its values are the report's, not the model's.
export interface Visual {
  id: string
  type: 'bar' | 'share' | 'waterfall'
  title: string
  // The scale every item's value is in; null for figures shown as printed.
  unit: VisualUnit
  items: VisualItem[]
}

export interface LineVisual {
  chart: Visual
  // Key of the item this line is about - drawn in full while the rest is faded.
  emphasis: string | null
}

export interface NarrationLine {
  text: string
  target_id: string
  // Web pages the line draws on beyond the report. The backend only keeps URLs that
  // actually came back from its web searches. Absent on the locally-built stub script.
  sources?: string[]
  // Consecutive lines may carry the same chart with a different emphasis. Absent on the
  // stub script and on runs saved before charts existed.
  visual?: LineVisual | null
}

export type NarrationScript = NarrationLine[]

// A line's spoken audio. A script's audio is a list parallel to its lines, with null
// for any line that has no clip - the player times those lines itself.
export interface AudioClip {
  url: string
  duration_ms: number
}

export type NarrationAudio = (AudioClip | null)[]

// What the agent did to produce a script - one entry per model call, with the
// calculation tools it ran in that turn. Shown in the "Advisor's notes" panel.
export interface ToolCallTrace {
  name: string
  arguments: Record<string, unknown>
  output: Record<string, unknown>
}

export interface WebSearchTrace {
  action: 'search' | 'open_page' | 'find_in_page'
  query: string | null
  sources: string[]
}

export interface AgentTurn {
  turn: number
  tool_calls: ToolCallTrace[]
  web_searches: WebSearchTrace[]
  input_tokens: number
  output_tokens: number
  cost_usd: number
  duration_ms: number
}

// A URL the model cited that was removed before reaching the listener: 'unverified' if
// no web search in the run returned it, 'blocked' if it's on a forum/social/video site.
export interface RemovedSource {
  line: number // 1-based position in the script
  url: string
  reason: 'unverified' | 'blocked'
}

// A chart reference on a line that didn't hold up: 'unknown_chart' if no chart with
// that id was built (the line plays without one), 'unknown_emphasis' if the chart has
// no such item (it is shown with nothing emphasized), 'reappeared' if the chart came
// back after a line without it (it is only shown for its first run of lines).
export interface RemovedVisual {
  line: number // 1-based position in the script
  chart_id: string
  reason: 'unknown_chart' | 'unknown_emphasis' | 'reappeared'
  detail: string
}

export interface NarrationTrace {
  turns: AgentTurn[]
  total_input_tokens: number
  total_output_tokens: number
  // Tokens plus the per-call web search fee.
  total_cost_usd: number
  total_duration_ms: number
  total_web_searches: number
  repaired_target_ids: number
  dropped_source_urls: number
  blocked_source_urls: number
  // The URLs behind the two counts above. Absent on runs saved before it was recorded.
  removed_sources?: RemovedSource[]
  // Charts that failed their own checks are failed tool calls in `turns` instead.
  removed_visuals?: RemovedVisual[]
}

export interface NarrationResponse {
  lines: NarrationScript
  trace: NarrationTrace
}
