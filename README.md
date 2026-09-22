# Financial Agent

An AI tool that explains a company's financial report (PDF) with a spoken,
advisor-style walkthrough synced to the on-screen content.

See [docs/schema.md](docs/schema.md) for the data contract used across the backend
parser, frontend rendering, and narration sync.

## Backend (Python + FastAPI)

Dependencies are isolated in a virtual environment — never installed globally.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # run this every time before working in backend/
pip install -r requirements.txt
cp .env.example .env        # fill in OPENAI_API_KEY when available
uvicorn app.main:app --reload
```

Health check: `curl http://localhost:8000/api/health` → `{"status": "ok"}`

Upload and parse a report: `POST /api/reports/parse` with a `multipart/form-data` `file`
field (a PDF). Runs a cheap keyword-based gatekeeper check first, then the real
extraction via the OpenAI Responses API.

### Tests

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt   # adds pytest, httpx, reportlab on top of requirements.txt
pytest -q
```

All automated tests are self-contained (no network calls, no API cost). To sanity-check
extraction against a real report:

```bash
python scripts/parse_sample.py path/to/report.pdf   # hits the real API - costs money
```

## Frontend (React + TypeScript + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open the printed local URL. The dev server proxies `/api/*` to `http://localhost:8000`,
so run the backend first (or alongside). Drag a report PDF onto the upload zone to parse
it end-to-end.

## Project layout

```
backend/    FastAPI app: schema (app/models/), PDF parsing pipeline (app/services/), tests/
frontend/   React app: PDF uploader (src/components/), API client (src/api/), mirrored types (src/types/)
docs/       Schema design notes
```
