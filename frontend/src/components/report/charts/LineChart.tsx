import type { ChartSeries } from '../../../types/report'
import { seriesColorVar } from './colors'
import { CHART_HEIGHT, CHART_WIDTH, formatTick, niceMax, tickValues } from './scale'
import { ChartLegend } from './ChartLegend'
import './charts.css'

interface LineChartProps {
  series: ChartSeries[]
}

const WIDTH = CHART_WIDTH
const HEIGHT = CHART_HEIGHT
// Wider right margin than the shared default: leaves room for the end-of-line value
// label the mark spec calls for ("Lines -> value at the end").
const MARGIN = { top: 16, right: 64, bottom: 32, left: 56 }
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom
// Past this many series, converging end-labels would collide - fall back to legend +
// tooltip only rather than stack labels (marks-and-anatomy.md's collision rule).
const MAX_END_LABEL_SERIES = 3

export function LineChart({ series }: LineChartProps) {
  if (series.length === 0 || series[0].data.length === 0) return null

  const labels = series[0].data.map((point) => point.label)
  const groupCount = labels.length

  const maxValue = niceMax(Math.max(...series.flatMap((s) => s.data.map((d) => d.value)), 1))
  const valueToY = (value: number) => MARGIN.top + PLOT_HEIGHT - (value / maxValue) * PLOT_HEIGHT
  const indexToX = (index: number) =>
    groupCount === 1 ? MARGIN.left + PLOT_WIDTH / 2 : MARGIN.left + (index / (groupCount - 1)) * PLOT_WIDTH

  const ticks = tickValues(maxValue)
  const baselineY = MARGIN.top + PLOT_HEIGHT
  const showEndLabels = series.length <= MAX_END_LABEL_SERIES

  return (
    <>
      <svg className="chart-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" preserveAspectRatio="xMidYMid meet">
        {ticks.map((tick) => {
          const y = valueToY(tick)
          return (
            <g key={tick}>
              <line className="chart-gridline" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y} y2={y} />
              <text className="chart-axis-label" x={MARGIN.left - 8} y={y} textAnchor="end" dominantBaseline="middle">
                {formatTick(tick)}
              </text>
            </g>
          )
        })}

        {labels.map((label, index) => (
          <text key={label} className="chart-axis-label" x={indexToX(index)} y={baselineY + 16} textAnchor="middle">
            {label}
          </text>
        ))}

        {series.map((s, seriesIndex) => {
          const points = s.data.map((point, index) => ({ x: indexToX(index), y: valueToY(point.value), point }))
          const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
          const last = points[points.length - 1]
          return (
            <g key={s.name}>
              <path className="chart-line" d={pathD} stroke={seriesColorVar(seriesIndex)} />
              {points.map((p) => (
                <circle key={p.point.label} className="chart-marker" cx={p.x} cy={p.y} r={4} fill={seriesColorVar(seriesIndex)}>
                  <title>{`${s.name} · ${p.point.label}: ${p.point.value.toLocaleString('en-US')}`}</title>
                </circle>
              ))}
              {showEndLabels && last && (
                <text className="chart-value-label" x={last.x + 8} y={last.y} dominantBaseline="middle">
                  {last.point.value.toLocaleString('en-US')}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      <ChartLegend names={series.map((s) => s.name)} />
    </>
  )
}
