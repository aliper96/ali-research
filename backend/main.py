"""
ali_researcher FastAPI application.

Endpoints
---------
POST /api/research
    Start a new research session.

GET  /api/research/{session_id}
    Poll the current state of a session as JSON.

GET  /api/research/{session_id}/stream
    Server-Sent Events stream for real-time progress and completion.

GET  /api/research/{session_id}/graph
    Knowledge graph enriched with Memgraph algorithms.

GET  /api/graph/global
    Global knowledge graph accumulated across all sessions.

GET  /api/sessions
    List recent sessions (from PostgreSQL).

GET  /api/health
    Health check.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

load_dotenv(Path(__file__).parent / ".env")  # backend/.env — must come before imports

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from .agent.researcher import run_research
from .agent.review_runner import run_review
from .agent.paper_parser import parse_paper
from .models.schemas import ResearchSession, StartResearchRequest
from .models.review_schemas import ReviewSession
from .storage.session_store import session_store
from .storage.review_store import review_store
from .storage.graph_store import graph_store
from .storage import db

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ali_researcher",
    description="Agentic academic research tool powered by Claude.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "memgraph": graph_store.is_available(),
        "postgres": db.is_available(),
    }


@app.get("/api/sessions")
async def list_sessions(limit: int = 50) -> list[dict]:
    """Return recent research sessions ordered by creation date descending."""
    return await session_store.list_sessions(limit=min(limit, 200))


# ---------------------------------------------------------------------------
# Review endpoints
# ---------------------------------------------------------------------------

@app.post("/api/review")
async def start_review(
    background_tasks: BackgroundTasks,
    paper_file: UploadFile,
    num_reviewers: int = Form(default=3),
    bib_file: UploadFile | None = None,
) -> dict:
    """
    Upload a paper (PDF or .tex) and optionally a .bib file.
    Returns a review session_id immediately; results arrive via SSE.
    """
    num_reviewers = max(1, min(5, num_reviewers))
    paper_bytes = await paper_file.read()
    bib_bytes = await bib_file.read() if bib_file else None

    parsed = parse_paper(paper_file.filename or "paper", paper_bytes, bib_bytes)

    session = await review_store.create_session(
        paper_title=parsed.title,
        paper_abstract=parsed.abstract,
        filename=paper_file.filename or "paper",
        num_reviewers=num_reviewers,
    )

    background_tasks.add_task(
        run_review,
        session_id=session.session_id,
        paper_title=parsed.title,
        paper_abstract=parsed.abstract,
        paper_text=parsed.full_text,
        bib_refs=parsed.bib_refs,
        num_reviewers=num_reviewers,
    )

    return {"session_id": session.session_id, "paper_title": parsed.title}


@app.get("/api/review/{session_id}", response_model=ReviewSession)
async def get_review_session(session_id: str) -> ReviewSession:
    session = await review_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review session '{session_id}' not found.")
    return session


@app.get("/api/review/{session_id}/stream")
async def stream_review_session(session_id: str) -> EventSourceResponse:
    session = await review_store.get_or_load_session(session_id)
    if session is None:
        async def _err():
            yield {"event": "error", "data": json.dumps({"detail": "Session not found."})}
        return EventSourceResponse(_err())

    if session.status in ("completed", "error"):
        async def _done():
            yield {"event": "complete", "data": session.model_dump_json()}
        return EventSourceResponse(_done())

    queue = review_store.get_queue(session_id)
    if queue is None:
        async def _noq():
            yield {"event": "error", "data": json.dumps({"detail": "Queue not found."})}
        return EventSourceResponse(_noq())

    async def _events():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield {"comment": "keep-alive"}
                continue

            if event.get("type") == "complete":
                done = await review_store.get_or_load_session(session_id)
                yield {"event": "complete", "data": (done or session).model_dump_json()}
                break
            else:
                yield {"event": "progress", "data": json.dumps(event)}

    return EventSourceResponse(_events())


@app.get("/api/reviews")
async def list_reviews(limit: int = 20) -> list[dict]:
    return await review_store.list_sessions(limit=min(limit, 100))


@app.get("/api/research/{session_id}/graph")
async def get_graph(session_id: str) -> dict:
    session = await session_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if session.status != "completed":
        raise HTTPException(status_code=202, detail="Research still running.")

    if not graph_store.is_available():
        if session.result:
            papers = [p.model_dump() for p in session.result.papers]
            edges = [{"source": l.source, "target": l.target, "type": "CITES"}
                     for l in session.result.citation_links]
            return {"nodes": papers, "edges": edges, "communities": 0, "memgraph": False}
        return {"nodes": [], "edges": [], "communities": 0, "memgraph": False}

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, graph_store.get_graph_data, session_id)
    data["memgraph"] = True
    return data


@app.get("/api/graph/global")
async def get_global_graph() -> dict:
    """Global knowledge graph — papers accumulated across ALL sessions."""
    if not graph_store.is_available():
        return {"nodes": [], "edges": [], "communities": 0, "total_papers": 0, "memgraph": False}

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, graph_store.get_global_graph_data)
    data["memgraph"] = True
    return data


@app.post("/api/research")
async def start_research(
    body: StartResearchRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    session = await session_store.create_session(body.input)
    session_id = session.session_id

    logger.info("Created session %s for input: %.80s…", session_id, body.input)

    background_tasks.add_task(
        run_research,
        session_id=session_id,
        user_input=body.input,
        depth=body.depth,
    )

    return {"session_id": session_id}


@app.get("/api/research/{session_id}", response_model=ResearchSession)
async def get_session(session_id: str) -> ResearchSession:
    session = await session_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session


@app.get("/api/research/{session_id}/stream")
async def stream_session(session_id: str) -> EventSourceResponse:
    session = await session_store.get_or_load_session(session_id)
    if session is None:
        async def _error_gen():
            yield {
                "event": "error",
                "data": json.dumps({"detail": f"Session '{session_id}' not found."}),
            }
        return EventSourceResponse(_error_gen())

    # Already done (e.g. client reconnected or session loaded from DB after restart)
    if session.status in ("completed", "error"):
        async def _done_gen():
            yield {"event": "complete", "data": session.model_dump_json()}
        return EventSourceResponse(_done_gen())

    queue = session_store.get_queue(session_id)
    if queue is None:
        # Shouldn't happen for a running session, but handle gracefully
        async def _err_gen():
            yield {
                "event": "error",
                "data": json.dumps({"detail": "Session queue not found."}),
            }
        return EventSourceResponse(_err_gen())

    async def _event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield {"comment": "keep-alive"}
                continue

            event_type = event.get("type")

            if event_type == "complete":
                done_session = await session_store.get_or_load_session(session_id)
                if done_session is not None:
                    yield {"event": "complete", "data": done_session.model_dump_json()}
                else:
                    yield {
                        "event": "complete",
                        "data": json.dumps({"session_id": session_id, "status": "completed"}),
                    }
                break

            elif event_type in ("log", "progress"):
                yield {"event": "progress", "data": json.dumps(event)}

            else:
                yield {"event": event_type or "message", "data": json.dumps(event)}

    return EventSourceResponse(_event_generator())
