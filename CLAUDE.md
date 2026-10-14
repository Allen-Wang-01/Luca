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
python start.py                    # serves http://localhost:8000, health at /api/health
                                    # (short for `uvicorn app.main:app --reload`)
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

### Saved runs: previews and the start page's demos (no API calls)

Set `DEV_SAMPLES_DIR=../temp` in `backend/.env` and restart the backend. The start page
then lists every `{name}.json` that has a `{name}.narration.json` as a demo (`GET
/api/dev/samples`), and any saved run opens at
`http://localhost:5173/?sample=NVIDIAAn` (optionally `&version=v1`). This loads
`temp/NVIDIAAn.json` (parsed report, re-validated with the current rules) plus
`temp/NVIDIAAn.narration.json` (or `.narration.v1.json`, as saved by
`scripts/narrate_sample.py`) and seeds the narration cache, so no parse or narration
request is made. The endpoint (`app/routers/dev_samples.py`) isn't registered at all
unless `DEV_SAMPLES_DIR` is set. Everything in that directory is served to anyone, so
a deployed backend should point it at one holding only the demos.

Saved speech is part of the same preview. `python scripts/synthesize_sample.py
../temp/NVIDIAAn.narration.json` (real API, costs money; `--dry-run` shows the estimate
first) writes one WAV per line into `temp/NVIDIAAn.audio/`, named after the line's text,
for roughly the first `--minutes` of the script (default 4.5). The sample endpoint
returns the clip for each line whose exact text has one, so every saved narration
version picks up whichever of its lines are voiced, and already-saved lines are never
paid for twice.

Charts can be previewed the same way, on top of a narration that already has speech:
`python scripts/illustrate_sample.py ../temp/NVIDIAAn.json ../temp/NVIDIAAn.charts.json`
(no API calls) runs hand-written chart tool calls through the real chart tools and
validator and writes `temp/NVIDIAAn.narration.charts.json`, served at
`?sample=NVIDIAAn&version=charts`. Line text is untouched, so saved clips still match.
The charts file can also list `calculations`, run first through the real calculation
tools, so charts of calculated figures can be previewed the same way.

## Architecture

This is an AI tool that turns an uploaded financial report PDF into a spoken,
advisor-style walkthrough synced to on-screen content (auto-scroll, highlight, and a
karaoke-style zoom on whatever the narration is currently discussing, and cards that
pop up next to it with the figure or a chart). The AI is an analyst reporting to you;
that sync between what is said and what the page does is the point of the product, and
no change should weaken it.

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

Nothing downstream is meant to depend on what a company calls its rows. The parser
marks each row with what it measures (`quantity`), the scale it is printed in (`scale`),
the sub-heading it sits under (`group`), and, for a total, the rows that add up to it
(`sum_of`); calculations, labels and the arithmetic check all work from those. All four
are optional, and a report parsed before they existed falls back to the older guesses
(report-wide unit scale, a row label containing "per share", a few label-matching
arithmetic rules) - which is why the saved NVIDIA sample still loads unchanged.

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
`FinancialReport`. Rows have no ids yet at that point, so a total refers to its parts by
the row `index` the model writes on every row; those are turned into row ids here, and
a table whose written indexes don't match the rows' real positions loses all its
`sum_of` rather than risk pointing one row off. Then `report_validator.validate()`
(`app/services/report_validator.py`) attaches `Flag`s in place: each total is checked
against the rows it names, column by column. A sum that fails in some columns is a
misread figure (`arithmetic_mismatch`); one that fails in every column is a wrong
relationship and is only logged; one that fails with a single column to check is
`unconfirmed_sum`. A table whose columns can't be told apart gets `ambiguous_columns`.
Only `arithmetic_mismatch` is shown to the narration model
(`narration_context.NARRATED_FLAG_CODES`), since the prompt tells it to warn the
listener about every flag it sees. Both are pure functions with no I/O, so
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

Once the script is written it is checked, as a fixed step of the loop rather than a
tool the model may or may not call (`_review_and_correct`). Every line lists where its
figures come from (`figures`, the same references the tools take):
- `narration_figures.py` compares each amount and percentage in a line's text with what
  the line lists, within the rounding it was said with. A mismatch is `must_fix`. It
  A line can also carry a calculation of its own (`calculations`: the figures and one
  operation), for a number that occurs to the model while writing - calling a tool
  there would cost a turn, so it used to do the arithmetic in its head. The backend
  works it out with the tools' own code (`narration_tools.evaluate`) and the text has
  to match the result. It
  also raises two patterns as advice: a cited cell sharing neither row nor column with
  the others cited from its table (this year's figure for one thing against last year's
  for another), and a highlighted cell that is off the row and column of everything the
  line cites.
- `narration_reviewer.py` is one separate model call that reads each line next to the
  full labels of the figures it cites and reports any presented as the wrong period or
  item. It sees only the script and the labels, not the report or the agent's
  conversation. Its findings are advice, and a failed call is logged and skipped.
- Findings go back to the agent, which fixes the script in its own conversation
  without tools - up to `MAX_CORRECTIONS` turns, the second only if a figure is still
  wrong. It returns only the lines it changes (`LLMScriptEdits`: replace or remove, by
  line number; `narration_validator.apply_edits` applies them), so a correction costs
  a few lines of output rather than the whole script again, and no other line can come
  back different. Figures on a line that cites a web page are only excused from the
  check if that page really came back from a search - a made-up link would otherwise
  be removed later and leave its figures with no source. A figure it worked out itself can stay if it adds the calculation to the line.
  It is told to remove what it can't fix and reword the neighbouring lines so the
  script still flows. Only a line with a `must_fix` finding left after that is cut by
  the code, and a script that loses more than half its lines is rejected (→ 502).
The rounds, findings and cut lines are in the trace's `review` and shown in the
"Advisor's notes" panel; the reviewer call and correction turns are counted in the
trace's totals.

The supporting pieces are pure functions with their own tests, same as the parsing
pipeline:
- `narration_context.py` renders the report into compact, id-annotated prompt text
  (one line per row, with the row id and every cell id written out next to its value)
  and collects the set of valid target ids.
- `narration_tools.py` — `percent_change` / `ratio` / `difference` / `combine` (several
  figures added and subtracted in one call). Operands are
  **references, not numbers**: `{id: <cell id>, quote: null}` for a table figure, or
  `{id: <paragraph id>, quote: "$3.2 billion"}` for a figure that only appears in
  prose — the quote is checked to appear verbatim in that paragraph before use. Values
  are looked up here, and figures printed in different scales (a row's own `scale`, the
  report's unit scale, "billion" in prose) are put on a common one when mixed, so
  figures never pass through the model's own transcription or mental arithmetic. Every
  result gets a `calc_id` that a later call can pass as an operand, for figures that
  take two steps. Figures of different kinds (a row's `quantity`) can't be added,
  subtracted or compared; `ratio` can divide one by another. Errors come back as tool
  output so the model can correct itself.
- `report_labels.py` — how a row and a column are named away from their table: with
  the sub-heading where a row label is shared, and with the column's group header.
- `narration_visuals.py` — `bar_chart` / `share_bar` / `waterfall`, the charts a line
  can bring up in a card. Same reference operands as the calculation tools (it reuses
  `FigureIndex.resolve`), so the model picks the chart type, labels and figures but
  never writes a value; an item can be a `calc_id`, and is then marked as calculated on
  the card. A chart is checked against itself before it gets an id (a
  waterfall's start plus its steps must equal its end, a share bar's parts can't exceed
  its total - both within the rounding of the printed figures); a failed chart is a tool
  error the model can correct. A `ChartBuilder` holds the charts built in one run.
- `narration_validator.py` attaches each line's chart (`attach_visuals`: a `chart_id`
  no tool produced is dropped and the line kept; an unknown `chart_emphasis` is dropped
  and the chart kept; an emphasis follows the line's highlight where that is one of the
  chart's items, and is otherwise dropped unless it is a figure the line cites; a chart
  that comes back after a line without it is only shown for its first run of lines -
  all recorded in the trace's `removed_visuals`), repairs
  `target_id`s that don't exist (nearest valid
  ancestor cell → row → block, then the previous line's target), drops cited source
  URLs that didn't come back from a web search in this run or are on a blocked site
  (forums, social media, video — `BLOCKED_SOURCE_DOMAINS`), and rejects scripts that
  are empty or mostly invented (→ 502).

The model also has the API's built-in `web_search` tool, for outside context on changes
the report doesn't explain. Those searches run on OpenAI's side inside a single model
call, so the loop doesn't execute them: it records each search's query and returned
URLs (`include=["web_search_call.action.sources"]`) in the trace, caps the total with
`MAX_WEB_SEARCHES` (passed as `max_tool_calls`, and the tool is withdrawn once used up),
and uses the returned URLs to verify each line's `sources`.

What comes back from a search is the query and the URLs, not the pages: their content
is only visible to the model inside the call that searched, and nothing of it reaches
the next turn. A report with many calculations is written several turns after its
search, and by then the model had nothing left to cite (the first report it worked on
happened to be written in the turn it searched in, which hid this). So the model takes
notes - `narration_notes.py`, a `note_finding(fact, url)` tool it calls in the same
turn as the search. Tool calls stay in the conversation, so the notes are there when
the script is written, and the URL is checked against the search results on the spot,
while the model can still correct it. Search calls are billed per
call ($10 / 1k) on top of tokens; `pricing.py` adds that fee to each turn's cost (the
search content itself already shows up in the response's input token usage).

A run can be followed while it happens. `generate_narration` takes an `on_event`
callback and reports each turn as it starts and ends (the finished turn is the trace's
own `AgentTurn`) and each check of the script. `POST /api/reports/narration/stream`
sends those as server-sent events, with a keep-alive comment every 15 seconds, and
ends with a `result` event carrying what `/narration` returns, or an `error` event.
The frontend uses the stream (`api/narration.ts`) and shows the events on the cover
while the walkthrough is prepared (`LiveActivity`, built from the notes panel's
`TurnView`). With a listener the model calls themselves are streamed
(`_call_model`, `client.responses.stream`), so three things are reported from inside a
turn: each web search as it comes back, each tool call as the model asks for it, and
each line of the script as its text is completed (read out of the JSON written so
far). Tools still run after the call returns, so results come with `turn_finished`.
Without a listener (`/narration`, `scripts/narrate_sample.py`) the call is the plain
`responses.parse` it always was. The run is not cancelled when the listener
disconnects. The streamed call has only been tested with fakes, not yet on a real run.

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

A report is shown as a sequence of screens (`ReportView`): a cover (company, period,
what the parse found, and the start button once the narration is ready), the
walkthrough itself, a closing screen when the last line has played, and a plain reading
view. The start page (`HomeScreen`) is only there while no report is loaded.

The page works from what a script already carries - each line's target, the figures it
cites, its chart and sources - plus the report's own structure. It knows nothing of how
the narration is organized, so the narration can be rewritten without touching it:
- `narration/lineFocus.ts` decides what a line lights up. Besides its target, the other
  cells it cites in the same table are lit more quietly. A line that targets a whole
  table is narrowed to the cells it cites there; if it cites none it is a remark, and
  nothing is highlighted - the line is shown in the middle of the screen instead
  (`SpotlightLine`).
- `narration/segments.ts` cuts the progress bar into runs of lines that stay in one
  section of the report (`SegmentedProgress`; a segment jumps to its first line).
- `narration/mentions.ts` lists the figures and charts the lines have pointed at, in
  order. `FigureRail` shows the ones reached so far beside the report (a drawer on
  narrower screens), and the closing screen lays all of them out with the sources.
Tables show the statement's hierarchy from `sum_of`, `group` and rows without figures
(totals, items, sub-headings); a report parsed before those existed comes out flat.

On a phone a card docks above the narration bar instead of following its target, the
target is scrolled to the top of the screen rather than the middle, tables scroll
sideways under a fixed label column, and `useNarrationPlayer.play` starts the clip
inside the tap, which phone browsers require for sound. None of the phone behaviour
has been tried on a real device yet.

While a line plays, a card floats next to its target (`AnchoredCard`, which handles
placement): `VisualCard` with the line's chart if it has one (`charts/VisualChart.tsx`;
the item named by `emphasis` stays in full color and the rest fades, and the card stays
up across consecutive lines that share a chart), otherwise `FocusCard` repeating the
table figure for row and cell targets. A card names its row and column the way the
backend does (`narration/targetIndex.ts`: sub-heading in front of a shared row label,
group header in front of the column) and gives the row's own unit where it isn't the
table's. Only charts in cards have item-level emphasis;
the report's own `ChartBlock`s still have no data-point ids.

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
target single cells where one figure carries the line. A line that named a
publication while its link was rejected turned out to be the model inventing the link:
it writes a plausible, title-like address where the search returned an opaque one
(settled on the Apple runs below, and now caught when the note is taken). The rule
about flagging information from a later period still hasn't been exercised. Speech
exists for saved samples only, and only for older NVIDIA scripts; the Live2D avatar
has been dropped. The narration agent picks its own charts, four or five a script on
the Apple runs, including charts of calculated figures. Phase 1 has been
run end-to-end against a real NVIDIA quarterly report: table figures were verified
accurate, id generation and arithmetic validation worked correctly on real data. Two
issues found during that real run were fixed: an `oneOf` in the LLM-facing schema that
OpenAI's structured-output validator rejects (fixed by removing the discriminator so
pydantic emits `anyOf` instead — see `llm_report.py`), and paragraph text being
paraphrased instead of extracted verbatim, plus bullet lists being merged into one
paragraph instead of split per item (fixed via `llm_client.py` prompt instructions and
a new `style: "list_item"` — that specific fix has not yet been re-verified against a
real run).

The pipeline has also been run on a second report, Apple's quarterly statements, with
no code changed for it: all 238 cells matched the PDF and ids were fine, but the run
exposed what the next round of changes addressed - a line that read out last year's
net income as this year's, per-share and share-count rows scaled by the report-wide
unit, repeated row labels and repeated column dates that cards couldn't tell apart,
arithmetic rules that matched none of its row labels, no way to add more than two
figures or calculate in two steps, and charts brought back at the end of the script.
Those changes (row `quantity`/`scale`/`group`/`sum_of`, `combine` and reusable
calculation results, charts of calculated figures, the figure check with its reviewer
and correction turns, notes on search results) are covered by unit tests and **have
been run against the real API on Apple**:
- Re-parsed with the new prompt, the same 238 cells came back, every row's quantity
  and scale was right, and all 22 totals the parser declared held in every column.
  The parser folded the two sales breakdowns into the income statement this time
  (three tables instead of five, with their column groups) and produced no paragraph
  blocks; titles and unit notes are on the tables. Accepted as is.
- Narrated five times while the checks were being tuned. In the last run 55 stated
  figures all matched what their lines cite, one line was missing a reference and was
  fixed by a single edited line, no line was cut, and eight lines carry a real source.
  The check earned its place early: three figures the model had worked out in its
  head, one line highlighting a region while emphasizing the next one's bar, and a
  made-up news link behind two analyst estimates were all caught.
- The search problem was only found here: Apple's script was never written in the turn
  that searched, so no run used a single search result until the model took notes.

Still open after those runs:
- **NVIDIA has not been narrated with this code.** Its saved parse has none of the new
  row fields, so it is the test of the fallbacks; so far that rests on unit tests and
  on replaying its saved tool calls.
- Nothing checks the prose. The last Apple script opens with a garbled clause and
  calls term debt "total debt"; both passed, since the figures are right.
- The reviewer sees a calculation as its formula, without the labels of the figures in
  it, so it can't tell when a result is described as something it isn't.
- A figure taken from a web page is held to a real link, not to what the note says.
- A line about nothing in particular (a remark, a takeaway) still highlights a whole
  table. Left for when the page gets a closing screen or a key-points panel.
- A run now costs about $0.09 and two minutes, three times the first Apple run: web
  searches are $0.01 each plus their content in the input, and a report with many
  calculations takes seven or eight turns (`MAX_TURNS` is 8).
- A line's own `calculations` are rarely used; the model mostly calculates ahead.

A third report (Meta) is being held back, unparsed, to check that none of this was
fitted to the first two.

Supported input is English-language earnings releases and financial statements of
listed companies; banks, insurers and funds are out of scope.

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
- **Phase 5** — Live2D avatar: dropped, not going to be built.
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
