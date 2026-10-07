import type { LineVisual } from '../../narration/types'
import { AnchoredCard } from './AnchoredCard'
import { VisualChart } from './charts/VisualChart'
import './VisualCard.css'

interface VisualCardProps {
  anchorId: string
  visual: LineVisual
}

// The chart the narration brought up for the current line, floating next to whatever
// that line highlights - a table figure or a paragraph alike. It takes the place of the
// figure card: the chart already shows the numbers.
export function VisualCard({ anchorId, visual }: VisualCardProps) {
  return (
    <AnchoredCard anchorId={anchorId} className="visual-card">
      <div className="visual-card__title">{visual.chart.title}</div>
      <VisualChart chart={visual.chart} emphasis={visual.emphasis} />
    </AnchoredCard>
  )
}
