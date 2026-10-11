import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { FinancialReport } from '../../types/report'
import { resolveLineFocus } from '../../narration/lineFocus'
import { buildMentions, type Mention } from '../../narration/mentions'
import { buildSegments, type Segment } from '../../narration/segments'
import { buildTargetIndex } from '../../narration/targetIndex'
import { useGeneratedNarration, type GeneratedNarration } from '../../narration/useGeneratedNarration'
import {
  lineDurationMs,
  useNarrationPlayer,
  type NarrationPlayer as NarrationPlayerState,
} from '../../narration/useNarrationPlayer'
import { NarrationSyncProvider, useNarrationSync } from './NarrationSyncContext'
import { NarrationPlayer } from './NarrationPlayer'
import { AdvisorNotes } from './AdvisorNotes'
import { DOCKED_BELOW_PX } from './AnchoredCard'
import { BlockList } from './BlockList'
import { ClosingScreen } from './ClosingScreen'
import { CoverScreen } from './CoverScreen'
import { FigureRail } from './FigureRail'
import { FocusCard } from './FocusCard'
import { SpotlightLine } from './SpotlightLine'
import { VisualCard } from './VisualCard'
import './sync.css'
import './ReportView.css'

interface ReportViewProps {
  report: FinancialReport
  // Set for a saved walkthrough rather than a fresh upload; shown as a badge.
  sampleLabel?: string | null
  // Leaves the report for the start page.
  onExit: () => void
}

// 'cover': the report's title page, where the walkthrough is started.
// 'presenting': the walkthrough - the report with highlight, cards and the narration
// bar. When its last line has played it shows the closing screen instead.
// 'reading': the plain report, with nothing lit or dimmed.
type Mode = 'cover' | 'presenting' | 'reading'

const NO_IDS: string[] = []

export function ReportView({ report, sampleLabel = null, onExit }: ReportViewProps) {
  const narration = useGeneratedNarration(report)
  const player = useNarrationPlayer(narration.script, narration.audio)
  const [mode, setMode] = useState<Mode>('cover')

  // A new script arriving mid-walkthrough (the generated one after a retry, say) goes
  // back to the cover rather than carrying on from the same line number in other words.
  const [prevScript, setPrevScript] = useState(narration.script)
  if (narration.script !== prevScript) {
    setPrevScript(narration.script)
    if (mode === 'presenting') setMode('cover')
  }

  const screen = mode === 'presenting' && player.hasEnded ? 'closing' : mode
  const presenting = screen === 'presenting'

  const targets = useMemo(() => buildTargetIndex(report), [report])
  const segments = useMemo(() => buildSegments(narration.script, report, targets), [narration.script, report, targets])
  const mentions = useMemo(() => buildMentions(narration.script, targets), [narration.script, targets])
  const focus = useMemo(() => resolveLineFocus(player.currentLine, targets), [player.currentLine, targets])
  const totalDurationMs = useMemo(
    () =>
      narration.script.reduce(
        (sum, line, index) => sum + (narration.audio?.[index]?.duration_ms ?? lineDurationMs(line.text)),
        0,
      ),
    [narration.script, narration.audio],
  )

  const { hasEnded, play, pause, playFrom } = player
  const start = useCallback(() => {
    setMode('presenting')
    if (hasEnded) playFrom(0)
    else play()
  }, [hasEnded, play, playFrom])
  const read = useCallback(() => {
    pause()
    setMode('reading')
  }, [pause])

  // Each screen starts at its top, not wherever the last one was scrolled to.
  useEffect(() => {
    if (screen !== 'presenting') window.scrollTo({ top: 0 })
  }, [screen])

  const { meta } = report
  const canResume = player.currentIndex > 0 && !player.hasEnded

  return (
    <NarrationSyncProvider
      activeId={presenting ? focus.primaryId : null}
      citedIds={presenting ? focus.citedIds : NO_IDS}
      targets={targets}
    >
      <div className="report-view" data-screen={screen}>
        <header className="session-bar">
          <span className="session-bar__title">
            <strong>{meta.company_name}</strong>
            <span className="session-bar__period">{meta.fiscal_period}</span>
            {sampleLabel && (
              <span className="session-bar__badge" title="A saved walkthrough - nothing is generated while you watch">
                {sampleLabel}
              </span>
            )}
          </span>
          <span className="session-bar__actions">
            {screen === 'reading' && player.hasEnded && (
              // The walkthrough is still at its end, so going back into it lands on the
              // closing screen rather than starting over.
              <button type="button" className="session-bar__button" onClick={() => setMode('presenting')}>
                Back to summary
              </button>
            )}
            {screen === 'reading' && (
              <button
                type="button"
                className="session-bar__button session-bar__button--primary"
                onClick={start}
                disabled={narration.status === 'loading'}
              >
                {narration.status === 'loading'
                  ? 'Preparing walkthrough…'
                  : player.hasEnded
                    ? 'Watch again'
                    : canResume
                      ? 'Resume walkthrough'
                      : 'Start walkthrough'}
              </button>
            )}
            {presenting ? (
              <button type="button" className="session-bar__button" onClick={read}>
                Exit walkthrough
              </button>
            ) : (
              <button type="button" className="session-bar__button" onClick={onExit}>
                Back to start
              </button>
            )}
          </span>
        </header>

        {screen === 'cover' && (
          <CoverScreen
            report={report}
            status={narration.status}
            error={narration.error}
            lineCount={narration.script.length}
            durationMs={totalDurationMs}
            canResume={canResume}
            onStart={start}
            onRead={read}
            onRetry={narration.retry}
          />
        )}

        {screen === 'closing' && (
          <ClosingScreen
            report={report}
            script={narration.script}
            mentions={mentions}
            onReplay={() => playFrom(0)}
            onSeek={playFrom}
            onRead={read}
            onExit={onExit}
          />
        )}

        {(screen === 'presenting' || screen === 'reading') && (
          <ReportBody
            report={report}
            narration={narration}
            player={player}
            presenting={presenting}
            segments={segments}
            mentions={mentions}
            onExit={read}
          />
        )}
      </div>
    </NarrationSyncProvider>
  )
}

interface ReportBodyProps {
  report: FinancialReport
  narration: GeneratedNarration
  player: NarrationPlayerState
  presenting: boolean
  segments: Segment[]
  mentions: Mention[]
  onExit: () => void
}

function isInteractive(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && target.closest('button, a, input, textarea, select') !== null
}

function ReportBody({ report, narration, player, presenting, segments, mentions, onExit }: ReportBodyProps) {
  const { activeId, activeTarget, getElement } = useNarrationSync()
  const [notesOpen, setNotesOpen] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  const { trace } = narration
  const line = player.currentLine
  const visual = line?.visual

  useEffect(() => {
    if (!activeId) return
    // On a phone the card docks over the bottom of the screen, so the target goes to
    // the top (below the bar, see `scroll-margin-top`) instead of the middle. `inline`
    // also brings a figure in a sideways-scrolling table into view.
    const narrow = window.innerWidth <= DOCKED_BELOW_PX
    getElement(activeId)?.scrollIntoView({ behavior: 'smooth', block: narrow ? 'start' : 'center', inline: 'center' })
  }, [activeId, getElement])

  // Presenting from a keyboard or a clicker: space pauses, the arrows step.
  const { isPlaying, play, pause, next, prev } = player
  useEffect(() => {
    if (!presenting) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isInteractive(event.target)) return
      if (event.key === ' ') {
        event.preventDefault()
        if (isPlaying) pause()
        else play()
      } else if (event.key === 'ArrowRight') {
        next()
      } else if (event.key === 'ArrowLeft') {
        prev()
      } else if (event.key === 'Escape') {
        onExit()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [presenting, isPlaying, play, pause, next, prev, onExit])

  let card: ReactNode = null
  if (presenting && line && !activeId) {
    // Keyed by line so each remark fades in afresh.
    card = <SpotlightLine key={player.currentIndex} text={line.text} visual={visual} />
  } else if (activeId && visual) {
    // Keyed by chart, not by target: while consecutive lines stay on one chart the
    // card stays up and only moves its emphasis.
    card = <VisualCard key={visual.chart.id} anchorId={activeId} visual={visual} />
  } else if (activeId && activeTarget && activeTarget.kind !== 'block') {
    // Keyed by target so each new line's card pops in afresh.
    card = <FocusCard key={activeId} anchorId={activeId} target={activeTarget} />
  }

  const mentionsReached = mentions.filter((mention) => mention.lineIndex <= player.currentIndex).length

  return (
    <div className="report-view__stage">
      <div className="report-view__body">
        <BlockList blocks={report.blocks} />
      </div>
      {card}
      {presenting && (
        <>
          <FigureRail
            mentions={mentions}
            currentIndex={player.currentIndex}
            open={railOpen}
            onClose={() => setRailOpen(false)}
            onSeek={player.seek}
          />
          {notesOpen && trace && (
            <AdvisorNotes trace={trace} lineCount={narration.script.length} onClose={() => setNotesOpen(false)} />
          )}
          <NarrationPlayer
            currentIndex={player.currentIndex}
            total={player.total}
            currentText={line?.text ?? null}
            currentSources={line?.sources}
            isPlaying={player.isPlaying}
            durationMs={player.durationMs}
            segments={segments}
            captionsOnly={narration.audio !== null && !player.isSpoken}
            notice={
              narration.status === 'failed' && (
                <>
                  <span title={narration.error ?? undefined}>
                    Couldn't prepare the advisor's narration - playing a basic walkthrough instead.
                  </span>
                  <button type="button" className="narration-player__text-button" onClick={narration.retry}>
                    Retry
                  </button>
                </>
              )
            }
            actions={
              <>
                <button
                  type="button"
                  className="narration-player__text-button report-view__rail-toggle"
                  onClick={() => setRailOpen((open) => !open)}
                  aria-expanded={railOpen}
                >
                  Figures · {mentionsReached}
                </button>
                <button
                  type="button"
                  className="narration-player__text-button"
                  onClick={() => setNotesOpen((open) => !open)}
                  disabled={!trace}
                  aria-expanded={notesOpen && !!trace}
                  title={trace ? undefined : 'Only available for a walkthrough the advisor prepared'}
                >
                  Advisor's notes
                </button>
              </>
            }
            onPlay={player.play}
            onPause={player.pause}
            onNext={player.next}
            onPrev={player.prev}
            onSeek={player.seek}
          />
        </>
      )}
    </div>
  )
}
