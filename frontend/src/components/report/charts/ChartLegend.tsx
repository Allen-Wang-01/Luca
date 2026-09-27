import { seriesColorVar } from './colors'
import './charts.css'

interface ChartLegendProps {
  names: string[]
  // Explicit per-entry color, for callers (e.g. PieChart's folded "Other" slice) whose
  // fill doesn't follow the plain categorical index. Falls back to the categorical
  // slot order otherwise.
  colors?: string[]
}

// "A legend is always present for two or more series ... A single series needs no
// legend box: the chart's title already says what's plotted." (marks-and-anatomy.md)
export function ChartLegend({ names, colors }: ChartLegendProps) {
  if (names.length < 2) return null
  return (
    <ul className="chart-legend">
      {names.map((name, index) => (
        <li key={name} className="chart-legend__item">
          <span className="chart-legend__swatch" style={{ background: colors?.[index] ?? seriesColorVar(index) }} aria-hidden="true" />
          {name}
        </li>
      ))}
    </ul>
  )
}
