import type { Segment } from '../../narration/segments'
import './SegmentedProgress.css'

interface SegmentedProgressProps {
  segments: Segment[]
  currentIndex: number
  isPlaying: boolean
  // How long the current line lasts; its share of the bar fills over that time.
  durationMs: number
  onSeek: (index: number) => void
}

// Progress through the whole walkthrough, cut into the parts of the report it passes
// through. Each part is as wide as the number of lines spent there and jumps to its
// first line when clicked.
export function SegmentedProgress({ segments, currentIndex, isPlaying, durationMs, onSeek }: SegmentedProgressProps) {
  return (
    <div className="segmented-progress">
      {segments.map((segment) => {
        const done = Math.min(Math.max(currentIndex - segment.start, 0), segment.count)
        const isCurrent = currentIndex >= segment.start && currentIndex < segment.start + segment.count
        return (
          <button
            key={`${segment.key}-${segment.start}`}
            type="button"
            className="segmented-progress__segment"
            data-current={isCurrent}
            style={{ flexGrow: segment.count }}
            title={segment.label}
            aria-label={`Jump to ${segment.label}`}
            onClick={() => onSeek(segment.start)}
          >
            <span className="segmented-progress__track">
              <span className="segmented-progress__done" style={{ width: `${(done / segment.count) * 100}%` }} />
              {isCurrent && (
                <span
                  className="segmented-progress__line"
                  style={{ left: `${(done / segment.count) * 100}%`, width: `${100 / segment.count}%` }}
                >
                  <span
                    key={currentIndex}
                    className="segmented-progress__line-fill"
                    style={{
                      animationDuration: `${durationMs}ms`,
                      animationPlayState: isPlaying ? 'running' : 'paused',
                    }}
                  />
                </span>
              )}
            </span>
          </button>
        )
      })}
    </div>
  )
}
