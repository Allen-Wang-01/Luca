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

// Ids of everything that contains the target: a cell's row and table, a row's table.
export function ancestorIds(target: NarrationTarget | undefined): string[] {
  if (!target || target.kind === 'block') return []
  return target.kind === 'row' ? [target.table.id] : [target.row.id, target.table.id]
}
