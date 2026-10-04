import { sourceLabel } from '../../narration/sourceLabel'
import type { AgentTurn, NarrationTrace, ToolCallTrace, WebSearchTrace } from '../../narration/types'
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
}

interface ToolInput {
  label: string
  raw_text: string
}

// Tool output is typed loosely on the wire (it's whatever the backend tool returned),
// so pull out the fields this panel knows how to show and ignore anything else.
function readInputs(output: Record<string, unknown>): ToolInput[] {
  if (!Array.isArray(output.inputs)) return []
  return output.inputs.filter(
    (input): input is ToolInput =>
      typeof input === 'object' && input !== null && typeof input.label === 'string' && typeof input.raw_text === 'string',
  )
}

// Shown when a call failed before resolving its inputs: each operand is
// {id, quote}, so show the id, plus the quoted figure for prose operands.
function describeArguments(args: Record<string, unknown>): string {
  return Object.values(args)
    .map((operand) => {
      if (typeof operand !== 'object' || operand === null) return String(operand)
      const { id, quote } = operand as { id?: unknown; quote?: unknown }
      return typeof quote === 'string' ? `${String(id)} ("${quote}")` : String(id)
    })
    .join(', ')
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

  return (
    <li className={`advisor-notes__call${error ? ' advisor-notes__call--error' : ''}`}>
      <span className="advisor-notes__tool">{TOOL_LABELS[call.name] ?? call.name}</span>
      <div className="advisor-notes__call-body">
        {inputs.length > 0 ? (
          <span className="advisor-notes__inputs">
            {inputs.map((input) => `${input.label} (${input.raw_text})`).join(' → ')}
          </span>
        ) : (
          <span className="advisor-notes__inputs">{describeArguments(call.arguments)}</span>
        )}
        {formula && <code className="advisor-notes__formula">{formula}</code>}
        {error && <span className="advisor-notes__error">{error}</span>}
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

function pluralize(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

function TurnView({ turn, isFinal, lineCount }: { turn: AgentTurn; isFinal: boolean; lineCount: number }) {
  const searches = turn.web_searches ?? []
  const didWork = turn.tool_calls.length > 0 || searches.length > 0
  const summary = [
    searches.length > 0 && `searched the web ${searches.length === 1 ? 'once' : `${searches.length} times`}`,
    turn.tool_calls.length > 0 && `ran ${pluralize(turn.tool_calls.length, 'calculation')}`,
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
  const calculationCount = trace.turns.reduce((sum, turn) => sum + turn.tool_calls.length, 0)

  return (
    <aside className="advisor-notes" aria-label="Advisor's notes">
      <div className="advisor-notes__header">
        <div>
          <h3 className="advisor-notes__title">Advisor's notes</h3>
          <p className="advisor-notes__summary">
            {pluralize(trace.turns.length, 'turn')} · {pluralize(calculationCount, 'calculation')} ·{' '}
            {pluralize(trace.total_web_searches ?? 0, 'web search')} ·{' '}
            {formatTokens(trace.total_input_tokens + trace.total_output_tokens)} tokens · $
            {trace.total_cost_usd.toFixed(4)} · {formatSeconds(trace.total_duration_ms)}
            {trace.repaired_target_ids > 0 && ` · ${trace.repaired_target_ids} highlight targets repaired`}
            {trace.dropped_source_urls > 0 && ` · ${trace.dropped_source_urls} unverified sources removed`}
            {trace.blocked_source_urls > 0 && ` · ${trace.blocked_source_urls} forum/social sources removed`}
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
      </ol>
    </aside>
  )
}
