# ali_researcher

AI-powered academic research assistant. Give it a topic, arXiv ID, DOI, or URL — it launches an agentic Claude loop that searches arXiv and Semantic Scholar, synthesizes the findings, and delivers a structured report with papers, citation network, gap analysis, and implementation roadmap.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python · FastAPI · Anthropic SDK · SSE |
| AI Agent | Claude Sonnet 4.6 with tool-use loop |
| Paper sources | arXiv API · Semantic Scholar API · DuckDuckGo |
| Frontend | Next.js 14 · TypeScript · Tailwind CSS |
| UI | shadcn/ui-style components · Lucide icons |
| Data | TanStack Query v5 · TanStack Table v8 |
| Charts | Recharts (citation scatter plot) |

## Setup

### 1. Backend

```bash
cd backend

# Copy env and add your Anthropic API key
cp .env.example .env
# Edit .env → ANTHROPIC_API_KEY=sk-ant-...

# Install dependencies (Python 3.11+ recommended)
pip install -r requirements.txt

# Run
uvicorn backend.main:app --reload --port 8000
```

The API will be at `http://localhost:8000`.
Swagger docs: `http://localhost:8000/docs`

### 2. Frontend

```bash
cd frontend

# Copy env (defaults point to localhost:8000)
cp .env.local.example .env.local

# Install
npm install

# Dev server
npm run dev
```

Open `http://localhost:3000`.

## Architecture

```
ali_researcher/
├── backend/
│   ├── main.py                  # FastAPI app + routes
│   ├── agent/
│   │   ├── researcher.py        # Agentic loop (claw-code pattern)
│   │   └── tools.py             # Tool specs + executors
│   ├── models/schemas.py        # Pydantic models
│   └── storage/session_store.py # In-memory sessions + SSE queues
└── frontend/
    ├── src/app/
    │   ├── page.tsx             # Home / search
    │   └── research/[id]/      # Live research view
    ├── src/components/
    │   ├── SearchForm.tsx
    │   ├── ResearchProgress.tsx # Real-time SSE log feed
    │   ├── PapersTable.tsx      # TanStack Table with sort/filter/expand
    │   ├── CitationNetwork.tsx  # Recharts scatter plot
    │   └── ResearchReport.tsx   # Tabbed results view
    └── src/lib/
        ├── api.ts               # API client + SSE streaming
        └── types.ts             # Shared TypeScript types
```

## Research flow

```
User input
    ↓
POST /api/research  →  creates session, returns session_id
    ↓
BackgroundTask: run_research()
    ├── Claude calls search_arxiv(query)
    ├── Claude calls search_semantic_scholar(query)
    ├── Claude calls get_arxiv_paper(id) for key papers
    ├── Claude calls get_paper_citations(id)
    ├── Claude calls search_web(query) for implementations
    └── Claude returns final JSON report
    ↓
Session updated → SSE "complete" event
    ↓
Frontend renders: Summary · Papers · Network · Gaps · Roadmap
```

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/research` | Start research (`{ input, depth }`) |
| `GET` | `/api/research/{id}` | Poll session JSON |
| `GET` | `/api/research/{id}/stream` | SSE real-time stream |
| `GET` | `/api/health` | Liveness probe |

### Depth levels

- `quick` — 5-8 papers, ~6 tool calls, fast
- `standard` (default) — 10-15 papers, ~12 tool calls
- `deep` — 20+ papers, ~20 tool calls, thorough

## Input formats

- Free topic: `"attention mechanisms in transformers"`
- arXiv ID: `"2301.07041"` or `"arxiv:2301.07041"`
- DOI: `"10.1145/3531146.3533234"`
- URL: `"https://arxiv.org/abs/2312.00752"`
