import { useCallback, useEffect, useState } from 'react'
import type { FinancialReport } from '../../types/report'
import { useGeneratedNarration, type GeneratedNarration } from '../../narration/useGeneratedNarration'
import { useNarrationPlayer, type NarrationPlayer as NarrationPlayerState } from '../../narration/useNarrationPlayer'
import { NarrationSyncProvider, useNarrationSync } from './NarrationSyncContext'
import { NarrationPlayer } from './NarrationPlayer'
import { AdvisorNotes } from './AdvisorNotes'
import { BlockList } from './BlockList'
import './sync.css'
import './ReportView.css'

interface ReportViewProps {
  report: FinancialReport
}

export function ReportView({ report }: ReportViewProps) {
  const narration = useGeneratedNarration(report)
  const player = useNarrationPlayer(narration.script)

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

  return (
    <NarrationSyncProvider activeId={activeId}>
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
  const { activeId, getElement } = useNarrationSync()
  const [notesOpen, setNotesOpen] = useState(false)
  const { trace } = narration

  useEffect(() => {
    if (!activeId) return
    const element = getElement(activeId)
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeId, getElement])

  return (
    <div className="report-view">
      <BlockList blocks={report.blocks} />
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
