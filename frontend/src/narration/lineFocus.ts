import type { NarrationTarget, TargetIndex } from './targetIndex'
import type { NarrationLine } from './types'

// What the page does for one line, worked out from the line's target and the figures
// it cites - not from what kind of line the script says it is, so it holds however the
// narration is written.
export interface LineFocus {
  // What the page scrolls to, highlights and hangs its card on. null for a line about
  // nothing in particular (an opening remark, a takeaway): highlighting a whole table
  // for it would point the viewer at nothing, so the line is shown on its own instead.
  primaryId: string | null
  // Other cells the line cites in the same table, lit along with the primary one - "up
  // from 94 to 109" lights both figures.
  citedIds: string[]
}

const NO_FOCUS: LineFocus = { primaryId: null, citedIds: [] }

function tableId(target: NarrationTarget): string | null {
  if (target.kind === 'block') return target.block.type === 'table' ? target.block.id : null
  return target.table.id
}

export function resolveLineFocus(line: NarrationLine | null, targets: TargetIndex): LineFocus {
  if (!line) return NO_FOCUS
  const target = targets.get(line.target_id)
  if (!target) return NO_FOCUS
  // A paragraph or a chart is a precise enough target as it is.
  const table = tableId(target)
  if (table === null) return { primaryId: line.target_id, citedIds: [] }

  // Absent on scripts saved before lines listed their figures, and on the stub script:
  // those lines light their target alone.
  const cited: string[] = []
  for (const figure of line.figures ?? []) {
    const figureTarget = targets.get(figure.id)
    if (figureTarget?.kind === 'cell' && figureTarget.table.id === table && !cited.includes(figure.id)) {
      cited.push(figure.id)
    }
  }

  if (target.kind === 'block') {
    // A whole table: narrow it to the figures the line cites there, if it cites any.
    const [first, ...rest] = cited
    return first ? { primaryId: first, citedIds: rest } : NO_FOCUS
  }
  return { primaryId: line.target_id, citedIds: cited.filter((id) => id !== line.target_id) }
}
