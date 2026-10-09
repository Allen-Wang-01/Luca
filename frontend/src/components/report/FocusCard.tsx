import { columnLabel, rowLabel, rowUnit, type NarrationTarget } from '../../narration/targetIndex'
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
  const label = rowLabel(table, row)
  const unit = rowUnit(table, row)

  return (
    <AnchoredCard anchorId={anchorId}>
      <div className="focus-card__eyebrow">{table.title}</div>
      {target.kind === 'cell' ? (
        <>
          <div className="focus-card__metric">
            {label}
            {target.column && <span className="focus-card__period">{columnLabel(table, target.column)}</span>}
          </div>
          <div className="focus-card__value">{formatCellValue(target.cell)}</div>
          {unit && target.cell.value_type !== 'percent' && target.cell.value_type !== 'text' && (
            <div className="focus-card__unit">{unit}</div>
          )}
        </>
      ) : (
        <>
          <div className="focus-card__metric">{label}</div>
          {row.cells.length > 0 && (
            <dl className="focus-card__series">
              {table.columns.map((column) => {
                const cell = row.cells.find((c) => c.col_id === column.id)
                return (
                  cell && (
                    <div key={column.id} className="focus-card__series-item">
                      <dt>{columnLabel(table, column)}</dt>
                      <dd>{formatCellValue(cell)}</dd>
                    </div>
                  )
                )
              })}
            </dl>
          )}
          {unit && <div className="focus-card__unit">{unit}</div>}
        </>
      )}
    </AnchoredCard>
  )
}
