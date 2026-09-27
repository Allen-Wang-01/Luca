import type { Block, FinancialReport } from '../types/report'
import type { NarrationScript } from './types'

function blockToText(block: Block): string {
  switch (block.type) {
    case 'paragraph':
      return block.text
    case 'table':
      return `${block.title}${block.unit ? ` (${block.unit})` : ''}`
    case 'chart':
      return block.title
  }
}

// Real narration script generation (an LLM turning the parsed report into
// analytical narration) doesn't exist yet, so this placeholder stands in for it: one
// line per block, in document order, block content as the line's text and the block
// id as its target. Swapping in the real generator later only means swapping what
// produces the script - the sync engine that consumes it doesn't change.
export function buildStubScript(report: FinancialReport): NarrationScript {
  return report.blocks.map((block) => ({
    text: blockToText(block),
    target_id: block.id,
  }))
}
