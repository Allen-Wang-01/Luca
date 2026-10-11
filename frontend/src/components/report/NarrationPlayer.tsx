import { useLayoutEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import type { Segment } from '../../narration/segments'
import { sourceLabel } from '../../narration/sourceLabel'
import { SegmentedProgress } from './SegmentedProgress'
import './NarrationPlayer.css'

interface NarrationPlayerProps {
  currentIndex: number
  total: number
  currentText: string | null
  // Web pages the current line draws on, shown as links under the caption.
  currentSources?: string[]
  isPlaying: boolean
  durationMs: number
  // The parts of the report the script passes through, for the progress bar.
  segments: Segment[]
  // The script has audio, but not for the current line - say so, so a silent stretch
  // doesn't look like broken playback.
  captionsOnly?: boolean
  // A one-line strip above the controls, e.g. explaining a fallback script.
  notice?: ReactNode
  // Right-hand slot for extra controls.
  actions?: ReactNode
  onPlay: () => void
  onPause: () => void
  onNext: () => void
  onPrev: () => void
  onSeek: (index: number) => void
}

// Fixed bottom bar. The caption shows the line being spoken; for lines without audio
// it stands in for the voice. Either way it's the visible proof that scroll/highlight
// sync is actually following the script, not just decoration.
export function NarrationPlayer({
  currentIndex,
  total,
  currentText,
  currentSources = [],
  isPlaying,
  durationMs,
  segments,
  captionsOnly = false,
  notice,
  actions,
  onPlay,
  onPause,
  onNext,
  onPrev,
  onSeek,
}: NarrationPlayerProps) {
  const inert = total === 0
  const segment = segments.find((s) => currentIndex >= s.start && currentIndex < s.start + s.count)

  // The bar grows and shrinks with its caption. Whatever else is fixed to the window
  // (the spotlight line, the figure rail, the notes panel) keeps clear of it through
  // this variable rather than by guessing its height.
  const barRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const bar = barRef.current
    if (!bar) return
    const root = document.documentElement
    const publish = () => root.style.setProperty('--narration-bar-height', `${bar.offsetHeight}px`)
    publish()
    const observer = new ResizeObserver(publish)
    observer.observe(bar)
    return () => {
      observer.disconnect()
      root.style.removeProperty('--narration-bar-height')
    }
  }, [])

  return (
    <div ref={barRef} className="narration-player">
      {notice && <div className="narration-player__notice">{notice}</div>}
      <SegmentedProgress
        segments={segments}
        currentIndex={currentIndex}
        isPlaying={isPlaying}
        durationMs={durationMs}
        onSeek={onSeek}
      />

      <div className="narration-player__row">
        <div className="narration-player__controls">
          <button
            type="button"
            className="narration-player__button"
            onClick={onPrev}
            disabled={inert || currentIndex === 0}
            aria-label="Previous line"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 6h2v12H6zM20 6v12l-9-6z" />
            </svg>
          </button>

          <button
            type="button"
            className="narration-player__button narration-player__button--primary"
            onClick={isPlaying ? onPause : onPlay}
            disabled={inert}
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M7 5l13 7-13 7z" />
              </svg>
            )}
          </button>

          <button
            type="button"
            className="narration-player__button"
            onClick={onNext}
            disabled={inert || currentIndex >= total - 1}
            aria-label="Next line"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M16 6h2v12h-2zM4 6v12l9-6z" />
            </svg>
          </button>

          <span className="narration-player__counter">{inert ? '– / –' : `${currentIndex + 1} / ${total}`}</span>
          {captionsOnly && !inert && (
            <span className="narration-player__tag" title="No audio was generated for this line">
              Captions only
            </span>
          )}
        </div>

        <div className="narration-player__caption-group">
          {segment && <p className="narration-player__segment">{segment.label}</p>}
          <p className="narration-player__caption">{currentText}</p>
          {currentSources.length > 0 && (
            <p className="narration-player__sources">
              Source{currentSources.length > 1 ? 's' : ''}:{' '}
              {currentSources.map((url, i) => (
                <span key={url}>
                  {i > 0 && ', '}
                  <a href={url} target="_blank" rel="noopener noreferrer" title={url}>
                    {sourceLabel(url)}
                  </a>
                </span>
              ))}
            </p>
          )}
        </div>

        {actions && <div className="narration-player__actions">{actions}</div>}
      </div>
    </div>
  )
}
