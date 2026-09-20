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

## Frontend (React + TypeScript + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open the printed local URL. The dev server proxies `/api/*` to `http://localhost:8000`,
so run the backend first (or alongside) to see "Backend status: connected".

## Project layout

```
backend/    FastAPI app, Pydantic schema (app/models/report.py)
frontend/   React app, TypeScript types mirroring the schema (src/types/report.ts)
docs/       Schema design notes
```
