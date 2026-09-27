import type { ChartSeries } from '../../../types/report'
import { MAX_DIRECT_CATEGORICAL_SLICES, seriesColorVar } from './colors'
import { CHART_HEIGHT, CHART_WIDTH } from './scale'
import { ChartLegend } from './ChartLegend'
import './charts.css'

interface PieChartProps {
  series: ChartSeries[]
}

const WIDTH = CHART_WIDTH
const HEIGHT = CHART_HEIGHT
const CENTER_X = 180
const CENTER_Y = HEIGHT / 2
const RADIUS = 110
// Below this share, an outside percentage label would collide with its neighbors -
// the legend + hover tooltip carry it instead.
const MIN_LABEL_SHARE = 0.06

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
}

function arcPath(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, r, startAngle)
  const end = polarToCartesian(cx, cy, r, endAngle)
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0
  return `M${cx},${cy} L${start.x},${start.y} A${r},${r} 0 ${largeArc} 1 ${end.x},${end.y} Z`
}

export function PieChart({ series }: PieChartProps) {
  const data = series[0]?.data ?? []
  if (data.length === 0) return null

  // Sorted largest-first for a readable sweep; a fresh static render each time, not an
  // interactive filter, so assigning color by this render's order doesn't violate
  // "color follows the entity, never its rank."
  const sorted = [...data].sort((a, b) => b.value - a.value)
  const overflow = sorted.length > MAX_DIRECT_CATEGORICAL_SLICES
  const visible = overflow ? sorted.slice(0, MAX_DIRECT_CATEGORICAL_SLICES - 1) : sorted
  const folded = sorted.slice(visible.length)
  const otherTotal = folded.reduce((sum, point) => sum + point.value, 0)
  const slices = folded.length > 0 ? [...visible, { label: 'Other', value: otherTotal }] : visible
  const otherIndex = folded.length > 0 ? slices.length - 1 : -1

  const total = slices.reduce((sum, point) => sum + point.value, 0) || 1
  const sliceColor = (index: number) => (index === otherIndex ? 'var(--color-border)' : seriesColorVar(index))

  let angle = -Math.PI / 2
  const arcs = slices.map((slice, index) => {
    const share = slice.value / total
    const startAngle = angle
    const endAngle = angle + share * Math.PI * 2
    angle = endAngle
    return { slice, startAngle, endAngle, midAngle: (startAngle + endAngle) / 2, share, index }
  })

  return (
    <>
      <svg className="chart-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" preserveAspectRatio="xMidYMid meet">
        {arcs.map(({ slice, startAngle, endAngle, midAngle, share, index }) => {
          const labelPos = polarToCartesian(CENTER_X, CENTER_Y, RADIUS + 18, midAngle)
          const leaderStart = polarToCartesian(CENTER_X, CENTER_Y, RADIUS + 2, midAngle)
          const anchor = Math.cos(midAngle) >= 0 ? 'start' : 'end'
          return (
            <g key={slice.label}>
              <path
                className="chart-pie-slice"
                d={arcPath(CENTER_X, CENTER_Y, RADIUS, startAngle, endAngle)}
                fill={sliceColor(index)}
                stroke="var(--color-surface)"
                strokeWidth={2}
              >
                <title>{`${slice.label}: ${slice.value.toLocaleString('en-US')} (${(share * 100).toFixed(1)}%)`}</title>
              </path>
              {share >= MIN_LABEL_SHARE && (
                <g>
                  <line className="chart-gridline" x1={leaderStart.x} y1={leaderStart.y} x2={labelPos.x} y2={labelPos.y} />
                  <text className="chart-value-label" x={labelPos.x} y={labelPos.y} textAnchor={anchor} dominantBaseline="middle">
                    {(share * 100).toFixed(0)}%
                  </text>
                </g>
              )}
            </g>
          )
        })}
      </svg>
      <ChartLegend names={slices.map((s) => s.label)} colors={slices.map((_, index) => sliceColor(index))} />
    </>
  )
}
