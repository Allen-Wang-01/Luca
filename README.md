# Financial Agent

Upload a company's financial report as a PDF and an AI advisor walks you through it out
loud: what the numbers are, how they changed and what that means. As each figure is
mentioned it is highlighted on the report, and a card next to it shows the figure or a
chart.

## How it works

1. **Reading the report.** A multimodal model reads the PDF directly and returns the
   report as structured data: every table, row and cell with its own id. The backend
   then checks the totals against the rows that add up to them.
2. **Preparing the walkthrough.** An agent writes the script in a tool-calling loop. It
   never does arithmetic itself: it asks calculation tools for a change or a ratio
   between cells of the report, draws charts from the same cells, and can search the
   web for context the report doesn't give.
3. **Checking the script.** Every figure in every line is compared with the cell or the
   calculation the line cites. Anything that doesn't match goes back to the agent to
   fix, and a line that still can't be backed is cut.
4. **Playing it.** The page follows the script line by line: it scrolls to the figure,
   highlights it, and shows the card.

While the walkthrough is being prepared, the page shows the agent's work as it happens:
each turn, its calculations, searches and notes. Afterwards the same record, with tokens
and cost, is in the "Advisor's notes" panel.

## Demos

The start page lists walkthroughs prepared earlier (NVIDIA and Apple quarterly
reports). They open without an upload and without any model call.

## Running it locally

You need Python 3.11+, Node.js and an OpenAI API key.

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in OPENAI_API_KEY
python start.py             # http://localhost:8000
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173, proxies /api to the backend
```

To show the demos, point `DEV_SAMPLES_DIR` in `backend/.env` at a directory of saved
runs: `{name}.json` (a parsed report) next to `{name}.narration.json` (its script).

## Tests

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

The suite makes no network calls and costs nothing. `scripts/parse_sample.py` and
`scripts/narrate_sample.py` run the real pipeline against the API, which does.

## Project layout

```
backend/    FastAPI app: report schema (app/models/), parsing, narration agent and its
            tools (app/services/), endpoints (app/routers/), tests/
frontend/   React + TypeScript + Vite: report rendering and narration sync
            (src/components/report/, src/narration/), API clients (src/api/)
docs/       Notes on the report schema, the contract between the two
```

## Scope

English-language earnings releases and financial statements of listed companies. Banks,
insurers and funds aren't supported. The walkthrough is an automated reading of a
report, not investment advice.
