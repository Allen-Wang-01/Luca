// Mirrors backend/app/models/report.py. Keep the two in sync by hand;
// if the schema starts drifting, consider generating this file instead.

export type UnitScale = 'actual' | 'thousands' | 'millions' | 'billions'

export interface ReportMeta {
  company_name: string
  ticker: string | null
  report_type: string
  fiscal_period: string
  currency: string
  unit_scale: UnitScale
  source_filename: string
  parsed_at: string
}

export interface Flag {
  severity: 'warning' | 'error'
  code: string
  message: string
}

export interface ParagraphBlock {
  id: string
  type: 'paragraph'
  style: 'heading' | 'body' | 'note' | 'list_item'
  text: string
  page: number | null
}

export interface ColumnGroup {
  label: string
  col_ids: string[]
}

export interface Column {
  id: string
  label: string
}

export type CellValueType = 'number' | 'percent' | 'currency' | 'text'

export interface Cell {
  id: string
  col_id: string
  value: number | null
  raw_text: string
  value_type: CellValueType
}

// What a row's figures measure.
export type Quantity = 'money' | 'per_share' | 'share_count' | 'percent' | 'other'

export interface Row {
  id: string
  label: string
  cells: Cell[]
  flags: Flag[]
  // The three below are null on reports parsed before the parser filled them in.
  quantity: Quantity | null
  // The scale this row's figures are printed in, which need not be the report's.
  scale: UnitScale | null
  // The sub-heading the row sits under, for telling apart rows that share a label.
  group: string | null
  // For a total or subtotal: the rows of the same table that add up to it. The backend
  // checks the arithmetic and flags the row if it doesn't hold. Empty for other rows.
  sum_of: SumTerm[]
}

export interface SumTerm {
  row_id: string
  sign: 'add' | 'subtract'
}

export interface TableBlock {
  id: string
  type: 'table'
  title: string
  unit: string | null
  column_groups: ColumnGroup[]
  columns: Column[]
  rows: Row[]
  confidence: 'high' | 'low' | null
  flags: Flag[]
  page: number | null
}

export interface ChartDataPoint {
  label: string
  value: number
}

export interface ChartSeries {
  name: string
  data: ChartDataPoint[]
}

export type ChartType = 'bar' | 'line' | 'pie' | 'stacked_bar'

export interface ChartBlock {
  id: string
  type: 'chart'
  title: string
  chart_type: ChartType
  unit: string | null
  series: ChartSeries[]
  confidence: 'high' | 'low' | null
  note: string | null
  page: number | null
}

export type Block = ParagraphBlock | TableBlock | ChartBlock

export interface Section {
  id: string
  title: string
  block_ids: string[]
}

export interface FinancialReport {
  meta: ReportMeta
  sections: Section[]
  blocks: Block[]
}
