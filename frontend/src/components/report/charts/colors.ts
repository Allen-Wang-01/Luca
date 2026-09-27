// Categorical series colors: the dataviz skill's validated default 8-hue palette
// (references/palette.md), fixed order - never cycled or reassigned by rank. Defined
// as CSS custom properties on `.chart-block` (see ChartBlockView.css) so light/dark
// swap in one place; re-validated with the skill's validate_palette.js against this
// app's actual surfaces (#ffffff light / #131b2e dark) - both pass every hard check
// (light has a contrast WARN on 3 of the 8 slots, mitigated by always shipping a
// legend + sparse direct labels, per the skill's relief rule).
const SERIES_SLOT_COUNT = 8

export function seriesColorVar(index: number): string {
  const slot = (index % SERIES_SLOT_COUNT) + 1
  return `var(--series-${slot})`
}

// A pie/donut's slices all sit adjacent to their circle neighbors (same structure as
// a stacked bar wrapped into a ring), so it follows the "adjacent" categorical ladder,
// not the stricter all-pairs cap used by scatter/bubble/small-multiples. Past the
// 8-slot ceiling, fold the remainder into one "Other" slice rather than generate a 9th
// hue (a generated hue is indistinguishable from an existing one under CVD).
export const MAX_DIRECT_CATEGORICAL_SLICES = SERIES_SLOT_COUNT
