# Financial Report Schema

This is the canonical data contract for a parsed financial report. It is produced by
the PDF parsing step (Phase 1), rendered by the frontend (Phase 3), and referenced by
the narration script's `target_id` (Phase 2) for scroll/highlight sync.

Source of truth: `backend/app/models/report.py` (Pydantic). The frontend mirror lives at
`frontend/src/types/report.ts` and is kept in sync by hand — the schema is small enough
that codegen isn't worth the setup yet.

## Top-level shape

```
FinancialReport
├── meta        report-level metadata (company, period, currency, unit scale, ...)
├── sections    navigation tree; each section references block ids, for a table of contents
└── blocks      flat, ordered list of renderable content — the source of truth
```

`sections` is purely structural (for a nav/TOC panel); the actual content and ids live in
`blocks`. A block's `id` is what narration and UI sync target.

## Block types

Every block has `id` and a `type` discriminator (`paragraph` | `table` | `chart`).

- **ParagraphBlock** — a heading, body paragraph, note, or list item. `style`
  distinguishes them so the frontend can render each with its own component/typography.
- **TableBlock** — a financial statement table (income statement, balance sheet, etc.).
- **ChartBlock** — a trend or breakdown chart, expressed as structured series data (not
  an image) so the frontend renders it with its own charting component.

## Paragraph text is extracted verbatim, and lists are split per-item

`ParagraphBlock.text` must be the source document's exact original wording — not a
paraphrase, summary, or cleanup pass. This is a deliberate line between the phases:
Phase 1 (parsing) is a faithful transcription of what the document says, while Phase 2
(narration script generation) is the layer that's allowed to reinterpret it into
conversational, analytical narration. If Phase 1 already paraphrased the source, Phase 2
would be paraphrasing a paraphrase, with no faithful copy of the original left anywhere
in the pipeline — and for forward-looking/guidance language in particular, even
subtle rewording can shift meaning.

For the same reason, a bulleted or numbered list in the source is never merged into one
paragraph block — each item becomes its own `ParagraphBlock` with `style: "list_item"`,
verbatim, without the bullet marker itself. This preserves the source's structure and,
consistent with the row/cell id rationale below, gives narration a separate id to target
and highlight per list item instead of one all-or-nothing block for the whole list.

## Why rows and cells have their own ids

Narration rarely talks about "the table" — it talks about *revenue*, or *revenue vs. the
prior year*. If only the table had an id, the karaoke-style highlight could only ever
light up the whole table, which is a poor experience. So:

- `TableBlock.rows[].id` lets narration target a single row (e.g. "Revenue").
- `TableBlock.rows[].cells[].id` lets narration target a single value (e.g. "Revenue,
  Q2 FY2026" specifically, as opposed to the prior-year column).

The narration agent (`backend/app/services/narration_agent.py`) is told to pick the
most specific id for each line: a cell when the line cites one figure, a row for a
metric across periods, the block for an overview. Every row and cell id is written out
in the report text it reads, next to the value it names, so it copies ids rather than
assembling them from the rule below. Any `target_id` it gets wrong is
repaired by walking up this same hierarchy (cell → row → block) — which works because
row and cell ids are derived from their parent's id.

Chart data points have no ids, so narration about a chart always targets the whole
chart block.

## What a row measures, and where it sits

A statement mixes kinds of figures in one table: amounts in millions, per-share amounts
printed as they are, share counts in thousands. It also repeats labels - "Products"
under both sales and costs, "Basic" under both earnings per share and share counts.
Nothing in a row's label reliably says which is which, so the parser marks each row:

| Field | Meaning |
|---|---|
| `quantity` | `money`, `per_share`, `share_count`, `percent` or `other` |
| `scale` | the scale this row's figures are printed in (`actual`, `thousands`, ...), which need not be `meta.unit_scale` |
| `group` | the sub-heading the row is listed under, without its trailing colon |

All three are optional and `null` on a row without figures and on reports parsed before
they existed; code that reads them falls back to the report's unit scale and to a row
label containing "per share". They are used to put figures on one scale before
calculating with them, to refuse adding or comparing figures of different kinds (only
a ratio makes sense across kinds), and to name a row away from its table: where a label
is shared by several rows it is shown as `{group} · {label}`, and a column under a group
header as `{group label} · {column label}` (`backend/app/services/report_labels.py`,
mirrored in `frontend/src/narration/targetIndex.ts`).

## Totals name their parts

A row that is a total or a result of other rows lists them in `sum_of`:
`[{row_id, sign: "add" | "subtract"}]`. Figures are taken with the sign they are printed
with, so a cost printed as 400 is subtracted and an outflow printed as (120) is added.
This is what the arithmetic check runs on (see "Validation and confidence flags"), so
it doesn't depend on what a company calls its rows.

Rows have no ids while the LLM is filling in the report, so there it refers to rows by
position: every `LLMRow` carries an `index` the model writes out (0, 1, 2, ...), and
`sum_of` uses those. `id_assigner` converts them to row ids, and leaves out all of a
table's relationships if any written index doesn't match the row's real position - a
reference that is off by one would flag correct figures. A single relationship is left
out if it names a row that doesn't exist, the row itself, a row without figures, or the
same row twice.

## Charts the narration brings up

Separately from the report's own chart blocks, a narration line can carry a small chart
of its own (`NarrationLine.visual` in `backend/app/models/narration.py`, mirrored in
`frontend/src/narration/types.ts`), shown in a card next to the line's target:

```
LineVisual
├── chart      Visual: id, type (bar | share | waterfall), title, unit, items
└── emphasis   key of the one item this line is about, or null
```

Each `VisualItem` has a `key` (unique within its chart), a `label`, a `value` in the
chart's `unit`, a `role`, and where it came from (`source_id`, `raw_text`). `role` says
how the item is drawn: `item` for a bar, a part of a whole or a waterfall step (whose
value is signed), `total` for the whole a share bar's parts belong to, `start`/`end`
for a waterfall's opening and closing bars.

The same rule as for ids applies to these values: the model doesn't write them. It
calls a chart tool (`backend/app/services/narration_visuals.py`) with references - a
cell id, or a paragraph id plus the figure as written there - and the backend looks the
values up, puts them on one scale, and checks the chart against itself (a waterfall's
steps must lead from its start to its end; a share bar's parts can't exceed its total)
before giving it an id. Lines then refer to that id. Consecutive lines can share one
chart and move the `emphasis`, so the chart is embedded in every line that shows it
rather than stored once on the side.

A chart item can also be the result of a calculation (a margin the report doesn't
print, a growth rate per division). Such an item has `computed: true`, the calculation's
id as its `source_id`, and the card marks it so a viewer knows the figure isn't printed
in the report.

## Figures a narration line states

Every narration line lists where its figures come from, in `figures`:
`[{id, quote}]` - a cell id, a paragraph id plus the figure as written there, or the id
of a calculation from the same run (`calc_1`, ...). After the script is written, each
amount and percentage in a line's text is compared with what the line lists, a second
model reads each line against the labels of those figures, and the agent is asked to
correct what was found (`backend/app/services/narration_figures.py`,
`narration_reviewer.py`). What that found is returned in the trace as `review`: the
findings of each round, and any line that was cut because its figure was still wrong
after the corrections. A calculation id only means something next to the trace of the
run that produced it.

## Id generation rules (implemented in the Phase 1 parser, not by the LLM)

A multimodal model asked to invent globally-unique ids across a long document is
unreliable — it can produce duplicates or inconsistent formats. So the LLM only proposes
a human-readable slug per block (e.g. `income_statement`); the backend parser is
responsible for guaranteeing uniqueness and deriving the rest:

| Id | Rule |
|---|---|
| Block id | `{type_prefix}_{slug}`, e.g. `t_income_statement`, `p_3` (sequential when no slug), `c_revenue_trend`. Backend appends a numeric suffix on collision. |
| Row id | `{table_id}__r{row_index}` |
| Cell id | `{table_id}__r{row_index}_{col_id}` |

Concretely, this is two separate Pydantic schemas, not one:

- `backend/app/models/llm_report.py` — what the LLM's structured output actually
  produces. Same shape as `report.py`, but blocks and sections carry `slug` instead of
  `id`, and rows/cells carry no id field at all (rows carry an `index` instead, for
  `sum_of` - see "Totals name their parts").
- `backend/app/services/id_assigner.py` — `assign_ids(llm_report, source_filename) ->
  FinancialReport`, the pure function that applies the table above and produces the
  schema this document otherwise describes. It also fills in `meta.source_filename` and
  `meta.parsed_at`, which the LLM is never asked for.

## Validation and confidence flags

Two independent mechanisms flag suspect data, corresponding to Phase 1's "flag
suspected parsing errors" requirement:

- `confidence: "high" | "low"` — the LLM's own self-reported certainty about a table or
  chart it extracted (e.g. a smudged scan, an ambiguous figure).
- `flags: Flag[]` — populated by a **separate backend validation pass** over the parsed
  output (`backend/app/services/report_validator.py`). Kept separate from the LLM prompt
  so validation rules can be iterated on independently of parsing.

`Flag` has `severity` (`warning` | `error`), a `code`, and a human-readable `message`.

The validation pass checks every total against the rows its `sum_of` names, column by
column, allowing for the rounding of the printed figures and reading a dash as zero.
What a failure means depends on where it fails:

| Outcome | What it means | Flag |
|---|---|---|
| fails in some columns, holds in others | a figure in a failing column was misread | `arithmetic_mismatch` on the total's row |
| fails in every column (two or more) | the relationship itself is wrong, not the figures | none; logged only |
| fails in a table with one column to check | can't tell which | `unconfirmed_sum` on the total's row |

A table in which no row has `sum_of` (a report parsed before it existed) is checked
with a few rules that find rows by label instead, which also produce
`arithmetic_mismatch`.

A table gets `ambiguous_columns` when two of its columns read the same once their group
header is counted in - see "Two-level column headers".

Only `arithmetic_mismatch` says a figure is suspect, so it is the only code the
narration is shown and tells the listener about
(`narration_context.NARRATED_FLAG_CODES`). The others are about how the report was
parsed and appear on the page only.

## Two-level column headers

Real filings often group columns under a shared header (e.g. "Three Months Ended" over
two date columns). `TableBlock.column_groups` is optional and only used when a table
actually has this structure; simple tables omit it.

When the source prints such a header once for several tables - a statement followed by
breakdowns under the same column headings, or a table continued on the next page - the
parser repeats the full header, groups included, on each table. Without the groups, two
columns with the same date can't be told apart, by a reader or by the narration model
picking a figure; the validation pass flags a table where that happened
(`ambiguous_columns`).

## Example

A minimal report with one heading and a one-row income statement table:

```json
{
  "meta": {
    "company_name": "NVIDIA Corporation",
    "ticker": "NVDA",
    "report_type": "10-Q",
    "fiscal_period": "FY2026 Q2",
    "currency": "USD",
    "unit_scale": "millions",
    "source_filename": "nvda_10q_fy26q2.pdf",
    "parsed_at": "2026-09-19T00:00:00Z"
  },
  "sections": [
    {
      "id": "sec_income_statement",
      "title": "Income Statement",
      "block_ids": ["p_1", "t_income_statement"]
    }
  ],
  "blocks": [
    {
      "id": "p_1",
      "type": "paragraph",
      "style": "heading",
      "text": "Income Statement Overview",
      "page": 4
    },
    {
      "id": "t_income_statement",
      "type": "table",
      "title": "Consolidated Statement of Income",
      "unit": "USD millions",
      "column_groups": [],
      "columns": [
        { "id": "col0", "label": "Metric" },
        { "id": "col1", "label": "Q2 FY2026" },
        { "id": "col2", "label": "Q2 FY2025" }
      ],
      "rows": [
        {
          "id": "t_income_statement__r0",
          "label": "Revenue",
          "cells": [
            {
              "id": "t_income_statement__r0_col1",
              "col_id": "col1",
              "value": 46740,
              "raw_text": "46,740",
              "value_type": "number"
            },
            {
              "id": "t_income_statement__r0_col2",
              "col_id": "col2",
              "value": 30040,
              "raw_text": "30,040",
              "value_type": "number"
            }
          ],
          "flags": [],
          "quantity": "money",
          "scale": "millions",
          "group": null,
          "sum_of": []
        }
      ],
      "confidence": "high",
      "flags": [],
      "page": 4
    }
  ]
}
```
