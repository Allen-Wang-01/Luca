import type { ChartBlock } from '../../types/report'
import { useSyncTarget } from './NarrationSyncContext'
import { BarChart } from './charts/BarChart'
import { LineChart } from './charts/LineChart'
import { PieChart } from './charts/PieChart'
import './ChartBlockView.css'

interface ChartBlockViewProps {
  block: ChartBlock
}

export function ChartBlockView({ block }: ChartBlockViewProps) {
  const { ref, state } = useSyncTarget(block.id)

  return (
    <div ref={ref} data-sync={state} className="sync chart-block">
      <div className="chart-block__header">
        <h3 className="chart-block__title">{block.title}</h3>
        <div className="chart-block__meta">
          {block.unit && <span className="chart-block__unit">{block.unit}</span>}
          {block.confidence === 'low' && (
            <span className="chart-block__badge" title="Low extraction confidence">
              Low confidence
            </span>
          )}
        </div>
      </div>
      <div className="chart-block__body">
        {block.chart_type === 'pie' ? (
          <PieChart series={block.series} />
        ) : block.chart_type === 'line' ? (
          <LineChart series={block.series} />
        ) : (
          <BarChart series={block.series} stacked={block.chart_type === 'stacked_bar'} />
        )}
      </div>
      {block.note && <p className="chart-block__note">{block.note}</p>}
    </div>
  )
}
