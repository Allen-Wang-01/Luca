import type { Block, ParagraphBlock } from '../../types/report'
import { ParagraphBlockView } from './ParagraphBlockView'
import { TableBlockView } from './TableBlockView'
import { ChartBlockView } from './ChartBlockView'

interface BlockListProps {
  blocks: Block[]
}

type Group = { kind: 'single'; block: Block } | { kind: 'list'; blocks: ParagraphBlock[] }

function isListItem(block: Block): block is ParagraphBlock {
  return block.type === 'paragraph' && block.style === 'list_item'
}

// A bulleted/numbered list in the source is never merged into one paragraph block -
// each item is its own ParagraphBlock (see docs/schema.md) - but consecutive items
// should still read as one visual list rather than disconnected paragraphs.
function groupListItems(blocks: Block[]): Group[] {
  const groups: Group[] = []
  for (const block of blocks) {
    const last = groups[groups.length - 1]
    if (isListItem(block)) {
      if (last?.kind === 'list') {
        last.blocks.push(block)
      } else {
        groups.push({ kind: 'list', blocks: [block] })
      }
    } else {
      groups.push({ kind: 'single', block })
    }
  }
  return groups
}

export function BlockList({ blocks }: BlockListProps) {
  const groups = groupListItems(blocks)

  return (
    <>
      {groups.map((group) => {
        if (group.kind === 'list') {
          return (
            <ul key={group.blocks[0].id} className="paragraph-list">
              {group.blocks.map((block) => (
                <ParagraphBlockView key={block.id} block={block} />
              ))}
            </ul>
          )
        }

        const { block } = group
        switch (block.type) {
          case 'paragraph':
            return <ParagraphBlockView key={block.id} block={block} />
          case 'table':
            return <TableBlockView key={block.id} block={block} />
          case 'chart':
            return <ChartBlockView key={block.id} block={block} />
          default:
            return null
        }
      })}
    </>
  )
}
