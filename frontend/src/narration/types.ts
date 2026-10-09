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
  raw_text: string // the figure as printed in the report, or a calculated one written out
  source_id: string // the cell or paragraph it was read from, or the calculation's id
  // Calculated from the report's figures rather than printed in it. Missing on scripts
  // saved before charts could show calculated figures.
  computed?: boolean
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
  // Where the figures the line states come from; the backend checked the text against
  // them. Absent on the stub script and on runs saved before lines listed them.
  figures?: FigureRef[]
}

// A cell id, a paragraph id plus the figure as written there, or the id of a
// calculation from the same run's trace.
export interface FigureRef {
  id: string
  quote: string | null
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
  // 'correction': rewriting the script after its review found something. Absent on
  // runs saved before scripts were reviewed, where every turn is a draft turn.
  purpose?: 'draft' | 'correction'
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

// Something the review of the script found on one line.
// 'figure_mismatch': a figure the line states matches none of the figures it cites.
// 'unknown_reference': the line cites something that doesn't exist.
// 'isolated_cell': a cited cell shares neither a row nor a column with the others cited
// from its table - the pattern of a figure taken from the wrong period.
// 'target_not_cited': the line highlights one cell but cites others from that table.
// 'reviewer': a second model reading each line against the labels of what it cites.
export interface ReviewFinding {
  line: number // 1-based position in the script as it stood in that round
  text: string
  check: 'figure_mismatch' | 'unknown_reference' | 'isolated_cell' | 'target_not_cited' | 'reviewer'
  detail: string
  // true: checked exactly, and the line is cut if it is still there after the
  // corrections. false: a judgement - the model looks again, the line stays either way.
  must_fix: boolean
}

export interface ReviewRound {
  lines: number
  figures_confirmed: number
  findings: ReviewFinding[]
}

export interface RemovedLine {
  text: string
  detail: string
}

// What checking the script against the report found. The first round is the model's
// draft, each later one the script after a correction turn.
export interface NarrationReview {
  rounds: ReviewRound[]
  removed_lines: RemovedLine[]
  // The reviewer's own model call; null if it didn't run or failed.
  reviewer_input_tokens: number | null
  reviewer_output_tokens: number | null
  reviewer_cost_usd: number | null
  reviewer_duration_ms: number | null
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
  // Absent or null on runs saved before scripts were reviewed.
  review?: NarrationReview | null
}

export interface NarrationResponse {
  lines: NarrationScript
  trace: NarrationTrace
}
