import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FinancialReport } from '../../types/report'
import { buildTargetIndex } from '../../narration/targetIndex'
import { useGeneratedNarration, type GeneratedNarration } from '../../narration/useGeneratedNarration'
import { useNarrationPlayer, type NarrationPlayer as NarrationPlayerState } from '../../narration/useNarrationPlayer'
import { NarrationSyncProvider, useNarrationSync } from './NarrationSyncContext'
import { NarrationPlayer } from './NarrationPlayer'
import { AdvisorNotes } from './AdvisorNotes'
import { BlockList } from './BlockList'
import { FocusCard } from './FocusCard'
import { VisualCard } from './VisualCard'
import './sync.css'
import './ReportView.css'

interface ReportViewProps {
  report: FinancialReport
}

export function ReportView({ report }: ReportViewProps) {
  const narration = useGeneratedNarration(report)
  const player = useNarrationPlayer(narration.script, narration.audio)

  // Sync (scroll/highlight/scale) only kicks in once the reader has actually engaged
  // with the player - otherwise the first block would appear "active" the instant the
  // report loads, before anything has been narrated. A new script (the generated one
  // arriving after a retry, say) needs the same fresh start.
  const [hasStarted, setHasStarted] = useState(false)
  const [prevScript, setPrevScript] = useState(narration.script)
  if (narration.script !== prevScript) {
    setPrevScript(narration.script)
    setHasStarted(false)
  }
  const markStarted = useCallback(() => setHasStarted(true), [])

  const handlePlay = useCallback(() => {
    markStarted()
    player.play()
  }, [markStarted, player])
  const handleNext = useCallback(() => {
    markStarted()
    player.next()
  }, [markStarted, player])
  const handlePrev = useCallback(() => {
    markStarted()
    player.prev()
  }, [markStarted, player])

  const activeId = hasStarted ? (player.currentLine?.target_id ?? null) : null
  const targets = useMemo(() => buildTargetIndex(report), [report])

  return (
    <NarrationSyncProvider activeId={activeId} targets={targets}>
      <ReportViewInner
        report={report}
        narration={narration}
        player={player}
        onPlay={handlePlay}
        onNext={handleNext}
        onPrev={handlePrev}
      />
    </NarrationSyncProvider>
  )
}

interface ReportViewInnerProps {
  report: FinancialReport
  narration: GeneratedNarration
  player: NarrationPlayerState
  onPlay: () => void
  onNext: () => void
  onPrev: () => void
}

function ReportViewInner({ report, narration, player, onPlay, onNext, onPrev }: ReportViewInnerProps) {
  const { activeId, activeTarget, getElement } = useNarrationSync()
  const [notesOpen, setNotesOpen] = useState(false)
  const { trace } = narration
  const visual = player.currentLine?.visual

  useEffect(() => {
    if (!activeId) return
    const element = getElement(activeId)
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeId, getElement])

  return (
    <div className="report-view">
      <BlockList blocks={report.blocks} />
      {activeId && visual ? (
        // Keyed by chart, not by target: while consecutive lines stay on one chart the
        // card stays up and only moves its emphasis.
        <VisualCard key={visual.chart.id} anchorId={activeId} visual={visual} />
      ) : (
        activeId &&
        activeTarget &&
        activeTarget.kind !== 'block' && (
          // Keyed by target so each new line's card pops in afresh.
          <FocusCard key={activeId} anchorId={activeId} target={activeTarget} />
        )
      )}
      {notesOpen && trace && (
        <AdvisorNotes trace={trace} lineCount={narration.script.length} onClose={() => setNotesOpen(false)} />
      )}
      <NarrationPlayer
        currentIndex={player.currentIndex}
        total={player.total}
        currentText={player.currentLine?.text ?? null}
        currentSources={player.currentLine?.sources}
        isPlaying={player.isPlaying}
        durationMs={player.durationMs}
        captionsOnly={narration.audio !== null && !player.isSpoken}
        disabled={narration.status === 'loading'}
        placeholder={
          <>
            <span className="spinner" aria-hidden="true" />
            Your advisor is reading the report and running the numbers…
          </>
        }
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
          <button
            type="button"
            className="narration-player__text-button"
            onClick={() => setNotesOpen((open) => !open)}
            disabled={!trace}
            aria-expanded={notesOpen && !!trace}
            title={trace ? undefined : 'Available once the advisor has finished preparing'}
          >
            Advisor's notes
          </button>
        }
        onPlay={onPlay}
        onPause={player.pause}
        onNext={onNext}
        onPrev={onPrev}
      />
    </div>
  )
}
