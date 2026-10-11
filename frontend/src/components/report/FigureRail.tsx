import { useEffect, useRef } from 'react'
import type { Mention } from '../../narration/mentions'
import './FigureRail.css'

const CHART_TYPE_LABELS = { bar: 'Bar chart', share: 'Share of total', waterfall: 'Waterfall' } as const

interface MentionTileProps {
  mention: Mention
  current?: boolean
  onSelect: () => void
}

// One thing the walkthrough pointed at. Clicking it goes back to the line that did.
export function MentionTile({ mention, current = false, onSelect }: MentionTileProps) {
  return (
    <button type="button" className="mention-tile" data-kind={mention.kind} data-current={current} onClick={onSelect}>
      {mention.kind === 'chart' ? (
        <>
          <span className="mention-tile__eyebrow">{CHART_TYPE_LABELS[mention.chart.type]}</span>
          <span className="mention-tile__label">{mention.chart.title}</span>
        </>
      ) : (
        <>
          <span className="mention-tile__label">{mention.label}</span>
          <span className="mention-tile__values">
            {mention.values.map((entry, i) => (
              <span key={i} className="mention-tile__entry">
                <span className="mention-tile__value">{entry.value}</span>
                {entry.period && <span className="mention-tile__period">{entry.period}</span>}
              </span>
            ))}
          </span>
          {mention.unit && <span className="mention-tile__unit">{mention.unit}</span>}
        </>
      )}
    </button>
  )
}

interface FigureRailProps {
  mentions: Mention[]
  currentIndex: number
  // Only matters on screens too narrow for the rail to stay up beside the report,
  // where it is a drawer.
  open: boolean
  onClose: () => void
  onSeek: (index: number) => void
}

// The figures and charts mentioned so far, building up beside the report as the
// walkthrough goes - what this company's report had that was worth pointing at.
export function FigureRail({ mentions, currentIndex, open, onClose, onSeek }: FigureRailProps) {
  const reached = mentions.filter((mention) => mention.lineIndex <= currentIndex)
  const listRef = useRef<HTMLDivElement>(null)

  // Keeps the newest one in view as the list grows.
  useEffect(() => {
    const list = listRef.current
    list?.scrollTo({ top: list.scrollHeight, behavior: 'smooth' })
  }, [reached.length])

  return (
    <aside className="figure-rail" data-open={open} aria-label="Figures mentioned so far">
      <div className="figure-rail__header">
        <h2 className="figure-rail__title">
          Mentioned so far
          <span className="figure-rail__count">{reached.length}</span>
        </h2>
        <button type="button" className="figure-rail__close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <div ref={listRef} className="figure-rail__list">
        {reached.length === 0 ? (
          <p className="figure-rail__empty">Figures and charts collect here as your advisor points them out.</p>
        ) : (
          reached.map((mention) => (
            <MentionTile
              key={mention.key}
              mention={mention}
              current={mention.lineIndex === currentIndex}
              onSelect={() => {
                onSeek(mention.lineIndex)
                onClose()
              }}
            />
          ))
        )}
      </div>
    </aside>
  )
}
