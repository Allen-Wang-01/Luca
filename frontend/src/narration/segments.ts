import type { Block, FinancialReport } from '../types/report'
import type { TargetIndex } from './targetIndex'
import type { NarrationScript } from './types'

// A stretch of consecutive lines that stay in one part of the report. The progress bar
// is cut into these, so its shape follows the report being walked through rather than
// any fixed outline of the narration.
export interface Segment {
  key: string
  label: string
  start: number // index of its first line
  count: number
}

const SMALL_WORDS = new Set(['a', 'an', 'and', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to'])

// Statement titles are often printed in capitals with a trailing "(Unaudited)"; as a
// label next to a progress bar they read better without either.
export function tidyTitle(title: string): string {
  const trimmed = title.replace(/\s*\([^)]*\)\s*$/, '').trim() || title.trim()
  if (trimmed !== trimmed.toUpperCase()) return trimmed
  return trimmed
    .toLowerCase()
    .split(/\s+/)
    .map((word, i) => (i > 0 && SMALL_WORDS.has(word) ? word : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(' ')
}

function blockLabel(block: Block): string {
  if (block.type === 'paragraph') return block.style === 'heading' ? block.text : 'Text'
  return block.title
}

export function buildSegments(script: NarrationScript, report: FinancialReport, targets: TargetIndex): Segment[] {
  // A block belongs to the section that lists it; one that no section lists stands for
  // itself.
  const partByBlockId = new Map<string, { key: string; label: string }>()
  for (const block of report.blocks) {
    partByBlockId.set(block.id, { key: block.id, label: tidyTitle(blockLabel(block)) })
  }
  for (const section of report.sections) {
    for (const blockId of section.block_ids) {
      if (partByBlockId.has(blockId)) partByBlockId.set(blockId, { key: section.id, label: tidyTitle(section.title) })
    }
  }

  const segments: Segment[] = []
  script.forEach((line, index) => {
    const target = targets.get(line.target_id)
    const blockId = !target ? null : target.kind === 'block' ? target.block.id : target.table.id
    const last = segments[segments.length - 1]
    // A line that points at nothing known stays with the lines before it.
    const part = (blockId !== null ? partByBlockId.get(blockId) : undefined) ?? last ?? { key: 'report', label: 'Report' }
    if (last && last.key === part.key) {
      last.count += 1
    } else {
      segments.push({ key: part.key, label: part.label, start: index, count: 1 })
    }
  })
  return segments
}
