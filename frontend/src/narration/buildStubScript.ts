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

// Fallback for when the narration agent (useGeneratedNarration) fails: a basic
// walkthrough built locally, with no LLM - one line per block, in document order,
// block content as the line's text and the block id as its target. Same script shape
// as the generated narration, so the sync engine plays either one unchanged.
export function buildStubScript(report: FinancialReport): NarrationScript {
  return report.blocks.map((block) => ({
    text: blockToText(block),
    target_id: block.id,
  }))
}
