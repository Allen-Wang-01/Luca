# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (`backend/`, Python + FastAPI)

Dependencies must stay isolated in the virtualenv — never install into a global/system Python.

```bash
cd backend
python3 -m venv .venv              # first time only; use python3.11+ (system python3 on this
                                    # machine may be an old 3.7 — check `python3 --version`)
source .venv/bin/activate          # every session, before running pip/uvicorn/python
pip install -r requirements.txt
cp .env.example .env               # fill in OPENAI_API_KEY (and OPENAI_BASE_URL if needed)
uvicorn app.main:app --reload      # serves http://localhost:8000, health at /api/health
```

Tests (`pip install -r requirements-dev.txt` first — adds pytest/httpx/reportlab on top
of `requirements.txt`, kept separate since those have no business in production):

```bash
pytest -q                                    # full suite, no network calls, no API cost
pytest tests/test_id_assigner.py -q          # single file
pytest tests/test_id_assigner.py::test_colliding_slugs_get_unique_ids -q  # single test
python scripts/parse_sample.py path/to.pdf   # manual end-to-end run against the real API - costs money, not part of the suite
```

### Frontend (`frontend/`, React + TypeScript + Vite)

```bash
cd frontend
npm install
npm run dev        # dev server; proxies /api/* to http://localhost:8000 (see vite.config.ts)
npm run build       # tsc -b && vite build
npm run lint         # oxlint
npx tsc --noEmit    # type-check only, no build output
```

There is no test suite yet.

## Architecture

This is an AI tool that turns an uploaded financial report PDF into a spoken,
advisor-style walkthrough synced to on-screen content (auto-scroll, highlight, and a
karaoke-style zoom on whatever the narration is currently discussing), with a small
floating Live2D avatar for lip-sync.

Backend and frontend are two independent, separately-run services (no monorepo tooling,
no shared build step). The connection between them is:

1. **The report schema is the central contract.** It is defined once as Pydantic models
   in `backend/app/models/report.py`, mirrored by hand in
   `frontend/src/types/report.ts`, and explained in detail (including the id-generation
   rules and the rationale behind them) in `docs/schema.md`. Read `docs/schema.md`
   before changing either side of the schema — the two files must be kept in sync
   manually; there is no codegen step.
2. **In dev, the frontend proxies `/api/*` to the backend** (`frontend/vite.config.ts`),
   so there's no CORS handling — run both servers and hit relative `/api/...` URLs from
   the frontend rather than hardcoding `localhost:8000`.

### Why the schema is shaped the way it is

The schema models a report as `meta` (company/period/currency/unit metadata) +
`sections` (a purely structural nav tree referencing block ids) + `blocks` (the flat,
ordered, renderable content: `paragraph` | `table` | `chart`, a discriminated union on
`type`).

Narration needs to target individual data points, not whole tables (e.g. "revenue" or
even "revenue, this quarter's column" specifically) for the highlight/zoom effect to
feel precise. So `TableBlock` rows and cells carry their own ids, not just the table.
Ids are **not** trusted to the LLM to generate uniquely across a long document — the
Phase 1 parser derives them deterministically from a model-proposed slug (see the id
rules table in `docs/schema.md`): `{type_prefix}_{slug}` for blocks,
`{table_id}__r{row_index}` for rows, `{table_id}__r{row_index}_{col_id}` for cells.

Two independent fields exist for flagging suspect data: `confidence` (the LLM's own
self-reported certainty) and `flags` (populated by a separate backend validation pass,
e.g. an arithmetic check like `revenue - cost == gross_profit`) — kept separate so
validation logic can evolve independently of the parsing prompt.

### PDF parsing pipeline (`POST /api/reports/parse`, `app/routers/reports.py`)

`pdf_gatekeeper.check_pdf()` (`app/services/pdf_gatekeeper.py`) runs first and returns
a rejection reason (or `None`) — all local, free checks, to avoid spending an LLM call
on an upload that's empty, oversized/too many pages (guards against huge-context cost),
corrupt, or just a keyword sniff-test miss over the PDF's text layer via `pypdf`. This
is the one place a traditional PDF library touches the pipeline; it never feeds text to
the LLM, and it lets non-text-layer PDFs (scans) through the keyword check rather than
blocking them, since there's no signal either way.

`llm_client.parse_report()` (`app/services/llm_client.py`) sends the PDF inline as
base64 to the OpenAI Responses API (`client.responses.parse(..., text_format=
LLMFinancialReport)`) and logs token usage + cost (`app/core/pricing.py`) on every call.
It returns an `LLMFinancialReport` (`app/models/llm_report.py`) — the schema the LLM
actually fills in, which is id-free (slugs instead; see the schema section above).

`id_assigner.assign_ids()` (`app/services/id_assigner.py`) converts that into the real
`FinancialReport`, then `report_validator.validate()` (`app/services/report_validator.py`)
attaches arithmetic-mismatch `Flag`s in place. Both are pure functions with no I/O, so
they're covered by fast unit tests independent of the API (`tests/test_id_assigner.py`,
`tests/test_report_validator.py`) — the LLM call itself is only exercised by
`scripts/parse_sample.py` (manual, costs money) or stubbed out via monkeypatching
`app.services.llm_client.parse_report` in endpoint tests
(`tests/test_reports_endpoint.py`).

## Project status and roadmap

The project is built in phases; each phase has its own acceptance criteria before
moving to the next. Current state: **Phase 0 done; Phase 1 (PDF parsing) implemented**
— upload → gatekeeper → LLM extraction → id assignment → arithmetic validation, with a
frontend drag-and-drop uploader wired to it. Not yet done within Phase 1: a real
end-to-end run against a live financial report has not been verified (pending API
access and a sample PDF), and `report_validator`'s row-label matching is expected to
need tuning once tested against real filing labels.

- **Phase 1** — PDF parsing: a multimodal LLM reads the PDF directly (no traditional
  PDF-to-text/Markdown library in the pipeline) and outputs JSON matching the schema
  above, followed by the arithmetic-consistency validation pass.
- **Phase 2** — Narration script generation: LLM turns the parsed JSON into
  `[{text, target_id}, ...]`, analytical rather than a recitation of numbers.
- **Phase 3** — Frontend sync: render the schema JSON with dedicated components per
  block type (no Markdown renderer), scroll/highlight/zoom driven by `target_id` as
  narration plays.
- **Phase 4** — TTS: narration text to streaming audio, synced to the Phase 3 visual
  triggers. TTS provider not yet chosen (ElevenLabs or OpenAI TTS are the candidates);
  word-level timestamp precision is not required for v1.
- **Phase 5** — Live2D avatar (via `pixi-live2d-display` + PixiJS): volume-driven lip
  sync only, no complex motion, shown as a draggable/resizable floating widget over the
  full-screen content.
- **Phase 6** — Agent capability: the model decides when a data point warrants a web
  search (e.g. an abnormal YoY change), with a hand-rolled multi-turn loop (not just SDK
  agent defaults) with a max-turn guard, basic observability (per-turn logging, token
  usage, latency), and visible source citations in the narration.
- **Phase 7** (conditional on Phase 6 results) — replace the OpenAI SDK agent loop with
  a hand-rolled implementation on the Responses API, for harness-building experience.

LLM access is via the OpenAI SDK (model referred to as "GPT-5.6 Luna", with built-in web
search) — connection details are provided by the user when needed for a given phase,
not assumed in advance.

**Explicitly out of scope:** scraping web pages/links (PDF input only), saving/replaying
past narration sessions, complex emotion or body-motion driving for the avatar, and
cross-report comparison analysis.

## Conventions

- All repository content — code comments, sample/mock data, and UI copy — must be in
  English, regardless of the language used to discuss the project.
