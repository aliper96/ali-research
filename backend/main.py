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
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv(Path(__file__).parent / ".env")  # backend/.env — must come before imports

from fastapi.responses import Response
from .agent.researcher import run_research
from .agent.review_runner import run_review
from .agent.audit_runner import run_audit
from .agent.deep_researcher import run_deep_research
from .agent.auto_researcher import run_auto_research
from .agent.lit_runner import run_lit_review
from .agent.compare_runner import run_compare
from .agent.draft_runner import run_draft
from .agent.paper_parser import parse_paper
from .agent.websearch_runner import run_websearch
from .agent.docs_runner import process_upload, answer_question
from .agent.pdf_export import generate_research_pdf, generate_review_pdf
from .agent.latex_coach import run_latex_coach, generate_annotated_pdf
from .storage.latex_store import latex_store
from .models.latex_schemas import LatexCoachSession
from .models.schemas import ResearchSession, StartResearchRequest
from .models.review_schemas import ReviewSession
from .models.audit_schemas import AuditSession, StartAuditRequest
from .models.deep_research_schemas import DeepResearchSession, StartDeepResearchRequest
from .models.websearch_schemas import WebSearchSession, StartWebSearchRequest
from .models.docs_schemas import DocRecord, DocsQARequest, DocsQAResult
from .storage.session_store import session_store
from .storage.review_store import review_store
from .storage.audit_store import audit_store
from .storage.deep_store import deep_store
from .storage.auto_store import auto_store
from .storage.lit_store import lit_store
from .storage.websearch_store import websearch_store
from .storage.artifact_store import (
    list_artifacts, read_artifact, list_all_sessions_with_artifacts
)
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


async def _watch_scheduler() -> None:
    """Background task: run due watches every 5 minutes."""
    while True:
        await asyncio.sleep(300)  # check every 5 min
        try:
            due = await db.get_due_watches()
            for w in due:
                logger.info("Watch scheduler: running watch %s (%s)", w["watch_id"], w["query"])
                try:
                    tmp_session = await session_store.create_session(w["query"])
                    await run_research(
                        session_id=tmp_session.session_id,
                        user_input=w["query"],
                        depth=w.get("depth", "quick"),
                    )
                    tmp = await session_store.get_or_load_session(tmp_session.session_id)
                    result_summary = None
                    if tmp and tmp.result:
                        result_summary = {
                            "session_id":  tmp.session_id,
                            "paper_count": len(tmp.result.papers),
                            "top_papers":  [p.title for p in tmp.result.papers[:3]],
                            "summary":     tmp.result.summary[:300],
                        }
                    await db.update_watch_result(w["watch_id"], result_summary or {}, w.get("schedule_hours", 168))
                except Exception as exc:
                    logger.warning("Watch %s run failed: %s", w["watch_id"], exc)
        except Exception as exc:
            logger.warning("Watch scheduler iteration failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    asyncio.create_task(_watch_scheduler())
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
        "papers_in_memory": await db.count_papers_memory(),
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


@app.get("/api/review/{session_id}/export/pdf")
async def export_review_pdf(session_id: str) -> Response:
    """Generate and download a formatted PDF of the review results."""
    session = await review_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review session '{session_id}' not found.")
    if session.status != "completed":
        raise HTTPException(status_code=400, detail="Review session not yet completed.")

    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        generate_review_pdf,
        session_id,
        session,
    )

    slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in (session.paper_title or "review"))
    slug = slug[:40].strip().replace(" ", "-").lower()
    filename = f"review-{slug or session_id[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reviews")
async def list_reviews(limit: int = 20) -> list[dict]:
    return await review_store.list_sessions(limit=min(limit, 100))


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------

@app.post("/api/audit")
async def start_audit(body: StartAuditRequest, background_tasks: BackgroundTasks) -> dict:
    """Start a paper audit session: compare claims vs. public codebase."""
    session = await audit_store.create_session(body.input)
    background_tasks.add_task(run_audit, session_id=session.session_id, user_input=body.input)
    return {"session_id": session.session_id}


@app.get("/api/audit/{session_id}", response_model=AuditSession)
async def get_audit_session(session_id: str) -> AuditSession:
    session = await audit_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Audit session '{session_id}' not found.")
    return session


@app.get("/api/audit/{session_id}/stream")
async def stream_audit_session(session_id: str) -> EventSourceResponse:
    session = await audit_store.get_or_load_session(session_id)
    if session is None:
        async def _err():
            yield {"event": "error", "data": json.dumps({"detail": "Session not found."})}
        return EventSourceResponse(_err())

    if session.status in ("completed", "error"):
        async def _done():
            yield {"event": "complete", "data": session.model_dump_json()}
        return EventSourceResponse(_done())

    queue = audit_store.get_queue(session_id)
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
                done = await audit_store.get_or_load_session(session_id)
                yield {"event": "complete", "data": (done or session).model_dump_json()}
                break
            else:
                yield {"event": "progress", "data": json.dumps(event)}

    return EventSourceResponse(_events())


@app.get("/api/audits")
async def list_audits(limit: int = 20) -> list[dict]:
    return await audit_store.list_sessions(limit=min(limit, 100))


# ---------------------------------------------------------------------------
# Watch endpoints
# ---------------------------------------------------------------------------

class CreateWatchRequest(BaseModel):
    query: str
    depth: str = "quick"
    schedule_hours: int = 168  # default: weekly


@app.post("/api/watch")
async def create_watch(body: CreateWatchRequest) -> dict:
    """Create a recurring research watch. Runs automatically on schedule."""
    watch_id = str(uuid.uuid4())
    result = await db.create_watch(
        watch_id=watch_id,
        query=body.query,
        depth=body.depth,
        schedule_hours=max(1, min(body.schedule_hours, 8760)),
    )
    if not result:
        raise HTTPException(status_code=503, detail="Database unavailable — watch not persisted.")
    return result


@app.get("/api/watches")
async def list_watches() -> list[dict]:
    return await db.list_watches()


@app.delete("/api/watch/{watch_id}")
async def delete_watch(watch_id: str) -> dict:
    deleted = await db.delete_watch(watch_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Watch '{watch_id}' not found.")
    return {"deleted": True, "watch_id": watch_id}


@app.post("/api/watch/{watch_id}/run")
async def run_watch_now(watch_id: str, background_tasks: BackgroundTasks) -> dict:
    """Manually trigger a watch run immediately."""
    watches = await db.list_watches()
    watch = next((w for w in watches if w["watch_id"] == watch_id), None)
    if watch is None:
        raise HTTPException(status_code=404, detail=f"Watch '{watch_id}' not found.")

    async def _run():
        try:
            tmp_session = await session_store.create_session(watch["query"])
            await run_research(
                session_id=tmp_session.session_id,
                user_input=watch["query"],
                depth=watch.get("depth", "quick"),
            )
            tmp = await session_store.get_or_load_session(tmp_session.session_id)
            result_summary = None
            if tmp and tmp.result:
                result_summary = {
                    "session_id":  tmp.session_id,
                    "paper_count": len(tmp.result.papers),
                    "top_papers":  [p.title for p in tmp.result.papers[:3]],
                    "summary":     tmp.result.summary[:300],
                }
            await db.update_watch_result(watch_id, result_summary or {}, watch.get("schedule_hours", 168))
        except Exception as exc:
            logger.warning("Manual watch run failed for %s: %s", watch_id, exc)

    background_tasks.add_task(_run)
    return {"status": "started", "watch_id": watch_id, "query": watch["query"]}


# ---------------------------------------------------------------------------
# Deep Research endpoints
# ---------------------------------------------------------------------------

@app.post("/api/deepresearch")
async def start_deep_research(body: StartDeepResearchRequest, background_tasks: BackgroundTasks) -> dict:
    session = await deep_store.create_session(body.input, body.depth)
    background_tasks.add_task(run_deep_research,
                               session_id=session.session_id, user_input=body.input,
                               depth=body.depth, num_researchers=body.num_researchers)
    return {"session_id": session.session_id}

@app.get("/api/deepresearch/{session_id}", response_model=DeepResearchSession)
async def get_deep_session(session_id: str) -> DeepResearchSession:
    s = await deep_store.get_or_load_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Deep research session not found.")
    return s

@app.get("/api/deepresearch/{session_id}/stream")
async def stream_deep_session(session_id: str) -> EventSourceResponse:
    return await _generic_stream(session_id, deep_store)

@app.get("/api/deepresearches")
async def list_deep_sessions(limit: int = 20) -> list[dict]:
    return await deep_store.list_sessions(limit=min(limit, 100))


# ---------------------------------------------------------------------------
# AutoResearch endpoints
# ---------------------------------------------------------------------------

class StartAutoResearchRequest(BaseModel):
    input: str
    max_iterations: int = 4

@app.post("/api/autoresearch")
async def start_auto_research(body: StartAutoResearchRequest, background_tasks: BackgroundTasks) -> dict:
    session = await auto_store.create_session(body.input)
    background_tasks.add_task(run_auto_research,
                               session_id=session.session_id, user_input=body.input,
                               max_iterations=min(body.max_iterations, 6))
    return {"session_id": session.session_id}

@app.get("/api/autoresearch/{session_id}", response_model=ResearchSession)
async def get_auto_session(session_id: str) -> ResearchSession:
    s = await auto_store.get_or_load_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="AutoResearch session not found.")
    return s

@app.get("/api/autoresearch/{session_id}/stream")
async def stream_auto_session(session_id: str) -> EventSourceResponse:
    return await _generic_stream(session_id, auto_store)

@app.get("/api/autoresearches")
async def list_auto_sessions(limit: int = 20) -> list[dict]:
    return await auto_store.list_sessions(limit=min(limit, 100))


# ---------------------------------------------------------------------------
# Lit review endpoints
# ---------------------------------------------------------------------------

class StartLitRequest(BaseModel):
    input: str
    depth: str = "deep"

@app.post("/api/lit")
async def start_lit_review(body: StartLitRequest, background_tasks: BackgroundTasks) -> dict:
    session = await lit_store.create_session(body.input)
    background_tasks.add_task(run_lit_review,
                               session_id=session.session_id, user_input=body.input, depth=body.depth)
    return {"session_id": session.session_id}

@app.get("/api/lit/{session_id}", response_model=ResearchSession)
async def get_lit_session(session_id: str) -> ResearchSession:
    s = await lit_store.get_or_load_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Lit review session not found.")
    return s

@app.get("/api/lit/{session_id}/stream")
async def stream_lit_session(session_id: str) -> EventSourceResponse:
    return await _generic_stream(session_id, lit_store)

@app.get("/api/lits")
async def list_lit_sessions(limit: int = 20) -> list[dict]:
    return await lit_store.list_sessions(limit=min(limit, 100))


# ---------------------------------------------------------------------------
# Compare endpoint (synchronous — returns result directly)
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    items: list[str]
    context: str = ""

@app.post("/api/compare")
async def compare_items(body: CompareRequest) -> dict:
    if len(body.items) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 items to compare.")
    if len(body.items) > 8:
        raise HTTPException(status_code=400, detail="Max 8 items per comparison.")
    return await run_compare(body.items, body.context)


# ---------------------------------------------------------------------------
# Draft endpoint (synchronous — needs an existing session result)
# ---------------------------------------------------------------------------

class DraftRequest(BaseModel):
    session_id: str
    format: str = "brief"   # brief | paper | blog
    title: str = ""

@app.post("/api/draft")
async def create_draft(body: DraftRequest) -> dict:
    valid_formats = {"brief", "paper", "blog"}
    if body.format not in valid_formats:
        raise HTTPException(status_code=400, detail=f"format must be one of {valid_formats}")
    # Try all session stores
    result_dict = None
    for store in [session_store, auto_store, lit_store]:
        s = await store.get_or_load_session(body.session_id)
        if s and s.result:
            result_dict = s.result.model_dump()
            break
    # Deep research: use synthesis sub-result
    if result_dict is None:
        deep_s = await deep_store.get_or_load_session(body.session_id)
        if deep_s and deep_s.result and deep_s.result.synthesis:
            result_dict = deep_s.result.synthesis.model_dump()
    if result_dict is None:
        raise HTTPException(status_code=404, detail="Session not found or has no result yet.")
    draft = await run_draft(result_dict, format=body.format, title=body.title)
    return draft


# ---------------------------------------------------------------------------
# Artifacts / outputs endpoints
# ---------------------------------------------------------------------------

@app.get("/api/outputs")
async def list_all_outputs() -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, list_all_sessions_with_artifacts)

@app.get("/api/outputs/{session_id}")
async def list_session_outputs(session_id: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    artifacts = await loop.run_in_executor(None, list_artifacts, session_id)
    if not artifacts:
        raise HTTPException(status_code=404, detail="No artifacts found for this session.")
    return artifacts

@app.get("/api/outputs/{session_id}/{filename}")
async def download_artifact(session_id: str, filename: str) -> Response:
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(None, read_artifact, session_id, filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    suffix = filename.rsplit(".", 1)[-1].lower()
    media_types = {"md": "text/markdown", "json": "application/json",
                   "bib": "text/plain", "txt": "text/plain"}
    media_type = media_types.get(suffix, "application/octet-stream")
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------------------------------------------------------------------------
# PDF inline proxy — serves PDFs from the LaTeX compiler service with
# Content-Disposition: inline so browsers display them instead of downloading.
# ---------------------------------------------------------------------------

@app.get("/api/pdf-proxy")
async def pdf_proxy(src: str = Query(..., description="Full URL of the PDF on the LaTeX service")):
    """Fetch a PDF from the latex compiler service and return it inline."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(src)
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch PDF: {exc}")

    filename = src.rsplit("/", 1)[-1] or "document.pdf"
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([resp.content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------------------
# Knowledge / papers_memory search endpoint
# ---------------------------------------------------------------------------

@app.get("/api/knowledge/search")
async def search_knowledge(q: str, limit: int = 20) -> list:
    if not q.strip():
        raise HTTPException(status_code=400, detail="q parameter required.")
    return await db.search_papers_memory(q.strip(), limit=min(limit, 50))

@app.get("/api/knowledge/stats")
async def knowledge_stats() -> dict:
    total_papers = await db.count_papers_memory()
    # Count distinct sessions across all session types
    total_sessions = await db.count_all_sessions()
    top_tags = await db.get_top_tags(limit=12)
    recent_papers = await db.get_recent_papers(limit=5)
    return {
        "total_papers": total_papers,
        "total_sessions": total_sessions,
        "top_tags": top_tags,
        "recent_papers": recent_papers,
    }


# ---------------------------------------------------------------------------
# Shared SSE stream helper (avoids repeating the generator for every workflow)
# ---------------------------------------------------------------------------

async def _generic_stream(session_id: str, store) -> EventSourceResponse:
    session = await store.get_or_load_session(session_id)
    if session is None:
        async def _err():
            yield {"event": "error", "data": json.dumps({"detail": "Session not found."})}
        return EventSourceResponse(_err())
    if session.status in ("completed", "error"):
        async def _done():
            yield {"event": "complete", "data": session.model_dump_json()}
        return EventSourceResponse(_done())
    queue = store.get_queue(session_id)
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
                done = await store.get_or_load_session(session_id)
                yield {"event": "complete", "data": (done or session).model_dump_json()}
                break
            else:
                yield {"event": "progress", "data": json.dumps(event)}
    return EventSourceResponse(_events())


@app.get("/api/research/{session_id}/graph")
async def get_graph(session_id: str) -> dict:
    # Check all session stores — lit/auto/deep sessions also have a graph view
    result = None
    for store in [session_store, auto_store, lit_store]:
        s = await store.get_or_load_session(session_id)
        if s and s.result:
            result = s.result
            break
    if result is None:
        deep_s = await deep_store.get_or_load_session(session_id)
        if deep_s and deep_s.result and deep_s.result.synthesis:
            result = deep_s.result.synthesis
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    if not graph_store.is_available():
        papers = [p.model_dump() for p in result.papers]
        edges = [{"source": l.source, "target": l.target, "type": "CITES"}
                 for l in result.citation_links]
        return {"nodes": papers, "edges": edges, "communities": 0, "memgraph": False}

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


# ---------------------------------------------------------------------------
# Docs endpoints (PDF / document Q&A)
# ---------------------------------------------------------------------------

_ALLOWED_DOC_EXTENSIONS = {".pdf", ".txt", ".md", ".tex"}
_MAX_DOC_SIZE_MB = 50


@app.post("/api/docs/upload", response_model=DocRecord)
async def upload_document(file: UploadFile) -> DocRecord:
    """Upload a PDF or text file — parses, chunks, and embeds it."""
    import os as _os
    ext = _os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_DOC_EXTENSIONS)}",
        )
    data = await file.read()
    if len(data) > _MAX_DOC_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {_MAX_DOC_SIZE_MB} MB limit.")
    try:
        record = await process_upload(file.filename or "document", data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return record


@app.get("/api/docs", response_model=list[DocRecord])
async def list_documents() -> list[DocRecord]:
    """Return all uploaded documents."""
    rows = await db.docs_list_documents()
    return [DocRecord(**r) for r in rows]


@app.delete("/api/docs/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    """Delete a document and all its chunks."""
    deleted = await db.docs_delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": True, "doc_id": doc_id}


@app.post("/api/docs/ask", response_model=DocsQAResult)
async def ask_documents(body: DocsQARequest) -> DocsQAResult:
    """Ask a question — answers grounded in uploaded documents via RAG."""
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty.")
    return await answer_question(body.question, top_k=min(body.top_k, 10))


# ---------------------------------------------------------------------------
# Web Search endpoints (Perplexity-like)
# ---------------------------------------------------------------------------

@app.post("/api/websearch")
async def start_websearch(body: StartWebSearchRequest, background_tasks: BackgroundTasks) -> dict:
    """Start a Perplexity-like web search session."""
    session = await websearch_store.create_session(body.input)
    background_tasks.add_task(
        run_websearch,
        session_id=session.session_id,
        user_input=body.input,
        recency=body.recency,
    )
    return {"session_id": session.session_id}


@app.get("/api/websearch/{session_id}", response_model=WebSearchSession)
async def get_websearch_session(session_id: str) -> WebSearchSession:
    s = await websearch_store.get_or_load_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Web search session not found.")
    return s


@app.get("/api/websearch/{session_id}/stream")
async def stream_websearch_session(session_id: str) -> EventSourceResponse:
    return await _generic_stream(session_id, websearch_store)


@app.get("/api/websearches")
async def list_websearch_sessions(limit: int = 20) -> list[dict]:
    return await websearch_store.list_sessions(limit=min(limit, 100))


# ---------------------------------------------------------------------------
# LaTeX Coach endpoints
# ---------------------------------------------------------------------------

_MAX_LATEX_ZIP_MB = 50


@app.post("/api/latexcoach/scan")
async def scan_latex_zip(latex_zip: UploadFile) -> dict:
    """
    Escanea un .zip y devuelve los archivos .tex candidatos a ser el archivo principal
    (los que contienen \\documentclass).
    """
    import zipfile as _zipfile, io as _io, re as _re

    zip_bytes = await latex_zip.read()
    candidates: list[dict] = []
    total_tex = 0

    try:
        with _zipfile.ZipFile(_io.BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if not info.filename.endswith(".tex"):
                    continue
                total_tex += 1
                try:
                    content = z.read(info.filename).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if r"\documentclass" not in content:
                    continue
                section_count = len(_re.findall(r"\\section(?:\*)?", content))
                candidates.append({
                    "filename": info.filename,
                    "section_count": section_count,
                    "size_kb": round(info.file_size / 1024, 1),
                })
    except _zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Archivo zip inválido o corrupto.")

    # Ordenar: más secciones primero, luego por nombre
    candidates.sort(key=lambda c: (-c["section_count"], c["filename"]))

    return {"candidates": candidates, "total_tex_files": total_tex}


@app.post("/api/latexcoach")
async def start_latex_coach(
    background_tasks: BackgroundTasks,
    latex_zip: UploadFile,
    main_tex: str = Form(default=""),
) -> dict:
    """
    Sube un .zip con un proyecto LaTeX.
    Opcionalmente acepta main_tex para especificar el archivo raíz
    cuando el zip tiene varios .tex con \\documentclass.
    """
    if not (latex_zip.filename or "").endswith(".zip"):
        raise HTTPException(status_code=400, detail="Se requiere un archivo .zip con el proyecto LaTeX.")

    zip_bytes = await latex_zip.read()
    if len(zip_bytes) > _MAX_LATEX_ZIP_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"El zip supera el límite de {_MAX_LATEX_ZIP_MB} MB.")

    session = await latex_store.create_session(latex_zip.filename or "project.zip")

    background_tasks.add_task(
        run_latex_coach,
        session_id=session.session_id,
        zip_bytes=zip_bytes,
        filename=latex_zip.filename or "project.zip",
        main_tex=main_tex.strip(),
    )

    return {"session_id": session.session_id, "filename": session.filename}


@app.get("/api/latexcoach/{session_id}", response_model=LatexCoachSession)
async def get_latex_coach_session(session_id: str) -> LatexCoachSession:
    session = await latex_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"LaTeX Coach session '{session_id}' not found.")
    return session


@app.get("/api/latexcoach/{session_id}/debug")
async def debug_latex_coach_session(session_id: str) -> dict:
    """Devuelve estado completo de la sesión incluyendo logs y errores para diagnóstico."""
    session = await latex_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "session_id": session_id,
        "status": session.status,
        "error": session.error,
        "progress_pct": session.progress.percentage,
        "logs": [{"ts": l.timestamp, "level": l.level, "msg": l.message} for l in session.progress.logs],
        "sections_count": len(session.sections),
        "sections_errors": [
            {"title": s.title, "issues": s.issues}
            for s in session.sections
            if any("failed" in (i or "").lower() or "error" in (i or "").lower() for i in s.issues)
        ],
        "model": __import__("os").getenv("LLM_MODEL", "gpt-5.4-nano"),
    }


@app.get("/api/latexcoach/{session_id}/stream")
async def stream_latex_coach_session(session_id: str) -> EventSourceResponse:
    return await _generic_stream(session_id, latex_store)


@app.get("/api/latexcoaches")
async def list_latex_coach_sessions(limit: int = 20) -> list[dict]:
    return await latex_store.list_sessions(limit=min(limit, 100))


@app.post("/api/latexcoach/{session_id}/annotated")
async def request_annotated_pdf(session_id: str) -> dict:
    """
    (Re)genera el PDF anotado con sugerencias en rojo para una sesión completada.
    Requiere que el zip original esté guardado en disco.
    """
    session = await latex_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.status != "completed":
        raise HTTPException(status_code=400, detail="Session not yet completed.")

    zip_path = latex_store.get_zip_path(session_id)
    if zip_path is None:
        raise HTTPException(
            status_code=410,
            detail="Original zip not available on disk. Session may have been created before this feature.",
        )

    pdf_url = await generate_annotated_pdf(session_id)
    if pdf_url is None:
        raise HTTPException(
            status_code=500,
            detail="Annotated PDF generation failed. Check that the LaTeX compiler service is running.",
        )
    return {"annotated_pdf_url": pdf_url}


class PatchSelection(BaseModel):
    section_idx: int
    suggestion_idx: int

class PatchRequest(BaseModel):
    suggestions: list[PatchSelection]

@app.post("/api/latexcoach/{session_id}/patch")
async def patch_latex_suggestions(session_id: str, req: PatchRequest):
    """
    Apply selected suggestions to the original zip and return a downloadable patched zip.
    Each suggestion is identified by (section_idx, suggestion_idx).
    """
    from fastapi.responses import StreamingResponse
    import io, zipfile

    session = await latex_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    zip_bytes = latex_store.get_zip_bytes(session_id)
    if zip_bytes is None:
        raise HTTPException(status_code=410, detail="Original zip not available on disk.")

    # Extract all tex files
    from .agent.latex_coach import _extract_tex_files
    tex_files = _extract_tex_files(zip_bytes)
    modified: dict[str, str] = {k: v for k, v in tex_files.items()}

    applied = 0
    skipped = 0
    for sel in req.suggestions:
        try:
            sec = session.sections[sel.section_idx]
            sug = sec.suggestions[sel.suggestion_idx]
        except IndexError:
            skipped += 1
            continue

        if not sug.target_text or not sug.replacement:
            skipped += 1
            continue

        fname = sug.file
        if fname not in modified:
            skipped += 1
            continue

        target = sug.target_text.strip()
        if target and target in modified[fname]:
            modified[fname] = modified[fname].replace(target, sug.replacement.strip(), 1)
            applied += 1
        else:
            skipped += 1

    logger.info("[Patch] session=%s applied=%d skipped=%d", session_id, applied, skipped)

    # Reconstruct zip
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z_in:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.infolist():
                if item.filename in modified:
                    z_out.writestr(item, modified[item.filename].encode("utf-8"))
                else:
                    z_out.writestr(item, z_in.read(item.filename))

    buf.seek(0)
    base = session.filename.rsplit(".", 1)[0] if session.filename else "project"
    download_name = f"{base}_patched.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


def _brace_delta(text: str) -> int:
    """Net brace count: positive = more { than }, negative = more } than {."""
    count = 0
    for ch in text:
        if ch == '{':
            count += 1
        elif ch == '}':
            count -= 1
    return count

def _has_early_close(text: str) -> bool:
    """Return True if a } appears before its matching { (would cause 'Too many }'s)."""
    depth = 0
    for ch in text:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                return True
    return False

# LaTeX structural commands that break the document if injected in wrong context
_STRUCTURAL_CMDS = (r"\item", r"\begin{", r"\end{", r"\section", r"\subsection",
                    r"\chapter", r"\paragraph", r"\subparagraph")

def _safe_to_apply(target: str, replacement: str) -> bool:
    """Return True if replacing target with replacement is structurally safe."""
    # Both must have the same net brace delta — they rely on surrounding context equally
    if _brace_delta(target) != _brace_delta(replacement):
        return False
    # Replacement must not have a } before its matching {
    if _has_early_close(replacement):
        return False
    # Skip structural commands that break list/section context
    if any(cmd in replacement for cmd in _STRUCTURAL_CMDS):
        return False
    return True


def _build_patched_zip(zip_bytes: bytes, session, req_suggestions: list) -> bytes:
    """Helper: apply patch selections and return new zip bytes."""
    import io as _io, zipfile as _zf
    from .agent.latex_coach import _extract_tex_files
    tex_files = _extract_tex_files(zip_bytes)
    modified: dict[str, str] = {k: v for k, v in tex_files.items()}
    for sel in req_suggestions:
        try:
            sec = session.sections[sel.section_idx]
            sug = sec.suggestions[sel.suggestion_idx]
        except IndexError:
            continue
        if not sug.target_text or not sug.replacement:
            continue
        target = sug.target_text.strip()
        replacement = sug.replacement.strip()
        # Skip replacements that would break LaTeX structure
        if not _safe_to_apply(target, replacement):
            logger.info("[Patch] skipping unsafe replacement for %s:%d — brace delta mismatch or structural cmd",
                        sug.file, sug.start_line)
            continue
        fname = sug.file
        if fname in modified and target and target in modified[fname]:
            modified[fname] = modified[fname].replace(target, replacement, 1)
    buf = _io.BytesIO()
    with _zf.ZipFile(_io.BytesIO(zip_bytes)) as z_in:
        with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as z_out:
            for item in z_in.infolist():
                if item.filename in modified:
                    z_out.writestr(item, modified[item.filename].encode("utf-8"))
                else:
                    z_out.writestr(item, z_in.read(item.filename))
    return buf.getvalue()


@app.post("/api/latexcoach/{session_id}/patch-preview")
async def patch_preview(session_id: str, req: PatchRequest) -> dict:
    """
    Apply selected suggestions, compile the patched zip, and return the PDF URL.
    Stores the result as patched_pdf_url in the session.
    """
    from .agent.latex_coach import _compile_zip
    session = await latex_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    zip_bytes = latex_store.get_zip_bytes(session_id)
    if zip_bytes is None:
        raise HTTPException(status_code=410, detail="Original zip not available on disk.")

    patched_zip = _build_patched_zip(zip_bytes, session, req.suggestions)
    result = await _compile_zip(patched_zip, session.filename or "patched.zip", lenient=True)
    logger.info("[PatchPreview] success=%s pdf_url=%s errors=%s", result.success, result.pdf_url, result.errors[:5])

    if result.pdf_url:
        session.patched_pdf_url = result.pdf_url
        await latex_store.update_session(session)
    return {
        "patched_pdf_url": result.pdf_url,
        "success": result.success,
        "errors": result.errors[:10],
    }


@app.get("/api/latexcoach/{session_id}/raw")
async def get_raw_tex(session_id: str, file: str = Query(default="")) -> dict:
    """
    Return the raw .tex source files from the original zip.
    If `file` is specified, return only that file's content.
    """
    from .agent.latex_coach import _extract_tex_files, _find_main_key
    zip_bytes = latex_store.get_zip_bytes(session_id)
    if zip_bytes is None:
        raise HTTPException(status_code=410, detail="Original zip not available on disk.")
    tex_files = _extract_tex_files(zip_bytes)
    if not tex_files:
        raise HTTPException(status_code=404, detail="No .tex files found in zip.")
    main_key = _find_main_key(tex_files)
    if file:
        content = tex_files.get(file)
        if content is None:
            raise HTTPException(status_code=404, detail=f"File '{file}' not found in zip.")
        return {"file": file, "content": content, "files": list(tex_files.keys()), "main": main_key}
    # Return all files index + main file content
    return {"file": main_key, "content": tex_files.get(main_key, ""), "files": list(tex_files.keys()), "main": main_key}


class CompileEditRequest(BaseModel):
    file: str
    content: str

@app.post("/api/latexcoach/{session_id}/compile-edit")
async def compile_edit(session_id: str, req: CompileEditRequest) -> dict:
    """
    Replace a single .tex file in the original zip with edited content, compile, return PDF URL.
    Powers the inline editor (Raw tab) — like Overleaf's compile button.
    """
    import io as _io, zipfile as _zf
    from .agent.latex_coach import _compile_zip

    zip_bytes = latex_store.get_zip_bytes(session_id)
    if zip_bytes is None:
        raise HTTPException(status_code=410, detail="Original zip not available on disk.")

    # Replace only the edited file; keep everything else intact
    buf = _io.BytesIO()
    with _zf.ZipFile(_io.BytesIO(zip_bytes)) as z_in:
        with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as z_out:
            replaced = False
            for item in z_in.infolist():
                if item.filename == req.file:
                    z_out.writestr(item, req.content.encode("utf-8"))
                    replaced = True
                else:
                    z_out.writestr(item, z_in.read(item.filename))
            if not replaced:
                # File wasn't in zip — add it at root
                z_out.writestr(req.file, req.content.encode("utf-8"))

    result = await _compile_zip(buf.getvalue(), req.file, lenient=True)
    if not result.pdf_url:
        raise HTTPException(
            status_code=500,
            detail=f"Compilation failed: {'; '.join(result.errors[:5])}",
        )
    return {"pdf_url": result.pdf_url, "errors": result.errors[:10], "warnings": result.warnings[:10]}


@app.post("/api/latexcoach/{session_id}/reanalyze")
async def reanalyze_latex_coach(
    session_id: str,
    background_tasks: BackgroundTasks,
    main_tex: str = Query(default=""),
) -> dict:
    """
    Re-ejecuta el análisis completo de una sesión existente usando el zip guardado en disco.
    Útil cuando el análisis previo falló o el código fue actualizado.
    """
    zip_bytes = latex_store.get_zip_bytes(session_id)
    if zip_bytes is None:
        raise HTTPException(
            status_code=410,
            detail="Original zip not available on disk. Please upload the project again.",
        )

    session = await latex_store.reset_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    background_tasks.add_task(
        run_latex_coach,
        session_id=session_id,
        zip_bytes=zip_bytes,
        filename=session.filename,
        main_tex=main_tex.strip(),
    )
    return {"session_id": session_id, "status": "restarted"}


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


@app.get("/api/research/{session_id}/export/pdf")
async def export_research_pdf(session_id: str) -> Response:
    """Generate and download a formatted PDF of the research results."""
    session = await session_store.get_or_load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if session.status != "completed" or session.result is None:
        raise HTTPException(status_code=400, detail="Research session not yet completed.")

    import asyncio
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        generate_research_pdf,
        session_id,
        session.input,
        session.result,
    )

    slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in session.input)[:40].strip().replace(" ", "-").lower()
    filename = f"research-{slug or session_id[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
