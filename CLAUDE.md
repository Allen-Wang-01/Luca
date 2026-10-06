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

### Previewing saved runs without API calls (local dev only)

Set `DEV_SAMPLES_DIR=../temp` in `backend/.env` and restart the backend, then open
`http://localhost:5173/?sample=NVIDIAAn` (optionally `&version=v1`). This loads
`temp/NVIDIAAn.json` (parsed report, re-validated with the current rules) plus
`temp/NVIDIAAn.narration.json` (or `.narration.v1.json`, as saved by
`scripts/narrate_sample.py`) and seeds the narration cache, so no parse or narration
request is made. The endpoint (`app/routers/dev_samples.py`) isn't registered at all
unless `DEV_SAMPLES_DIR` is set.

Saved speech is part of the same preview. `python scripts/synthesize_sample.py
../temp/NVIDIAAn.narration.json` (real API, costs money; `--dry-run` shows the estimate
first) writes one WAV per line into `temp/NVIDIAAn.audio/`, named after the line's text,
for roughly the first `--minutes` of the script (default 4.5). The sample endpoint
returns the clip for each line whose exact text has one, so every saved narration
version picks up whichever of its lines are voiced, and already-saved lines are never
paid for twice.

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

### Narration generation (`POST /api/reports/narration`, same router)

Takes a parsed `FinancialReport` (the client sends it back — nothing is stored
server-side) and returns `{lines: NarrationScript, trace}`. Kept separate from `/parse`
so the report renders immediately and narration can be retried alone.

`narration_agent.generate_narration()` (`app/services/narration_agent.py`) is a
hand-rolled tool-calling loop on the Responses API (not an SDK agent runner): each turn
calls the model with the calculation tools from `narration_tools.py`, executes any calls
it made, feeds the outputs back, and stops when the model returns the final
structured script. `MAX_TURNS` caps the loop (the last turn forces `tool_choice="none"`)
and `MAX_TOOL_CALLS` caps total calculations. Each turn is logged and recorded in a
`NarrationTrace` (tool calls, tokens, cost, latency) that the frontend shows in its
"Advisor's notes" panel.

The supporting pieces are pure functions with their own tests, same as the parsing
pipeline:
- `narration_context.py` renders the report into compact, id-annotated prompt text
  (one line per row, with the row id and every cell id written out next to its value)
  and collects the set of valid target ids.
- `narration_tools.py` — `percent_change` / `ratio` / `difference`. Operands are
  **references, not numbers**: `{id: <cell id>, quote: null}` for a table figure, or
  `{id: <paragraph id>, quote: "$3.2 billion"}` for a figure that only appears in
  prose — the quote is checked to appear verbatim in that paragraph before use. Values
  are looked up here, and table (report unit scale) and prose ("billion") figures are
  put on a common scale when mixed, so figures never pass through the model's own
  transcription or mental arithmetic. Errors come back as tool output so the model can
  correct itself.
- `narration_validator.py` repairs `target_id`s that don't exist (nearest valid
  ancestor cell → row → block, then the previous line's target), drops cited source
  URLs that didn't come back from a web search in this run or are on a blocked site
  (forums, social media, video — `BLOCKED_SOURCE_DOMAINS`), and rejects scripts that
  are empty or mostly invented (→ 502).

The model also has the API's built-in `web_search` tool, for outside context on changes
the report doesn't explain. Those searches run on OpenAI's side inside a single model
call, so the loop doesn't execute them: it records each search's query and returned
URLs (`include=["web_search_call.action.sources"]`) in the trace, caps the total with
`MAX_WEB_SEARCHES` (passed as `max_tool_calls`, and the tool is withdrawn once used up),
and uses the returned URLs to verify each line's `sources`. Search calls are billed per
call ($10 / 1k) on top of tokens; `pricing.py` adds that fee to each turn's cost (the
search content itself already shows up in the response's input token usage).

The agent loop is tested with a fake client (`tests/test_narration_agent.py`);
`scripts/narrate_sample.py parsed.json` runs it against the real API (costs money).

### Speech (`app/services/tts_client.py`)

`tts_client.synthesize(text)` turns one narration line into a WAV clip with its
duration. It is the only module that knows the provider (`gpt-4o-mini-tts`, which OpenAI
shuts down on 2027-01-06 - the replacement goes in this file). Audio is requested as raw
PCM so duration is exact and silence is detectable without an audio library; a clip that
is silent or far too short for its text is retried once and otherwise returned with a
warning. Cost is estimated from audio length (`pricing.calculate_tts_cost`), since the
speech endpoint reports no usage. So far speech only exists for saved samples (see
"Previewing saved runs"); a freshly uploaded report is still narrated with timed
captions only.

On the frontend, `useNarrationPlayer` takes the script plus an optional list of clips
parallel to its lines. A line with a clip lasts exactly as long as its audio; a line
without one is timed from its word count, so a partly voiced script still plays through.

On the frontend, `useGeneratedNarration` requests the script once per report (cached at
module level so StrictMode's double effect doesn't pay twice) and falls back to
`buildStubScript` with a retry prompt if generation fails. Narration is English-only for
now.

## Project status and roadmap

The project is built in phases; each phase has its own acceptance criteria before
moving to the next. Current state: **Phase 0, 1 and 3 done; Phase 2 done** as a
tool-calling agent with calculation tools (see "Narration generation" above), verified
against the real NVIDIA report. **Phase 6's web search is implemented** in the same loop
and verified against the real API: searches run, cited links are checked, and lines now
target single cells where one figure carries the line. Two things from that run are
still open: a line can name a publication while its link is rejected by the validator
(the rejected links are now recorded in the trace, so the next real run shows whether
they were invented or just spelled differently from the search result), and the rule
about flagging information from a later period hasn't been exercised yet. Phases 4–5
(TTS, avatar) are next. Phase 1 has been
run end-to-end against a real NVIDIA quarterly report: table figures were verified
accurate, id generation and arithmetic validation worked correctly on real data. Two
issues found during that real run were fixed: an `oneOf` in the LLM-facing schema that
OpenAI's structured-output validator rejects (fixed by removing the discriminator so
pydantic emits `anyOf` instead — see `llm_report.py`), and paragraph text being
paraphrased instead of extracted verbatim, plus bullet lists being merged into one
paragraph instead of split per item (fixed via `llm_client.py` prompt instructions and
a new `style: "list_item"` — that specific fix has not yet been re-verified against a
real run). `report_validator`'s row-label matching is still expected to need tuning for
non-English or differently-worded reports (see the language-independence discussion
this repo's chat history covered, not yet acted on).

- **Phase 1** — PDF parsing: a multimodal LLM reads the PDF directly (no traditional
  PDF-to-text/Markdown library in the pipeline) and outputs JSON matching the schema
  above, followed by the arithmetic-consistency validation pass.
- **Phase 2** — Narration script generation: LLM turns the parsed JSON into
  `[{text, target_id}, ...]`, analytical rather than a recitation of numbers.
- **Phase 3** — Frontend sync: render the schema JSON with dedicated components per
  block type (no Markdown renderer), scroll/highlight/zoom driven by `target_id` as
  narration plays. Phase 2 (the real narration script) doesn't exist yet, so Phase 3
  is built against a stub script instead of waiting: a `NarrationScript =
  {text: string, target_id: string}[]` contract, fed by a placeholder generated from
  `report.blocks` in order (block content as `text`, block `id` as `target_id`). The
  sync engine (scroll/highlight/scale) is built and tested against that stub; swapping
  in Phase 2's real output later should require no changes to the sync engine itself,
  only to what produces the script.
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
- Model-facing text (prompts, tool descriptions, tool error messages) uses generic,
  made-up examples — never figures, labels, or ids from a real report used for testing
  (e.g. the NVIDIA sample). Otherwise test runs on that report overstate how well the
  prompt generalizes.
