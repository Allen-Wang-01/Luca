import type { CSSProperties } from 'react'
import type { Visual, VisualItem, VisualUnit } from '../../../narration/types'
import { seriesColorVar } from './colors'
import { roundedTopRectPath } from './scale'
import './visual-chart.css'

interface VisualChartProps {
  chart: Visual
  // Key of the item being narrated: it stays in full color while the others fade.
  emphasis: string | null
}

const UNIT_SUFFIX: Record<NonNullable<VisualUnit>, string> = {
  billions: 'B',
  millions: 'M',
  thousands: 'K',
  percent: '%',
}

// Compact enough to sit on top of a bar: three significant figures or so, with the
// chart's scale as a suffix (81.6B, 0.24B, 1,250M).
function formatValue(value: number, unit: VisualUnit, signed = false): string {
  const magnitude = Math.abs(value)
  const digits = magnitude < 10 ? 2 : magnitude < 1000 ? 1 : 0
  const text = magnitude.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: digits })
  const sign = value < 0 ? '−' : signed ? '+' : ''
  return `${sign}${text}${unit ? UNIT_SUFFIX[unit] : ''}`
}

const LABEL_FONT_PX = 13
const LABEL_LINE_PX = 15
const MAX_LABEL_LINES = 3

// SVG text doesn't wrap, so axis labels are broken into lines by hand, on spaces, to
// roughly fit the width of their column.
function wrapLabel(label: string, widthPx: number): string[] {
  const maxChars = Math.max(6, Math.floor(widthPx / (LABEL_FONT_PX * 0.56)))
  const lines: string[] = []
  for (const word of label.split(/\s+/)) {
    const last = lines[lines.length - 1]
    if (last !== undefined && `${last} ${word}`.length <= maxChars) lines[lines.length - 1] = `${last} ${word}`
    else lines.push(word)
  }
  if (lines.length <= MAX_LABEL_LINES) return lines
  return [...lines.slice(0, MAX_LABEL_LINES - 1), `${lines[MAX_LABEL_LINES - 1]}…`]
}

function dimmed(item: VisualItem, emphasis: string | null): boolean {
  return emphasis !== null && item.key !== emphasis
}

// Marks appear one after another, in reading order, as the card pops in.
function order(index: number): CSSProperties {
  return { '--visual-order': index } as CSSProperties
}

const COLUMN_WIDTH = 104
const MIN_PLOT_WIDTH = 440
const PLOT_HEIGHT = 170
const TOP = 30 // room for the value label above the tallest bar
const SIDE = 8
const LABELS_HEIGHT = 10 + MAX_LABEL_LINES * LABEL_LINE_PX
const MAX_BAR_WIDTH = 44
const VALUE_GAP = 7

interface Column {
  item: VisualItem
  // The bar spans these two values on the chart's scale.
  from: number
  to: number
  tone: 'neutral' | 'up' | 'down'
  text: string
}

// A waterfall is a bar chart whose middle bars float: each step starts where the
// running total stood and ends where it leaves it.
function buildColumns(chart: Visual): Column[] {
  if (chart.type !== 'waterfall') {
    return chart.items.map((item) => ({
      item,
      from: 0,
      to: item.value,
      tone: 'neutral',
      text: formatValue(item.value, chart.unit),
    }))
  }

  let running = 0
  return chart.items.map((item) => {
    if (item.role !== 'item') {
      running = item.value
      return { item, from: 0, to: item.value, tone: 'neutral', text: formatValue(item.value, chart.unit) }
    }
    const from = running
    running += item.value
    return {
      item,
      from,
      to: running,
      tone: item.value < 0 ? 'down' : 'up',
      text: formatValue(item.value, chart.unit, true),
    }
  })
}

function ColumnChart({ chart, emphasis }: VisualChartProps) {
  const columns = buildColumns(chart)
  const width = Math.max(MIN_PLOT_WIDTH, columns.length * COLUMN_WIDTH) + SIDE * 2
  const slot = (width - SIDE * 2) / columns.length
  const barWidth = Math.min(MAX_BAR_WIDTH, slot * 0.5)

  const levels = columns.flatMap((column) => [column.from, column.to])
  const top = Math.max(0, ...levels)
  const bottom = Math.min(0, ...levels)
  const span = top - bottom || 1
  // Negative bars carry their value label underneath, so they need the same headroom.
  const plotBottom = TOP + PLOT_HEIGHT - (bottom < 0 ? TOP - VALUE_GAP : 0)
  const y = (value: number) => TOP + ((top - value) / span) * (plotBottom - TOP)
  const height = TOP + PLOT_HEIGHT + LABELS_HEIGHT

  return (
    <svg className="visual-chart__svg" viewBox={`0 0 ${width} ${height}`} style={{ width: `${width / 16}rem` }} role="img">
      <line className="visual-chart__baseline" x1={SIDE} x2={width - SIDE} y1={y(0)} y2={y(0)} />
      {columns.map((column, i) => {
        const centerX = SIDE + slot * i + slot / 2
        const x = centerX - barWidth / 2
        const upper = y(Math.max(column.from, column.to))
        const lower = y(Math.min(column.from, column.to))
        const rising = column.to >= column.from
        const next = columns[i + 1]
        return (
          <g key={column.item.key} className="visual-chart__mark" data-dimmed={dimmed(column.item, emphasis)} style={order(i)}>
            {/* Carries this column's closing level over to where the next one starts. */}
            {chart.type === 'waterfall' && next && (
              <line
                className="visual-chart__connector"
                x1={x + barWidth}
                x2={centerX + slot - barWidth / 2}
                y1={y(column.to)}
                y2={y(column.to)}
              />
            )}
            {rising ? (
              <path
                className="visual-chart__bar"
                data-tone={column.tone}
                data-grows="up"
                d={roundedTopRectPath(x, upper, barWidth, Math.max(lower - upper, 1), 4)}
              />
            ) : (
              <rect
                className="visual-chart__bar"
                data-tone={column.tone}
                data-grows="down"
                x={x}
                y={upper}
                width={barWidth}
                height={Math.max(lower - upper, 1)}
              />
            )}
            <text
              className="visual-chart__value"
              x={centerX}
              y={rising ? upper - VALUE_GAP : lower + VALUE_GAP + 11}
              textAnchor="middle"
            >
              {column.text}
            </text>
            <text className="visual-chart__label" x={centerX} y={TOP + PLOT_HEIGHT + 8} textAnchor="middle">
              {wrapLabel(column.item.label, slot - 8).map((line, lineIndex) => (
                <tspan key={lineIndex} x={centerX} dy={LABEL_LINE_PX}>
                  {line}
                </tspan>
              ))}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function formatShare(part: number, total: number): string {
  const percent = (part / total) * 100
  return `${percent.toLocaleString('en-US', { maximumFractionDigits: percent < 10 ? 1 : 0 })}%`
}

function ShareChart({ chart, emphasis }: VisualChartProps) {
  const total = chart.items.find((item) => item.role === 'total')
  const parts = chart.items.filter((item) => item.role === 'item')
  if (!total || total.value <= 0) return null

  const rest = Math.max(0, total.value - parts.reduce((sum, part) => sum + part.value, 0))
  // Rounding in the printed figures can leave a sliver that isn't a real remainder.
  const showRest = rest / total.value >= 0.005

  return (
    <div className="visual-chart__share">
      <div className="visual-chart__share-bar">
        {parts.map((part, i) => (
          <div
            key={part.key}
            className="visual-chart__segment"
            data-dimmed={dimmed(part, emphasis)}
            style={{ ...order(i), flexGrow: part.value, background: seriesColorVar(i) }}
          />
        ))}
        {showRest && (
          <div
            className="visual-chart__segment visual-chart__segment--rest"
            data-dimmed={emphasis !== null && emphasis !== total.key}
            style={{ ...order(parts.length), flexGrow: rest }}
          />
        )}
      </div>
      <ul className="visual-chart__parts">
        {parts.map((part, i) => (
          <li key={part.key} className="visual-chart__part" data-dimmed={dimmed(part, emphasis)}>
            <span className="visual-chart__swatch" style={{ background: seriesColorVar(i) }} />
            <span className="visual-chart__part-label">{part.label}</span>
            <span className="visual-chart__part-share">{formatShare(part.value, total.value)}</span>
            <span className="visual-chart__part-value">{formatValue(part.value, chart.unit)}</span>
          </li>
        ))}
      </ul>
      <div className="visual-chart__total">
        of {total.label} · {formatValue(total.value, chart.unit)}
      </div>
    </div>
  )
}

// The chart a narration line brings up next to what it's highlighting. Unlike the
// charts in the report body, these are read at a glance while someone is talking: no
// axis to decode, every mark labelled with its value, and one mark picked out at a time.
export function VisualChart({ chart, emphasis }: VisualChartProps) {
  // An emphasis that names nothing in this chart would fade every mark.
  const known = emphasis !== null && chart.items.some((item) => item.key === emphasis) ? emphasis : null
  return chart.type === 'share' ? (
    <ShareChart chart={chart} emphasis={known} />
  ) : (
    <ColumnChart chart={chart} emphasis={known} />
  )
}
