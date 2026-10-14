import type { NarrationEvent } from '../../narration/types'
import type { NarrationStatus } from '../../narration/useGeneratedNarration'
import type { FinancialReport } from '../../types/report'
import { LiveActivity } from './LiveActivity'
import { PreparationSteps } from './PreparationSteps'
import './CoverScreen.css'

interface CoverScreenProps {
  report: FinancialReport
  status: NarrationStatus
  error: string | null
  // What the advisor has reported doing so far, shown while the walkthrough is prepared.
  progress: NarrationEvent[]
  lineCount: number
  // Running time of the whole script, from its clips where it has them.
  durationMs: number
  // True when coming back to a walkthrough that was left part-way.
  canResume: boolean
  onStart: () => void
  onRead: () => void
  onRetry: () => void
}

interface ReportStat {
  value: number
  label: string
}

// What is in this report, counted from the parse itself.
function reportStats(report: FinancialReport): ReportStat[] {
  const tables = report.blocks.filter((block) => block.type === 'table')
  const rows = tables.flatMap((table) => table.rows)
  const figures = rows.reduce((count, row) => count + row.cells.filter((cell) => cell.value !== null).length, 0)
  const totals = rows.filter((row) => (row.sum_of ?? []).length > 0).length
  const flagged = rows.filter((row) => row.flags.length > 0).length + tables.filter((table) => table.flags.length > 0).length

  const stats: ReportStat[] = [
    { value: tables.length, label: tables.length === 1 ? 'table' : 'tables' },
    { value: figures, label: 'figures read' },
  ]
  // Only a report whose totals name their parts has any to count.
  if (totals > 0) stats.push({ value: totals, label: 'totals checked' })
  if (totals > 0 || flagged > 0) stats.push({ value: flagged, label: flagged === 1 ? 'figure to double-check' : 'figures to double-check' })
  return stats
}

function formatMinutes(durationMs: number): string {
  const minutes = Math.max(1, Math.round(durationMs / 60_000))
  return `about ${minutes} min`
}

// The first thing shown for a report: whose it is and what's in it, and the button that
// starts the walkthrough once it has been prepared.
export function CoverScreen({
  report,
  status,
  error,
  progress,
  lineCount,
  durationMs,
  canResume,
  onStart,
  onRead,
  onRetry,
}: CoverScreenProps) {
  const { meta } = report

  return (
    <div className="cover-screen">
      <div className="cover-screen__panel">
        <p className="cover-screen__eyebrow">{meta.report_type}</p>
        <h1 className="cover-screen__company">
          {meta.company_name}
          {meta.ticker && <span className="cover-screen__ticker">{meta.ticker}</span>}
        </h1>
        <p className="cover-screen__period">{meta.fiscal_period}</p>

        <dl className="cover-screen__stats">
          {reportStats(report).map((stat) => (
            <div key={stat.label} className="cover-screen__stat">
              <dd>{stat.value.toLocaleString('en-US')}</dd>
              <dt>{stat.label}</dt>
            </div>
          ))}
        </dl>

        {status === 'loading' ? (
          <div className="cover-screen__preparing">
            <PreparationSteps stage="narrating" />
            <LiveActivity events={progress} />
            <p className="cover-screen__hint">This can take a couple of minutes. You can read the report while you wait.</p>
          </div>
        ) : (
          <>
            {status === 'failed' && (
              <p className="cover-screen__notice" title={error ?? undefined}>
                Couldn't prepare the advisor's walkthrough. You can try again, or play a basic one that simply reads
                through the report.
              </p>
            )}
            <div className="cover-screen__actions">
              <button type="button" className="cover-screen__start" onClick={onStart}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M7 5l13 7-13 7z" />
                </svg>
                {status === 'failed' ? 'Play basic walkthrough' : canResume ? 'Resume walkthrough' : 'Start walkthrough'}
              </button>
              {status === 'failed' && (
                <button type="button" className="cover-screen__secondary" onClick={onRetry}>
                  Try again
                </button>
              )}
            </div>
            <p className="cover-screen__hint">
              {lineCount} lines · {formatMinutes(durationMs)}
            </p>
          </>
        )}

        <button type="button" className="cover-screen__link" onClick={onRead}>
          Read the report yourself
        </button>
      </div>
    </div>
  )
}
