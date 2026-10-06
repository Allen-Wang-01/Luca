import { useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import type { NarrationTarget } from '../../narration/targetIndex'
import { useNarrationSync } from './NarrationSyncContext'
import { formatCellValue } from './formatCellValue'
import './FocusCard.css'

type TableTarget = Exclude<NarrationTarget, { kind: 'block' }>

interface FocusCardProps {
  anchorId: string
  target: TableTarget
}

const GAP_PX = 14
const VIEWPORT_MARGIN_PX = 12
const ARROW_INSET_PX = 22

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

// A row can be wider than its table's horizontal scroll area; anchor to the part of it
// that's actually on screen, so the card doesn't centre itself over clipped columns.
function visibleBounds(anchor: HTMLElement) {
  const rect = anchor.getBoundingClientRect()
  const scroller = anchor.closest('.table-block__scroll')?.getBoundingClientRect()
  return {
    top: rect.top,
    bottom: rect.bottom,
    left: scroller ? Math.max(rect.left, scroller.left) : rect.left,
    right: scroller ? Math.min(rect.right, scroller.right) : rect.right,
  }
}

// Table rows and cells are too tightly packed to scale up in place, so the figure being
// narrated is repeated in a large card floating next to it - readable from the back of
// a room or over a screen share, which a background tint on a 13px cell is not.
export function FocusCard({ anchorId, target }: FocusCardProps) {
  const { getElement } = useNarrationSync()
  const cardRef = useRef<HTMLDivElement>(null)

  // Re-placed every frame rather than on scroll events: the anchor moves with the
  // page's smooth scroll and with the table's own scroll container, and a frame loop
  // follows both without listening to each one.
  useLayoutEffect(() => {
    let frame = 0
    const place = () => {
      const card = cardRef.current
      const anchor = getElement(anchorId)
      if (card && anchor) {
        const bounds = visibleBounds(anchor)
        const width = card.offsetWidth
        const height = card.offsetHeight
        const centerX = (bounds.left + bounds.right) / 2
        const left = clamp(centerX - width / 2, VIEWPORT_MARGIN_PX, window.innerWidth - width - VIEWPORT_MARGIN_PX)
        const fitsAbove = bounds.top - height - GAP_PX >= VIEWPORT_MARGIN_PX
        const top = fitsAbove ? bounds.top - height - GAP_PX : bounds.bottom + GAP_PX

        card.style.transform = `translate3d(${Math.round(left)}px, ${Math.round(top)}px, 0)`
        card.style.setProperty('--focus-card-arrow-x', `${clamp(centerX - left, ARROW_INSET_PX, width - ARROW_INSET_PX)}px`)
        card.dataset.placement = fitsAbove ? 'above' : 'below'
      }
      frame = requestAnimationFrame(place)
    }
    place()
    return () => cancelAnimationFrame(frame)
  }, [anchorId, getElement])

  const { table, row } = target

  // The card repeats what's already in the table, so it's hidden from assistive tech.
  return createPortal(
    <div ref={cardRef} className="focus-card" aria-hidden="true">
      <div className="focus-card__body">
        <div className="focus-card__eyebrow">{table.title}</div>
        {target.kind === 'cell' ? (
          <>
            <div className="focus-card__metric">
              {row.label}
              {target.column && <span className="focus-card__period">{target.column.label}</span>}
            </div>
            <div className="focus-card__value">{formatCellValue(target.cell)}</div>
            {table.unit && target.cell.value_type !== 'percent' && target.cell.value_type !== 'text' && (
              <div className="focus-card__unit">{table.unit}</div>
            )}
          </>
        ) : (
          <>
            <div className="focus-card__metric">{row.label}</div>
            {row.cells.length > 0 && (
              <dl className="focus-card__series">
                {table.columns.map((column) => {
                  const cell = row.cells.find((c) => c.col_id === column.id)
                  return (
                    cell && (
                      <div key={column.id} className="focus-card__series-item">
                        <dt>{column.label}</dt>
                        <dd>{formatCellValue(cell)}</dd>
                      </div>
                    )
                  )
                })}
              </dl>
            )}
            {table.unit && <div className="focus-card__unit">{table.unit}</div>}
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
