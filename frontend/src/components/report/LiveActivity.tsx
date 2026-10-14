import { useEffect, useRef } from 'react'
import type { NarrationEvent } from '../../narration/types'
import { CallView, ThoughtView, TurnView, WebSearchView } from './AdvisorNotes'
import './LiveActivity.css'

interface LiveActivityProps {
  // What the run has reported so far, in order.
  events: NarrationEvent[]
}

type TurnStarted = Extract<NarrationEvent, { type: 'turn_started' }>

// The turn whose model call is still out, and what it has reported from inside it.
// Once the turn finishes, its own record replaces these.
function turnInProgress(events: NarrationEvent[]): { started: TurnStarted; inside: NarrationEvent[] } | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i]
    if (event.type === 'turn_finished') return null
    if (event.type === 'turn_started') return { started: event, inside: events.slice(i + 1) }
  }
  return null
}

// What is going on right now, from the last thing reported.
function currentStep(events: NarrationEvent[]): string | null {
  const last = events[events.length - 1]
  if (!last) return null
  switch (last.type) {
    case 'turn_started':
      return last.purpose === 'correction' ? 'Fixing what the check found…' : 'Thinking…'
    case 'thinking':
      return 'Thinking…'
    case 'web_search':
      return 'Reading what the search found…'
    case 'tool_requested':
      return 'Asking for more…'
    case 'line_written':
      return 'Writing the script…'
    case 'review_started':
      return 'Checking every figure in the script against the report…'
    case 'turn_finished':
    case 'review_finished':
      return 'Finishing up…'
  }
}

// The advisor's work while the walkthrough is being prepared: each turn as it comes
// back, with the same detail the advisor's notes show afterwards, and at the bottom the
// turn in progress - its searches, the tools it has asked for and the lines it has
// written so far. Keeps itself scrolled to the newest entry.
export function LiveActivity({ events }: LiveActivityProps) {
  const listRef = useRef<HTMLOListElement>(null)

  useEffect(() => {
    const list = listRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [events.length])

  const step = currentStep(events)
  if (!step) return null
  const current = turnInProgress(events)
  const linesWritten = current ? current.inside.filter((event) => event.type === 'line_written') : []

  return (
    <section className="live-activity" aria-label="What the advisor is doing">
      <h2 className="live-activity__title">
        <span className="live-activity__dot" aria-hidden="true" />
        Live from the advisor
      </h2>
      <ol ref={listRef} className="advisor-notes__turns live-activity__turns">
        {events.map((event, i) => {
          if (event.type === 'turn_finished') {
            const { turn } = event
            // The loop ends its drafting on the first turn that asks for no tool.
            const wroteScript = turn.purpose !== 'correction' && turn.tool_calls.length === 0
            const written = events.filter((e) => e.type === 'line_written' && e.turn === turn.turn).length
            return (
              <TurnView key={i} turn={turn} wroteScript={wroteScript} lineCount={wroteScript && written > 0 ? written : null} />
            )
          }
          if (event.type === 'review_finished') {
            return (
              <li key={i} className="advisor-notes__turn">
                <span className="advisor-notes__turn-title">Script check {event.round}</span>
                <p className="advisor-notes__turn-summary">
                  {event.lines} lines read, {event.figures_confirmed} figures matched to the report,{' '}
                  {event.findings === 0
                    ? 'nothing to fix'
                    : `${event.findings} to look at again${event.must_fix > 0 ? ` (${event.must_fix} wrong)` : ''}`}
                </p>
              </li>
            )
          }
          return null
        })}
        <li className="advisor-notes__turn">
          {current && (
            <>
              <span className="advisor-notes__turn-title">
                Turn {current.started.turn}
                {current.started.purpose === 'correction' && ' · correction'}
              </span>
              <ul className="advisor-notes__calls">
                {current.inside.map((event, i) => {
                  if (event.type === 'thinking') return <ThoughtView key={i} text={event.text} />
                  if (event.type === 'web_search') return <WebSearchView key={i} search={event.search} />
                  if (event.type === 'tool_requested') {
                    return <CallView key={i} call={{ name: event.name, arguments: event.arguments, output: {} }} />
                  }
                  return null
                })}
              </ul>
              {linesWritten.length > 0 && (
                <ol className="live-activity__lines">
                  {linesWritten.map((event, i) => (
                    <li key={i}>{event.type === 'line_written' && event.text}</li>
                  ))}
                </ol>
              )}
            </>
          )}
          <p className="live-activity__current">
            <span className="spinner" aria-hidden="true" />
            {step}
          </p>
        </li>
      </ol>
    </section>
  )
}
