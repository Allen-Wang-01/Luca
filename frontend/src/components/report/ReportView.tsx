import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FinancialReport } from '../../types/report'
import { buildStubScript } from '../../narration/buildStubScript'
import { useNarrationPlayer, type NarrationPlayer as NarrationPlayerState } from '../../narration/useNarrationPlayer'
import { NarrationSyncProvider, useNarrationSync } from './NarrationSyncContext'
import { NarrationPlayer } from './NarrationPlayer'
import { BlockList } from './BlockList'
import './sync.css'
import './ReportView.css'

interface ReportViewProps {
  report: FinancialReport
}

export function ReportView({ report }: ReportViewProps) {
  const script = useMemo(() => buildStubScript(report), [report])
  const player = useNarrationPlayer(script)

  // Sync (scroll/highlight/scale) only kicks in once the reader has actually engaged
  // with the player - otherwise the first block would appear "active" the instant the
  // report loads, before anything has been narrated.
  const [hasStarted, setHasStarted] = useState(false)
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
  player: NarrationPlayerState
  onPlay: () => void
  onNext: () => void
  onPrev: () => void
}

function ReportViewInner({ report, player, onPlay, onNext, onPrev }: ReportViewInnerProps) {
  const { activeId, getElement } = useNarrationSync()

  useEffect(() => {
    if (!activeId) return
    const element = getElement(activeId)
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeId, getElement])

  return (
    <div className="report-view">
      <BlockList blocks={report.blocks} />
      <NarrationPlayer
        currentIndex={player.currentIndex}
        total={player.total}
        currentText={player.currentLine?.text ?? null}
        isPlaying={player.isPlaying}
        durationMs={player.durationMs}
        onPlay={onPlay}
        onPause={player.pause}
        onNext={onNext}
        onPrev={onPrev}
      />
    </div>
  )
}
