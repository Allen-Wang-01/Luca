import { formatCellValue } from '../components/report/formatCellValue'
import { resolveLineFocus } from './lineFocus'
import { columnLabel, rowLabel, rowUnit, type TargetIndex } from './targetIndex'
import type { NarrationScript, Visual } from './types'

// Something the walkthrough has pointed at: a figure it highlighted, or a chart it
// brought up. Collected in the order they come up, they are what sets one company's
// walkthrough apart from another's, and by the end they are its summary. Built from
// each line's target, figures and chart alone - nothing the narration has to write.
export type Mention =
  | {
      kind: 'figure'
      key: string
      lineIndex: number // the first line that points at it
      label: string
      table: string
      // One entry for a single figure; a row brings the figures the line cites from it.
      values: { period: string | null; value: string }[]
      unit: string | null
    }
  | { kind: 'chart'; key: string; lineIndex: number; chart: Visual }

const MAX_ROW_VALUES = 2

export function buildMentions(script: NarrationScript, targets: TargetIndex): Mention[] {
  const mentions: Mention[] = []
  const seen = new Set<string>()

  script.forEach((line, lineIndex) => {
    const chart = line.visual?.chart
    if (chart && !seen.has(chart.id)) {
      seen.add(chart.id)
      mentions.push({ kind: 'chart', key: chart.id, lineIndex, chart })
    }

    const { primaryId, citedIds } = resolveLineFocus(line, targets)
    const target = primaryId === null ? undefined : targets.get(primaryId)
    if (!primaryId || !target || target.kind === 'block' || seen.has(primaryId)) return
    seen.add(primaryId)

    const { table, row } = target
    const cells =
      target.kind === 'cell'
        ? [target.cell]
        : // The figures the line cites from the row; all of them where it lists none.
          (row.cells.some((cell) => citedIds.includes(cell.id))
            ? row.cells.filter((cell) => citedIds.includes(cell.id))
            : row.cells
          ).slice(0, MAX_ROW_VALUES)
    if (cells.length === 0) return

    const plain = cells.every((cell) => cell.value_type === 'percent' || cell.value_type === 'text')
    mentions.push({
      kind: 'figure',
      key: primaryId,
      lineIndex,
      label: rowLabel(table, row),
      table: table.title,
      values: cells.map((cell) => {
        const column = table.columns.find((c) => c.id === cell.col_id)
        return { period: column ? columnLabel(table, column) : null, value: formatCellValue(cell) }
      }),
      unit: plain ? null : rowUnit(table, row),
    })
  })
  return mentions
}
