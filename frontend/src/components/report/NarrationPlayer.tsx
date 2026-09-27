import './NarrationPlayer.css'

interface NarrationPlayerProps {
  currentIndex: number
  total: number
  currentText: string | null
  isPlaying: boolean
  durationMs: number
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
  isPlaying,
  durationMs,
  onPlay,
  onPause,
  onNext,
  onPrev,
}: NarrationPlayerProps) {
  if (total === 0) return null

  return (
    <div className="narration-player">
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
            disabled={currentIndex === 0}
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
            disabled={currentIndex >= total - 1}
            aria-label="Next line"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M16 6h2v12h-2zM4 6v12l9-6z" />
            </svg>
          </button>

          <span className="narration-player__counter">
            {currentIndex + 1} / {total}
          </span>
        </div>

        <p className="narration-player__caption">{currentText}</p>
      </div>
    </div>
  )
}
