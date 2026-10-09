import type { Block, Cell, Column, FinancialReport, Row, TableBlock } from '../types/report'

// What a narration line's `target_id` points at, with the surrounding table context a
// row or cell needs to be shown on its own (its metric label, its period, its unit).
export type NarrationTarget =
  | { kind: 'block'; block: Block }
  | { kind: 'row'; table: TableBlock; row: Row }
  | { kind: 'cell'; table: TableBlock; row: Row; cell: Cell; column: Column | null }

export type TargetIndex = Map<string, NarrationTarget>

export function buildTargetIndex(report: FinancialReport): TargetIndex {
  const index: TargetIndex = new Map()
  for (const block of report.blocks) {
    index.set(block.id, { kind: 'block', block })
    if (block.type !== 'table') continue

    const columnById = new Map(block.columns.map((column) => [column.id, column]))
    for (const row of block.rows) {
      index.set(row.id, { kind: 'row', table: block, row })
      for (const cell of row.cells) {
        index.set(cell.id, { kind: 'cell', table: block, row, cell, column: columnById.get(cell.col_id) ?? null })
      }
    }
  }
  return index
}

// The three below name a row, a column and a row's unit for display away from the
// table itself. There the sub-heading above a row and the group header over a column
// are out of sight, so the label has to carry them. The backend names figures the same
// way for the narration model (backend/app/services/report_labels.py).

// The row's label, with its sub-heading in front where several rows share the label.
export function rowLabel(table: TableBlock, row: Row): string {
  const shared = table.rows.filter((other) => other.cells.length > 0 && other.label === row.label).length > 1
  return row.group && shared ? `${row.group} · ${row.label}` : row.label
}

// The column's label, with its group header in front if it has one.
export function columnLabel(table: TableBlock, column: Column): string {
  const group = table.column_groups.find((g) => g.col_ids.includes(column.id))
  return group ? `${group.label} · ${column.label}` : column.label
}

// What the row's figures are in. The table's unit line covers its amounts of money; a
// row that measures something else, or is printed in a scale of its own, needs its own.
export function rowUnit(table: TableBlock, row: Row): string | null {
  switch (row.quantity) {
    case 'per_share':
      return 'Per share'
    case 'share_count':
      return row.scale && row.scale !== 'actual' ? `Shares, in ${row.scale}` : 'Shares'
    case 'percent':
    case 'other':
      return null
    default:
      return table.unit
  }
}

// Ids of everything that contains the target: a cell's row and table, a row's table.
export function ancestorIds(target: NarrationTarget | undefined): string[] {
  if (!target || target.kind === 'block') return []
  return target.kind === 'row' ? [target.table.id] : [target.row.id, target.table.id]
}
