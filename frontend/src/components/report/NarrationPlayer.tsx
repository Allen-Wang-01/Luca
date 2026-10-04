import type { ReactNode } from 'react'
import { sourceLabel } from '../../narration/sourceLabel'
import './NarrationPlayer.css'

interface NarrationPlayerProps {
  currentIndex: number
  total: number
  currentText: string | null
  // Web pages the current line draws on, shown as links under the caption.
  currentSources?: string[]
  isPlaying: boolean
  durationMs: number
  // No script to play yet (e.g. narration still generating) - controls are inert and
  // `placeholder` takes the caption's place.
  disabled?: boolean
  placeholder?: ReactNode
  // A one-line strip above the controls, e.g. explaining a fallback script.
  notice?: ReactNode
  // Right-hand slot for extra controls.
  actions?: ReactNode
  onPlay: () => void
  onPause: () => void
  onNext: () => void
  onPrev: () => void
}

// Fixed bottom bar. There's no narration audio yet, so the caption text below the
// controls stands in for it - it's also the visible proof that scroll/highlight sync
// is actually following the script, not just decoration.
export function NarrationPlayer({
  currentIndex,
  total,
  currentText,
  currentSources = [],
  isPlaying,
  durationMs,
  disabled = false,
  placeholder,
  notice,
  actions,
  onPlay,
  onPause,
  onNext,
  onPrev,
}: NarrationPlayerProps) {
  const inert = disabled || total === 0

  return (
    <div className="narration-player">
      {notice && <div className="narration-player__notice">{notice}</div>}
      <div className="narration-player__progress-track">
        <div
          key={currentIndex}
          className="narration-player__progress-fill"
          style={{
            animationDuration: `${durationMs}ms`,
            animationPlayState: isPlaying ? 'running' : 'paused',
          }}
        />
      </div>

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
        </div>

        {inert && placeholder ? (
          <div className="narration-player__caption narration-player__caption--placeholder">{placeholder}</div>
        ) : (
          <div className="narration-player__caption-group">
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
        )}

        {actions && <div className="narration-player__actions">{actions}</div>}
      </div>
    </div>
  )
}
