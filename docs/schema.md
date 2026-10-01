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
metric across periods, the block for an overview. It sees row ids directly and is given
the cell id rule below rather than every cell id. Any `target_id` it gets wrong is
repaired by walking up this same hierarchy (cell → row → block) — which works because
row and cell ids are derived from their parent's id.

Chart data points have no ids, so narration about a chart always targets the whole
chart block.

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
  `id`, and rows/cells carry no id field at all.
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
  output (e.g. checking `revenue - cost = gross_profit` within tolerance). Kept separate
  from the LLM prompt so validation rules can be iterated on independently of parsing.

`Flag` has `severity` (`warning` | `error`), a `code` (e.g. `arithmetic_mismatch`), and a
human-readable `message`.

## Two-level column headers

Real filings often group columns under a shared header (e.g. "Three Months Ended" over
two date columns). `TableBlock.column_groups` is optional and only used when a table
actually has this structure; simple tables omit it.

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
          "flags": []
        }
      ],
      "confidence": "high",
      "flags": [],
      "page": 4
    }
  ]
}
```
