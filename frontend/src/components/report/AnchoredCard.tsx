import { useLayoutEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useNarrationSync } from './NarrationSyncContext'
import './AnchoredCard.css'

interface AnchoredCardProps {
  // Id of the narration target the card floats next to.
  anchorId: string
  className?: string
  children: ReactNode
}

const GAP_PX = 14
const VIEWPORT_MARGIN_PX = 12
const ARROW_INSET_PX = 22
// Keep in sync with the phone breakpoint in the stylesheets.
export const DOCKED_BELOW_PX = 640

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

// A card floating next to whatever is being narrated, with an arrow pointing at it:
// above it when there's room, otherwise below. Shared by the cards that repeat a table
// figure at a readable size and the ones that show a chart.
export function AnchoredCard({ anchorId, className, children }: AnchoredCardProps) {
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
        // The narration bar is fixed to the bottom of the window; a card below a tall
        // target (a long paragraph, a whole table) must not slide underneath it.
        const floor = document.querySelector('.narration-player')?.getBoundingClientRect().top ?? window.innerHeight
        const lowest = floor - height - VIEWPORT_MARGIN_PX
        // On a phone a card is nearly as wide as the screen, and one that followed its
        // target around would cover the table it points into. It docks above the
        // narration bar instead, and the page keeps the target in the space over it
        // (see the scroll in ReportView).
        if (window.innerWidth <= DOCKED_BELOW_PX) {
          card.style.transform = `translate3d(${VIEWPORT_MARGIN_PX}px, ${Math.round(Math.max(VIEWPORT_MARGIN_PX, lowest))}px, 0)`
          card.dataset.placement = 'docked'
          frame = requestAnimationFrame(place)
          return
        }
        const fitsAbove = bounds.top - height - GAP_PX >= VIEWPORT_MARGIN_PX
        const below = bounds.bottom + GAP_PX
        const top = fitsAbove ? bounds.top - height - GAP_PX : Math.max(VIEWPORT_MARGIN_PX, Math.min(below, lowest))

        card.style.transform = `translate3d(${Math.round(left)}px, ${Math.round(top)}px, 0)`
        card.style.setProperty('--anchored-card-arrow-x', `${clamp(centerX - left, ARROW_INSET_PX, width - ARROW_INSET_PX)}px`)
        // 'over': neither side had room, so the card sits on top of its target and an
        // arrow would point at nothing.
        card.dataset.placement = fitsAbove ? 'above' : below <= lowest ? 'below' : 'over'
      }
      frame = requestAnimationFrame(place)
    }
    place()
    return () => cancelAnimationFrame(frame)
  }, [anchorId, getElement])

  // The card repeats what's already in the report, so it's hidden from assistive tech.
  return createPortal(
    <div ref={cardRef} className="anchored-card" aria-hidden="true">
      <div className={`anchored-card__body${className ? ` ${className}` : ''}`}>{children}</div>
    </div>,
    document.body,
  )
}
