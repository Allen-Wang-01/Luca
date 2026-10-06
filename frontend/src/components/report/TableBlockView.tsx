import type { Cell, Column, ColumnGroup, Flag, Row, TableBlock } from '../../types/report'
import { useSyncTarget } from './NarrationSyncContext'
import { formatCellValue } from './formatCellValue'
import './TableBlockView.css'

interface TableBlockViewProps {
  block: TableBlock
}

interface GroupHeaderCell {
  key: string
  label: string | null
  span: number
}

// column_groups only covers a contiguous range of columns some of the time (real data
// is usually one group spanning everything, but the schema doesn't guarantee that) -
// walk columns in order and merge runs that share the same group label, so ungrouped
// columns and partial coverage both render sensibly instead of assuming full coverage.
function buildGroupHeaderCells(columns: Column[], groups: ColumnGroup[]): GroupHeaderCell[] {
  const labelByColId = new Map<string, string>()
  for (const group of groups) {
    for (const colId of group.col_ids) {
      labelByColId.set(colId, group.label)
    }
  }

  const cells: GroupHeaderCell[] = []
  for (const column of columns) {
    const label = labelByColId.get(column.id) ?? null
    const last = cells[cells.length - 1]
    if (last && last.label === label) {
      last.span += 1
    } else {
      cells.push({ key: column.id, label, span: 1 })
    }
  }
  return cells
}

function FlagBadge({ flags }: { flags: Flag[] }) {
  if (flags.length === 0) return null
  const hasError = flags.some((flag) => flag.severity === 'error')
  const title = flags.map((flag) => flag.message).join('\n')
  return (
    <span
      className={`table-block__flag ${hasError ? 'table-block__flag--error' : 'table-block__flag--warning'}`}
      title={title}
      aria-label={title}
    >
      !
    </span>
  )
}

function TableCellView({ cell }: { cell: Cell }) {
  const { ref, state } = useSyncTarget(cell.id)
  return (
    <td
      ref={ref}
      data-sync={state}
      data-value-type={cell.value_type}
      className="sync--dense table-block__cell"
    >
      {formatCellValue(cell)}
    </td>
  )
}

function TableRowView({ row, columns }: { row: Row; columns: Column[] }) {
  const { ref, state } = useSyncTarget(row.id)
  return (
    <tr ref={ref} data-sync={state} className="sync--dense">
      <th scope="row" className="table-block__row-label">
        {row.label}
        <FlagBadge flags={row.flags} />
      </th>
      {columns.map((column) => {
        const cell = row.cells.find((c) => c.col_id === column.id)
        return cell ? <TableCellView key={cell.id} cell={cell} /> : <td key={column.id} className="table-block__cell" />
      })}
    </tr>
  )
}

export function TableBlockView({ block }: TableBlockViewProps) {
  const { ref, state } = useSyncTarget(block.id)
  const groupHeaderCells = block.column_groups.length > 0 ? buildGroupHeaderCells(block.columns, block.column_groups) : null

  return (
    <div ref={ref} data-sync={state} className="sync table-block">
      <div className="table-block__header">
        <h3 className="table-block__title">{block.title}</h3>
        <div className="table-block__meta">
          {block.unit && <span className="table-block__unit">{block.unit}</span>}
          {block.confidence === 'low' && (
            <span className="table-block__badge" title="Low extraction confidence">
              Low confidence
            </span>
          )}
          <FlagBadge flags={block.flags} />
        </div>
      </div>
      <div className="table-block__scroll">
        <table className="table-block__table">
          <thead>
            {groupHeaderCells && (
              <tr>
                <th className="table-block__row-label-header" />
                {groupHeaderCells.map((cell) => (
                  <th key={cell.key} colSpan={cell.span} className="table-block__group-header">
                    {cell.label ?? ''}
                  </th>
                ))}
              </tr>
            )}
            <tr>
              <th className="table-block__row-label-header" />
              {block.columns.map((column) => (
                <th key={column.id} className="table-block__col-header">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row) => (
              <TableRowView key={row.id} row={row} columns={block.columns} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
