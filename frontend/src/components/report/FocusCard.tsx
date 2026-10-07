import type { NarrationTarget } from '../../narration/targetIndex'
import { AnchoredCard } from './AnchoredCard'
import { formatCellValue } from './formatCellValue'
import './FocusCard.css'

type TableTarget = Exclude<NarrationTarget, { kind: 'block' }>

interface FocusCardProps {
  anchorId: string
  target: TableTarget
}

// Table rows and cells are too tightly packed to scale up in place, so the figure being
// narrated is repeated in a large card floating next to it - readable from the back of
// a room or over a screen share, which a background tint on a 13px cell is not.
export function FocusCard({ anchorId, target }: FocusCardProps) {
  const { table, row } = target

  return (
    <AnchoredCard anchorId={anchorId}>
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
    </AnchoredCard>
  )
}
