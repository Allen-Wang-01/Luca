import { sourceLabel } from '../../narration/sourceLabel'
import type {
  AgentTurn,
  NarrationTrace,
  RemovedSource,
  RemovedVisual,
  ToolCallTrace,
  WebSearchTrace,
} from '../../narration/types'
import './AdvisorNotes.css'

interface AdvisorNotesProps {
  trace: NarrationTrace
  lineCount: number
  onClose: () => void
}

const TOOL_LABELS: Record<string, string> = {
  percent_change: '% change',
  ratio: 'Ratio',
  difference: 'Difference',
  bar_chart: 'Bar chart',
  share_bar: 'Share bar',
  waterfall: 'Waterfall',
}

const CHART_TOOLS = new Set(['bar_chart', 'share_bar', 'waterfall'])

function isChartCall(call: ToolCallTrace): boolean {
  return CHART_TOOLS.has(call.name)
}

interface ToolInput {
  label: string
  raw_text: string
}

// Tool output is typed loosely on the wire (it's whatever the backend tool returned),
// so pull out the fields this panel knows how to show and ignore anything else.
// A calculation lists the figures it used as `inputs`; a chart lists them as `items`.
function readInputs(output: Record<string, unknown>): ToolInput[] {
  const inputs = Array.isArray(output.inputs) ? output.inputs : Array.isArray(output.items) ? output.items : []
  return inputs.filter(
    (input): input is ToolInput =>
      typeof input === 'object' && input !== null && typeof input.label === 'string' && typeof input.raw_text === 'string',
  )
}

// Every {id, quote} reference in a call's arguments, however deeply nested - a
// calculation passes them directly, a chart passes them inside its items.
function collectOperands(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(collectOperands)
  if (typeof value !== 'object' || value === null) return []
  const { id, quote } = value as { id?: unknown; quote?: unknown }
  if (typeof id === 'string') return [typeof quote === 'string' ? `${id} ("${quote}")` : id]
  return Object.values(value).flatMap(collectOperands)
}

// Shown when a call failed before resolving its inputs: the id of each figure it
// asked for, plus the quoted text for figures from prose.
function describeArguments(args: Record<string, unknown>): string {
  return collectOperands(args).join(', ')
}

function readString(output: Record<string, unknown>, key: string): string | null {
  const value = output[key]
  return typeof value === 'string' ? value : null
}

function formatTokens(count: number): string {
  return count >= 1000 ? `${(count / 1000).toFixed(1)}k` : String(count)
}

function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`
}

function ToolCallView({ call }: { call: ToolCallTrace }) {
  const error = readString(call.output, 'error')
  const formula = readString(call.output, 'formula')
  const inputs = readInputs(call.output)
  const isChart = isChartCall(call)
  const title = isChart && typeof call.arguments.title === 'string' ? call.arguments.title : null

  return (
    <li className={`advisor-notes__call${error ? ' advisor-notes__call--error' : ''}`}>
      <span className="advisor-notes__tool">{TOOL_LABELS[call.name] ?? call.name}</span>
      <div className="advisor-notes__call-body">
        {title && <span className="advisor-notes__chart-title">{title}</span>}
        {inputs.length > 0 ? (
          <span className="advisor-notes__inputs">
            {inputs.map((input) => `${input.label} (${input.raw_text})`).join(isChart ? ' · ' : ' → ')}
          </span>
        ) : (
          <span className="advisor-notes__inputs">{describeArguments(call.arguments)}</span>
        )}
        {formula && <code className="advisor-notes__formula">{formula}</code>}
        {error && (
          <span className="advisor-notes__error">
            {isChart && 'Rejected, not shown: '}
            {error}
          </span>
        )}
      </div>
    </li>
  )
}

const SEARCH_ACTION_LABELS: Record<WebSearchTrace['action'], string> = {
  search: 'Searched',
  open_page: 'Opened',
  find_in_page: 'Looked in',
}

function WebSearchView({ search }: { search: WebSearchTrace }) {
  return (
    <li className="advisor-notes__call">
      <span className="advisor-notes__tool advisor-notes__tool--search">Web</span>
      <div className="advisor-notes__call-body">
        <span className="advisor-notes__inputs">
          {SEARCH_ACTION_LABELS[search.action]}
          {search.query && <> “{search.query}”</>}
        </span>
        {search.sources.length > 0 && (
          <span className="advisor-notes__search-sources">
            {search.sources.map((url, i) => (
              <span key={url}>
                {i > 0 && ' · '}
                <a href={url} target="_blank" rel="noopener noreferrer" title={url}>
                  {sourceLabel(url)}
                </a>
              </span>
            ))}
          </span>
        )}
      </div>
    </li>
  )
}

// Removed URLs are shown as plain text, not links: an unverified one may not exist.
const REMOVED_REASON_LABELS: Record<RemovedSource['reason'], string> = {
  unverified: 'Not among the pages its searches returned - may be invented',
  blocked: 'Forum, social or video site - not shown as a source',
}

const REMOVED_VISUAL_LABELS: Record<RemovedVisual['reason'], string> = {
  unknown_chart: 'No such chart was built (a rejected chart has no id) - line plays without a chart',
  unknown_emphasis: 'Chart has no such item - shown with nothing emphasized',
}

function pluralize(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

function TurnView({ turn, isFinal, lineCount }: { turn: AgentTurn; isFinal: boolean; lineCount: number }) {
  const searches = turn.web_searches ?? []
  const didWork = turn.tool_calls.length > 0 || searches.length > 0
  const chartCount = turn.tool_calls.filter(isChartCall).length
  const calculationCount = turn.tool_calls.length - chartCount
  const summary = [
    searches.length > 0 && `searched the web ${searches.length === 1 ? 'once' : `${searches.length} times`}`,
    calculationCount > 0 && `ran ${pluralize(calculationCount, 'calculation')}`,
    chartCount > 0 && `drew ${pluralize(chartCount, 'chart')}`,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <li className="advisor-notes__turn">
      <div className="advisor-notes__turn-header">
        <span className="advisor-notes__turn-title">Turn {turn.turn}</span>
        <span className="advisor-notes__turn-stats">
          {formatTokens(turn.input_tokens)} in · {formatTokens(turn.output_tokens)} out · {formatSeconds(turn.duration_ms)}
        </span>
      </div>
      {didWork && (
        <>
          <p className="advisor-notes__turn-summary">{summary.charAt(0).toUpperCase() + summary.slice(1)}</p>
          <ul className="advisor-notes__calls">
            {searches.map((search, i) => (
              <WebSearchView key={`search-${i}`} search={search} />
            ))}
            {turn.tool_calls.map((call, i) => (
              <ToolCallView key={`call-${i}`} call={call} />
            ))}
          </ul>
        </>
      )}
      {isFinal && <p className="advisor-notes__turn-summary">Wrote the narration script ({lineCount} lines)</p>}
    </li>
  )
}

// Shows how the narration agent got to its script: every model call, the calculation
// tools it ran and their results, and what each call cost. Mirrors the backend trace.
export function AdvisorNotes({ trace, lineCount, onClose }: AdvisorNotesProps) {
  const toolCalls = trace.turns.flatMap((turn) => turn.tool_calls)
  const chartCalls = toolCalls.filter(isChartCall)
  const calculationCount = toolCalls.length - chartCalls.length
  const rejectedCharts = chartCalls.filter((call) => readString(call.output, 'error') !== null).length
  const removedSources = trace.removed_sources ?? []
  const removedVisuals = trace.removed_visuals ?? []

  return (
    <aside className="advisor-notes" aria-label="Advisor's notes">
      <div className="advisor-notes__header">
        <div>
          <h3 className="advisor-notes__title">Advisor's notes</h3>
          <p className="advisor-notes__summary">
            {pluralize(trace.turns.length, 'turn')} · {pluralize(calculationCount, 'calculation')} ·{' '}
            {chartCalls.length > 0 && `${pluralize(chartCalls.length - rejectedCharts, 'chart')} · `}
            {pluralize(trace.total_web_searches ?? 0, 'web search')} ·{' '}
            {formatTokens(trace.total_input_tokens + trace.total_output_tokens)} tokens · $
            {trace.total_cost_usd.toFixed(4)} · {formatSeconds(trace.total_duration_ms)}
            {trace.repaired_target_ids > 0 && ` · ${trace.repaired_target_ids} highlight targets repaired`}
            {trace.dropped_source_urls > 0 && ` · ${trace.dropped_source_urls} unverified citations rejected`}
            {trace.blocked_source_urls > 0 && ` · ${trace.blocked_source_urls} forum/social citations rejected`}
            {rejectedCharts > 0 && ` · ${pluralize(rejectedCharts, 'chart')} rejected`}
          </p>
        </div>
        <button type="button" className="advisor-notes__close" onClick={onClose} aria-label="Close advisor's notes">
          ×
        </button>
      </div>
      <ol className="advisor-notes__turns">
        {trace.turns.map((turn, i) => (
          <TurnView key={turn.turn} turn={turn} isFinal={i === trace.turns.length - 1} lineCount={lineCount} />
        ))}
        {removedSources.length > 0 && (
          <li className="advisor-notes__turn">
            <div className="advisor-notes__turn-header">
              <span className="advisor-notes__turn-title">Citations rejected by the validator</span>
            </div>
            <p className="advisor-notes__turn-summary">
              The advisor cited these links, but they failed our checks and were not shown. The lines themselves
              are still in the script.
            </p>
            <ul className="advisor-notes__calls">
              {removedSources.map((source, i) => (
                <li key={i} className="advisor-notes__call">
                  <span className="advisor-notes__tool advisor-notes__tool--removed">Line {source.line}</span>
                  <div className="advisor-notes__call-body">
                    <span className="advisor-notes__inputs">{REMOVED_REASON_LABELS[source.reason]}</span>
                    <span className="advisor-notes__search-sources">{source.url}</span>
                  </div>
                </li>
              ))}
            </ul>
          </li>
        )}
        {removedVisuals.length > 0 && (
          <li className="advisor-notes__turn">
            <div className="advisor-notes__turn-header">
              <span className="advisor-notes__turn-title">Charts removed by the validator</span>
            </div>
            <p className="advisor-notes__turn-summary">
              The advisor attached a chart to these lines that failed our checks. The lines themselves are still
              in the script.
            </p>
            <ul className="advisor-notes__calls">
              {removedVisuals.map((visual, i) => (
                <li key={i} className="advisor-notes__call">
                  <span className="advisor-notes__tool advisor-notes__tool--removed">Line {visual.line}</span>
                  <div className="advisor-notes__call-body">
                    <span className="advisor-notes__inputs">{REMOVED_VISUAL_LABELS[visual.reason]}</span>
                    <span className="advisor-notes__search-sources">
                      {visual.chart_id} · {visual.detail}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </li>
        )}
      </ol>
    </aside>
  )
}
