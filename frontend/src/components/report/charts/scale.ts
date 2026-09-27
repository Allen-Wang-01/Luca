// Shared layout for every chart form, so bar/line/pie sit at a consistent size and
// aspect ratio inside a ChartBlockView card.
export const CHART_WIDTH = 640
export const CHART_HEIGHT = 320
export const CHART_MARGIN = { top: 16, right: 16, bottom: 32, left: 56 }

// Rounds up to a "clean" axis max (1/2/5 x 10^n) so gridline ticks read as round
// numbers (0 / 1,000 / 2,000, ...) per the dataviz skill's labeling rules.
export function niceMax(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return step * magnitude
}

export function tickValues(max: number, count = 4): number[] {
  const step = max / count
  return Array.from({ length: count + 1 }, (_, i) => Math.round(step * i))
}

export function formatTick(value: number): string {
  return value.toLocaleString('en-US')
}

// SVG <rect> has no per-corner radius, so a bar/column's "4px rounded data-end, square
// at the baseline" needs a hand-built path: rounded top-left/top-right, square bottom.
export function roundedTopRectPath(x: number, y: number, width: number, height: number, radius: number): string {
  const r = Math.min(radius, width / 2, Math.max(height, 0))
  if (height <= 0) return ''
  if (r <= 0) {
    return `M${x},${y} H${x + width} V${y + height} H${x} Z`
  }
  return [
    `M${x},${y + r}`,
    `A${r},${r} 0 0 1 ${x + r},${y}`,
    `H${x + width - r}`,
    `A${r},${r} 0 0 1 ${x + width},${y + r}`,
    `V${y + height}`,
    `H${x}`,
    `Z`,
  ].join(' ')
}
