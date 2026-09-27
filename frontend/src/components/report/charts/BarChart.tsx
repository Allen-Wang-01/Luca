import type { ChartSeries } from '../../../types/report'
import { seriesColorVar } from './colors'
import { CHART_HEIGHT, CHART_MARGIN, CHART_WIDTH, formatTick, niceMax, roundedTopRectPath, tickValues } from './scale'
import { ChartLegend } from './ChartLegend'
import './charts.css'

interface BarChartProps {
  series: ChartSeries[]
  stacked?: boolean
}

const WIDTH = CHART_WIDTH
const HEIGHT = CHART_HEIGHT
const MARGIN = CHART_MARGIN
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom
const MAX_BAR_WIDTH = 24 // mark spec: bars are capped thin, never fill the slot
const BAR_GAP = 2 // surface gap between touching bars/segments

export function BarChart({ series, stacked = false }: BarChartProps) {
  if (series.length === 0 || series[0].data.length === 0) return null

  const labels = series[0].data.map((point) => point.label)
  const groupCount = labels.length
  const seriesCount = series.length

  const rawMax = stacked
    ? Math.max(...labels.map((_, i) => series.reduce((sum, s) => sum + (s.data[i]?.value ?? 0), 0)))
    : Math.max(...series.flatMap((s) => s.data.map((d) => d.value)))
  const maxValue = niceMax(Math.max(rawMax, 1))
  const valueToY = (value: number) => MARGIN.top + PLOT_HEIGHT - (value / maxValue) * PLOT_HEIGHT

  const groupWidth = PLOT_WIDTH / groupCount
  const barAreaWidth = stacked
    ? Math.min(groupWidth * 0.6, MAX_BAR_WIDTH)
    : Math.min(groupWidth * 0.7, seriesCount * MAX_BAR_WIDTH + (seriesCount - 1) * BAR_GAP)
  const singleBarWidth = stacked
    ? barAreaWidth
    : Math.min(MAX_BAR_WIDTH, (barAreaWidth - (seriesCount - 1) * BAR_GAP) / seriesCount)

  const ticks = tickValues(maxValue)
  const baselineY = MARGIN.top + PLOT_HEIGHT

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

        {labels.map((label, groupIndex) => {
          const groupX = MARGIN.left + groupIndex * groupWidth
          const barsStartX = groupX + (groupWidth - barAreaWidth) / 2
          const xAxisLabel = (
            <text className="chart-axis-label" x={groupX + groupWidth / 2} y={baselineY + 16} textAnchor="middle">
              {label}
            </text>
          )

          if (stacked) {
            let cumulative = 0
            const segments = series.map((s, seriesIndex) => {
              const value = s.data[groupIndex]?.value ?? 0
              const segmentBottom = cumulative
              cumulative += value
              const y = valueToY(cumulative)
              const height = Math.max(0, valueToY(segmentBottom) - y - (seriesIndex > 0 ? BAR_GAP : 0))
              const isTopSegment = seriesIndex === series.length - 1
              return (
                <path
                  key={s.name}
                  className="chart-bar"
                  d={roundedTopRectPath(barsStartX, y, singleBarWidth, height, isTopSegment ? 4 : 0)}
                  fill={seriesColorVar(seriesIndex)}
                >
                  <title>{`${s.name} · ${label}: ${value.toLocaleString('en-US')}`}</title>
                </path>
              )
            })
            return (
              <g key={label}>
                {segments}
                <text className="chart-value-label" x={barsStartX + singleBarWidth / 2} y={valueToY(cumulative) - 6} textAnchor="middle">
                  {cumulative.toLocaleString('en-US')}
                </text>
                {xAxisLabel}
              </g>
            )
          }

          return (
            <g key={label}>
              {series.map((s, seriesIndex) => {
                const value = s.data[groupIndex]?.value ?? 0
                const y = valueToY(value)
                const height = baselineY - y
                const x = barsStartX + seriesIndex * (singleBarWidth + BAR_GAP)
                return (
                  <g key={s.name}>
                    <path className="chart-bar" d={roundedTopRectPath(x, y, singleBarWidth, height, 4)} fill={seriesColorVar(seriesIndex)}>
                      <title>{`${s.name} · ${label}: ${value.toLocaleString('en-US')}`}</title>
                    </path>
                    {seriesCount === 1 && (
                      <text className="chart-value-label" x={x + singleBarWidth / 2} y={y - 6} textAnchor="middle">
                        {value.toLocaleString('en-US')}
                      </text>
                    )}
                  </g>
                )
              })}
              {xAxisLabel}
            </g>
          )
        })}
      </svg>
      <ChartLegend names={series.map((s) => s.name)} />
    </>
  )
}
