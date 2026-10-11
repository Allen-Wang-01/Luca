import type { Mention } from '../../narration/mentions'
import { sourceLabel } from '../../narration/sourceLabel'
import type { NarrationScript } from '../../narration/types'
import type { FinancialReport } from '../../types/report'
import { MentionTile } from './FigureRail'
import { COMPUTED_MARK, VisualChart } from './charts/VisualChart'
import './ClosingScreen.css'

interface ClosingScreenProps {
  report: FinancialReport
  script: NarrationScript
  mentions: Mention[]
  onReplay: () => void
  // Goes back into the walkthrough at the line that brought something up.
  onSeek: (index: number) => void
  onRead: () => void
  onExit: () => void
}

// Every page a line drew on, once each, in the order they came up.
function citedSources(script: NarrationScript): string[] {
  const urls: string[] = []
  for (const line of script) {
    for (const url of line.sources ?? []) {
      if (!urls.includes(url)) urls.push(url)
    }
  }
  return urls
}

// Shown when the last line has played: everything the walkthrough pointed at, laid out
// on one page, with the pages it drew on from outside the report.
export function ClosingScreen({ report, script, mentions, onReplay, onSeek, onRead, onExit }: ClosingScreenProps) {
  const figures = mentions.filter((mention) => mention.kind === 'figure')
  const charts = mentions.filter((mention) => mention.kind === 'chart')
  const sources = citedSources(script)

  return (
    <div className="closing-screen">
      <header className="closing-screen__header">
        <p className="closing-screen__eyebrow">End of the walkthrough</p>
        <h1 className="closing-screen__title">{report.meta.company_name}</h1>
        <p className="closing-screen__period">{report.meta.fiscal_period}</p>
        <div className="closing-screen__actions">
          <button type="button" className="closing-screen__primary" onClick={onReplay}>
            Watch again
          </button>
          <button type="button" className="closing-screen__secondary" onClick={onRead}>
            Read the report
          </button>
          <button type="button" className="closing-screen__secondary" onClick={onExit}>
            Back to start
          </button>
        </div>
      </header>

      {figures.length > 0 && (
        <section className="closing-screen__section">
          <h2 className="closing-screen__heading">The figures that came up</h2>
          <div className="closing-screen__figures">
            {figures.map((mention) => (
              <MentionTile key={mention.key} mention={mention} onSelect={() => onSeek(mention.lineIndex)} />
            ))}
          </div>
        </section>
      )}

      {charts.length > 0 && (
        <section className="closing-screen__section">
          <h2 className="closing-screen__heading">The charts</h2>
          <div className="closing-screen__charts">
            {charts.map(
              (mention) =>
                mention.kind === 'chart' && (
                  <button
                    key={mention.key}
                    type="button"
                    className="closing-screen__chart"
                    onClick={() => onSeek(mention.lineIndex)}
                  >
                    <span className="closing-screen__chart-title">{mention.chart.title}</span>
                    <VisualChart chart={mention.chart} emphasis={null} />
                    {mention.chart.items.some((item) => item.computed) && (
                      <span className="closing-screen__note">{COMPUTED_MARK} Calculated from the report's figures</span>
                    )}
                  </button>
                ),
            )}
          </div>
        </section>
      )}

      {sources.length > 0 && (
        <section className="closing-screen__section">
          <h2 className="closing-screen__heading">Outside sources</h2>
          <ul className="closing-screen__sources">
            {sources.map((url) => (
              <li key={url}>
                <a href={url} target="_blank" rel="noopener noreferrer" title={url}>
                  {sourceLabel(url)}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="closing-screen__disclaimer">
        An automated reading of the company's own report, for understanding it - not investment advice.
      </p>
    </div>
  )
}
