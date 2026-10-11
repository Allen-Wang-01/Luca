import type { LineVisual } from '../../narration/types'
import { COMPUTED_MARK, VisualChart } from './charts/VisualChart'
import './SpotlightLine.css'

interface SpotlightLineProps {
  text: string
  // The line's chart, if it has one: with nothing in the report to hang it on, it is
  // shown under the line itself.
  visual?: LineVisual | null
}

// A line that is about nothing in particular in the report - an opening remark, a
// bridge, a takeaway. Lighting up a whole table for it would send the viewer looking
// for something that isn't there, so the page holds still and the line takes the
// middle of the screen.
export function SpotlightLine({ text, visual }: SpotlightLineProps) {
  return (
    <div className="spotlight-line" aria-hidden="true">
      <div className="spotlight-line__panel" data-with-chart={!!visual}>
        <p className="spotlight-line__text">{text}</p>
        {visual && (
          // Direct children of the panel, not wrapped: the panel is what runs out of
          // height, and only its own children can be made to give way (see the CSS).
          <>
            <div className="spotlight-line__chart-title">{visual.chart.title}</div>
            <VisualChart chart={visual.chart} emphasis={visual.emphasis} />
            {visual.chart.items.some((item) => item.computed) && (
              <div className="spotlight-line__note">{COMPUTED_MARK} Calculated from the report's figures</div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
