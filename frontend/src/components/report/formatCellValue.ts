import type { Cell } from '../../types/report'

export function formatCellValue(cell: Cell): string {
  if (cell.raw_text) return cell.raw_text
  return cell.value === null ? '—' : String(cell.value)
}
