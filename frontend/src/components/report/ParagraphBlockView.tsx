import type { ParagraphBlock } from '../../types/report'
import { useSyncTarget } from './NarrationSyncContext'
import './ParagraphBlockView.css'

interface ParagraphBlockViewProps {
  block: ParagraphBlock
}

// Grouping consecutive list_item blocks into one <ul> is BlockList's job; this
// component only knows how to render a single block, as a list_item does as an <li>.
export function ParagraphBlockView({ block }: ParagraphBlockViewProps) {
  const { ref, state } = useSyncTarget(block.id)

  if (block.style === 'list_item') {
    return (
      <li ref={ref} data-sync={state} className="sync paragraph-block paragraph-block--list-item">
        {block.text}
      </li>
    )
  }

  if (block.style === 'heading') {
    return (
      <h2 ref={ref} data-sync={state} className="sync paragraph-block paragraph-block--heading">
        {block.text}
      </h2>
    )
  }

  if (block.style === 'note') {
    return (
      <p ref={ref} data-sync={state} className="sync paragraph-block paragraph-block--note">
        {block.text}
      </p>
    )
  }

  return (
    <p ref={ref} data-sync={state} className="sync paragraph-block paragraph-block--body">
      {block.text}
    </p>
  )
}
