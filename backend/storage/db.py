"""
Async PostgreSQL persistence layer (asyncpg).

Degrades gracefully: if asyncpg is not installed or DATABASE_URL is not set
the application runs fine with in-memory-only sessions.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import asyncpg
    _ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None  # type: ignore
    _ASYNCPG_AVAILABLE = False

_pool: Any = None


async def init_pool() -> None:
    """Initialise the connection pool and create all tables."""
    global _pool
    if not _ASYNCPG_AVAILABLE:
        logger.info("asyncpg not installed — sessions will be in-memory only")
        return
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.info("DATABASE_URL not set — sessions will be in-memory only")
        return
    try:
        _pool = await asyncpg.create_pool(
            db_url, min_size=1, max_size=5, command_timeout=10
        )
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id  TEXT PRIMARY KEY,
                    input       TEXT        NOT NULL,
                    status      TEXT        NOT NULL DEFAULT 'running',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    data        JSONB       NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_sessions (
                    session_id  TEXT PRIMARY KEY,
                    input       TEXT        NOT NULL,
                    status      TEXT        NOT NULL DEFAULT 'running',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    data        JSONB       NOT NULL
                )
                """
            )
            await conn.execute(
                "UPDATE audit_sessions SET status = 'error' WHERE status = 'running'"
            )
            # Generic session table shared by deep_research, autoresearch, lit, compare, draft
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generic_sessions (
                    table_name  TEXT        NOT NULL,
                    session_id  TEXT        NOT NULL,
                    input       TEXT        NOT NULL,
                    status      TEXT        NOT NULL DEFAULT 'running',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    data        JSONB       NOT NULL,
                    PRIMARY KEY (table_name, session_id)
                )
                """
            )
            await conn.execute(
                "UPDATE generic_sessions SET status = 'error' WHERE status = 'running'"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_sessions (
                    session_id   TEXT PRIMARY KEY,
                    paper_title  TEXT        NOT NULL DEFAULT '',
                    status       TEXT        NOT NULL DEFAULT 'running',
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    data         JSONB       NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS papers_memory (
                    paper_id       TEXT PRIMARY KEY,
                    title          TEXT NOT NULL DEFAULT '',
                    authors        JSONB NOT NULL DEFAULT '[]',
                    year           INTEGER,
                    abstract       TEXT DEFAULT '',
                    url            TEXT DEFAULT '',
                    arxiv_id       TEXT,
                    doi            TEXT,
                    venue          TEXT,
                    tags           JSONB NOT NULL DEFAULT '[]',
                    citation_count INTEGER NOT NULL DEFAULT 0,
                    first_seen     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    session_ids    JSONB NOT NULL DEFAULT '[]'
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS papers_memory_title_idx ON papers_memory USING gin(to_tsvector('english', title || ' ' || COALESCE(abstract, '')))"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watches (
                    watch_id       TEXT PRIMARY KEY,
                    query          TEXT        NOT NULL,
                    depth          TEXT        NOT NULL DEFAULT 'quick',
                    schedule_hours INTEGER     NOT NULL DEFAULT 168,
                    active         BOOLEAN     NOT NULL DEFAULT TRUE,
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_run_at    TIMESTAMPTZ,
                    next_run_at    TIMESTAMPTZ,
                    last_result    JSONB
                )
                """
            )
            # Documents (PDF/text Q&A)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS docs_documents (
                    doc_id      TEXT PRIMARY KEY,
                    title       TEXT        NOT NULL DEFAULT '',
                    filename    TEXT        NOT NULL DEFAULT '',
                    page_count  INTEGER     NOT NULL DEFAULT 0,
                    chunk_count INTEGER     NOT NULL DEFAULT 0,
                    size_bytes  INTEGER     NOT NULL DEFAULT 0,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS docs_chunks (
                    chunk_id    SERIAL PRIMARY KEY,
                    doc_id      TEXT        NOT NULL REFERENCES docs_documents(doc_id) ON DELETE CASCADE,
                    chunk_index INTEGER     NOT NULL,
                    content     TEXT        NOT NULL,
                    embedding   JSONB       NOT NULL DEFAULT '[]'
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS docs_chunks_doc_idx ON docs_chunks(doc_id)"
            )
            # Any session still marked 'running' from a previous process is dead.
            affected = await conn.execute(
                "UPDATE sessions SET status = 'error' WHERE status = 'running'"
            )
            await conn.execute(
                "UPDATE review_sessions SET status = 'error' WHERE status = 'running'"
            )
            if affected != "UPDATE 0":
                logger.info("Marked interrupted running sessions as error: %s", affected)
        logger.info("PostgreSQL: connected — sessions + review_sessions tables ready")
    except Exception as exc:
        logger.warning(
            "PostgreSQL unavailable (%s) — falling back to in-memory only", exc
        )
        _pool = None


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def is_available() -> bool:
    return _pool is not None


def _parse_dt(value: Any) -> datetime:
    """Accept either a datetime object or an ISO-8601 string."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


async def save_session(session_data: dict) -> None:
    """Upsert a full session record (called on create and on status change)."""
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (session_id, input, status, created_at, data)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (session_id) DO UPDATE
                    SET status = EXCLUDED.status,
                        data   = EXCLUDED.data
                """,
                session_data["session_id"],
                session_data["input"],
                session_data["status"],
                _parse_dt(session_data["created_at"]),
                json.dumps(session_data),
            )
    except Exception as exc:
        logger.warning("DB save_session failed (non-fatal): %s", exc)


async def load_session(session_id: str) -> Optional[dict]:
    """Fetch a single session by ID. Returns None if not found."""
    if _pool is None:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM sessions WHERE session_id = $1", session_id
            )
        if row is None:
            return None
        return json.loads(row["data"])
    except Exception as exc:
        logger.warning("DB load_session failed (non-fatal): %s", exc)
        return None


# ---------------------------------------------------------------------------
# Review sessions
# ---------------------------------------------------------------------------

async def save_review_session(session_data: dict) -> None:
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO review_sessions (session_id, paper_title, status, created_at, data)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (session_id) DO UPDATE
                    SET status      = EXCLUDED.status,
                        paper_title = EXCLUDED.paper_title,
                        data        = EXCLUDED.data
                """,
                session_data["session_id"],
                session_data.get("paper_title", ""),
                session_data["status"],
                _parse_dt(session_data["created_at"]),
                json.dumps(session_data),
            )
    except Exception as exc:
        logger.warning("DB save_review_session failed (non-fatal): %s", exc)


async def load_review_session(session_id: str) -> Optional[dict]:
    if _pool is None:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM review_sessions WHERE session_id = $1", session_id
            )
        return json.loads(row["data"]) if row else None
    except Exception as exc:
        logger.warning("DB load_review_session failed (non-fatal): %s", exc)
        return None


async def list_review_sessions(limit: int = 50) -> list[dict]:
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT session_id, paper_title, status, created_at,
                       data->'editor_report'->>'final_recommendation' AS recommendation
                FROM   review_sessions
                ORDER  BY created_at DESC
                LIMIT  $1
                """,
                limit,
            )
        return [
            {
                "session_id": r["session_id"],
                "paper_title": r["paper_title"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
                "recommendation": r["recommendation"],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("DB list_review_sessions failed (non-fatal): %s", exc)
        return []


async def save_generic_session(table_name: str, session_id: str, input_text: str,
                               status: str, created_at: Any, data: dict) -> None:
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO generic_sessions (table_name, session_id, input, status, created_at, data)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (table_name, session_id) DO UPDATE
                    SET status = EXCLUDED.status, data = EXCLUDED.data
                """,
                table_name, session_id, input_text, status, _parse_dt(created_at), json.dumps(data),
            )
    except Exception as exc:
        logger.warning("DB save_generic_session(%s) failed: %s", table_name, exc)


async def load_generic_session(table_name: str, session_id: str) -> Optional[dict]:
    if _pool is None:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM generic_sessions WHERE table_name=$1 AND session_id=$2",
                table_name, session_id,
            )
        return json.loads(row["data"]) if row else None
    except Exception as exc:
        logger.warning("DB load_generic_session(%s) failed: %s", table_name, exc)
        return None


async def list_generic_sessions(table_name: str, limit: int = 20) -> list[dict]:
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT session_id, input, status, created_at
                FROM   generic_sessions
                WHERE  table_name = $1
                ORDER  BY created_at DESC
                LIMIT  $2
                """,
                table_name, limit,
            )
        return [{"session_id": r["session_id"], "input": r["input"],
                 "status": r["status"], "created_at": r["created_at"].isoformat()}
                for r in rows]
    except Exception as exc:
        logger.warning("DB list_generic_sessions(%s) failed: %s", table_name, exc)
        return []


async def save_audit_session(session_data: dict) -> None:
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_sessions (session_id, input, status, created_at, data)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (session_id) DO UPDATE
                    SET status = EXCLUDED.status,
                        data   = EXCLUDED.data
                """,
                session_data["session_id"],
                session_data["input"],
                session_data["status"],
                _parse_dt(session_data["created_at"]),
                json.dumps(session_data),
            )
    except Exception as exc:
        logger.warning("DB save_audit_session failed (non-fatal): %s", exc)


async def load_audit_session(session_id: str) -> Optional[dict]:
    if _pool is None:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("SELECT data FROM audit_sessions WHERE session_id = $1", session_id)
        return json.loads(row["data"]) if row else None
    except Exception as exc:
        logger.warning("DB load_audit_session failed (non-fatal): %s", exc)
        return None


async def list_audit_sessions(limit: int = 20) -> list[dict]:
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT session_id, input, status, created_at,
                       data->'result'->>'verdict' AS verdict,
                       data->'result'->>'paper_title' AS paper_title
                FROM   audit_sessions
                ORDER  BY created_at DESC
                LIMIT  $1
                """,
                limit,
            )
        return [
            {
                "session_id":  r["session_id"],
                "input":       r["input"],
                "status":      r["status"],
                "created_at":  r["created_at"].isoformat(),
                "verdict":     r["verdict"],
                "paper_title": r["paper_title"],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("DB list_audit_sessions failed (non-fatal): %s", exc)
        return []


async def save_papers_memory(papers: list[dict], session_id: str) -> None:
    """Upsert papers into the cross-session memory table."""
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            for p in papers:
                paper_id = (
                    str(p.get("id") or "")
                    or str(p.get("arxiv_id") or "")
                    or str(p.get("doi") or "")
                )
                if not paper_id:
                    continue
                await conn.execute(
                    """
                    INSERT INTO papers_memory
                        (paper_id, title, authors, year, abstract, url,
                         arxiv_id, doi, venue, tags, citation_count,
                         last_seen, session_ids)
                    VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,NOW(),
                            jsonb_build_array($12::text))
                    ON CONFLICT (paper_id) DO UPDATE SET
                        title          = EXCLUDED.title,
                        -- prefer non-empty values; fall back to stored value if new one is blank
                        authors        = CASE WHEN EXCLUDED.authors::text <> '[]' THEN EXCLUDED.authors        ELSE papers_memory.authors        END,
                        year           = COALESCE(EXCLUDED.year,     papers_memory.year),
                        abstract       = CASE WHEN EXCLUDED.abstract  <> ''       THEN EXCLUDED.abstract       ELSE papers_memory.abstract       END,
                        url            = CASE WHEN EXCLUDED.url       <> ''       THEN EXCLUDED.url            ELSE papers_memory.url            END,
                        arxiv_id       = COALESCE(EXCLUDED.arxiv_id,  papers_memory.arxiv_id),
                        doi            = COALESCE(EXCLUDED.doi,       papers_memory.doi),
                        venue          = COALESCE(EXCLUDED.venue,     papers_memory.venue),
                        tags           = CASE WHEN EXCLUDED.tags::text <> '[]'    THEN EXCLUDED.tags           ELSE papers_memory.tags           END,
                        citation_count = GREATEST(papers_memory.citation_count, EXCLUDED.citation_count),
                        last_seen      = NOW(),
                        session_ids    = (
                            SELECT jsonb_agg(DISTINCT v)
                            FROM jsonb_array_elements_text(
                                papers_memory.session_ids || EXCLUDED.session_ids
                            ) v
                        )
                    """,
                    paper_id,
                    str(p.get("title") or ""),
                    json.dumps(p.get("authors") or []),
                    p.get("year"),
                    str(p.get("abstract") or ""),
                    str(p.get("url") or ""),
                    p.get("arxiv_id"),
                    p.get("doi"),
                    p.get("venue"),
                    json.dumps(p.get("tags") or []),
                    int(p.get("citation_count") or 0),
                    session_id,
                )
    except Exception as exc:
        logger.warning("DB save_papers_memory failed (non-fatal): %s", exc)


async def search_papers_memory(query: str, limit: int = 10) -> list[dict]:
    """Full-text search over previously seen papers."""
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT paper_id, title, authors, year, abstract, url,
                       arxiv_id, doi, venue, tags, citation_count,
                       first_seen, last_seen, session_ids,
                       ts_rank(
                           to_tsvector('english', title || ' ' || COALESCE(abstract, '')),
                           plainto_tsquery('english', $1)
                       ) AS rank
                FROM   papers_memory
                WHERE  to_tsvector('english', title || ' ' || COALESCE(abstract, ''))
                       @@ plainto_tsquery('english', $1)
                ORDER  BY rank DESC, citation_count DESC
                LIMIT  $2
                """,
                query,
                limit,
            )
        return [
            {
                "paper_id":      r["paper_id"],
                "title":         r["title"],
                "authors":       json.loads(r["authors"]),
                "year":          r["year"],
                "abstract":      r["abstract"],
                "url":           r["url"],
                "arxiv_id":      r["arxiv_id"],
                "doi":           r["doi"],
                "venue":         r["venue"],
                "tags":          json.loads(r["tags"]),
                "citation_count": r["citation_count"],
                "first_seen":    r["first_seen"].isoformat(),
                "last_seen":     r["last_seen"].isoformat(),
                "session_ids":   json.loads(r["session_ids"]),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("DB search_papers_memory failed (non-fatal): %s", exc)
        return []


async def count_papers_memory() -> int:
    if _pool is None:
        return 0
    try:
        async with _pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM papers_memory") or 0
    except Exception:
        return 0


async def count_all_sessions() -> int:
    """Total sessions across all tables."""
    if _pool is None:
        return 0
    try:
        async with _pool.acquire() as conn:
            n_sessions = await conn.fetchval("SELECT COUNT(*) FROM sessions") or 0
            n_generic  = await conn.fetchval("SELECT COUNT(*) FROM generic_sessions") or 0
            n_audit    = await conn.fetchval("SELECT COUNT(*) FROM audit_sessions") or 0
            return int(n_sessions) + int(n_generic) + int(n_audit)
    except Exception:
        return 0


async def get_top_tags(limit: int = 12) -> list[dict]:
    """Return the most frequent tags across all papers in memory."""
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT tag, COUNT(*) AS cnt
                FROM   papers_memory,
                       jsonb_array_elements_text(tags) AS tag
                GROUP  BY tag
                ORDER  BY cnt DESC
                LIMIT  $1
                """,
                limit,
            )
        return [{"tag": r["tag"], "count": r["cnt"]} for r in rows]
    except Exception as exc:
        logger.warning("DB get_top_tags failed: %s", exc)
        return []


async def get_recent_papers(limit: int = 5) -> list[dict]:
    """Return most recently seen papers."""
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT paper_id, title, authors, year, abstract, url,
                       arxiv_id, doi, venue, tags, citation_count, last_seen, session_ids
                FROM   papers_memory
                ORDER  BY last_seen DESC
                LIMIT  $1
                """,
                limit,
            )
        return [
            {
                "arxiv_id":      r["arxiv_id"],
                "title":         r["title"],
                "authors":       json.loads(r["authors"]),
                "year":          r["year"],
                "abstract":      r["abstract"],
                "url":           r["url"],
                "citation_count": r["citation_count"],
                "tags":          json.loads(r["tags"]),
                "session_ids":   json.loads(r["session_ids"]),
                "last_seen":     r["last_seen"].isoformat(),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("DB get_recent_papers failed: %s", exc)
        return []


async def create_watch(watch_id: str, query: str, depth: str, schedule_hours: int) -> dict:
    if _pool is None:
        return {}
    from datetime import timedelta
    try:
        async with _pool.acquire() as conn:
            next_run = datetime.now(timezone.utc) + timedelta(hours=schedule_hours)
            await conn.execute(
                """
                INSERT INTO watches (watch_id, query, depth, schedule_hours, next_run_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                watch_id, query, depth, schedule_hours, next_run,
            )
            return {"watch_id": watch_id, "query": query, "depth": depth,
                    "schedule_hours": schedule_hours, "next_run_at": next_run.isoformat()}
    except Exception as exc:
        logger.warning("DB create_watch failed: %s", exc)
        return {}


async def list_watches() -> list[dict]:
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT watch_id, query, depth, schedule_hours, active, created_at, last_run_at, next_run_at, last_result FROM watches ORDER BY created_at DESC"
            )
        return [
            {
                "watch_id":       r["watch_id"],
                "query":          r["query"],
                "depth":          r["depth"],
                "schedule_hours": r["schedule_hours"],
                "active":         r["active"],
                "created_at":     r["created_at"].isoformat(),
                "last_run_at":    r["last_run_at"].isoformat() if r["last_run_at"] else None,
                "next_run_at":    r["next_run_at"].isoformat() if r["next_run_at"] else None,
                "last_result":    json.loads(r["last_result"]) if r["last_result"] else None,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("DB list_watches failed: %s", exc)
        return []


async def delete_watch(watch_id: str) -> bool:
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute("DELETE FROM watches WHERE watch_id = $1", watch_id)
        return result != "DELETE 0"
    except Exception as exc:
        logger.warning("DB delete_watch failed: %s", exc)
        return False


async def update_watch_result(watch_id: str, result: dict, schedule_hours: int) -> None:
    if _pool is None:
        return
    from datetime import timedelta
    try:
        async with _pool.acquire() as conn:
            next_run = datetime.now(timezone.utc) + timedelta(hours=schedule_hours)
            await conn.execute(
                """
                UPDATE watches
                SET last_run_at = NOW(), next_run_at = $2, last_result = $3::jsonb
                WHERE watch_id = $1
                """,
                watch_id, next_run, json.dumps(result),
            )
    except Exception as exc:
        logger.warning("DB update_watch_result failed: %s", exc)


async def get_due_watches() -> list[dict]:
    """Return active watches whose next_run_at is in the past."""
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT watch_id, query, depth, schedule_hours FROM watches WHERE active = TRUE AND (next_run_at IS NULL OR next_run_at <= NOW())"
            )
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("DB get_due_watches failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Docs (PDF Q&A) helpers
# ---------------------------------------------------------------------------

async def docs_save_document(doc: dict) -> None:
    """Upsert a document record."""
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO docs_documents (doc_id, title, filename, page_count, chunk_count, size_bytes, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (doc_id) DO UPDATE
                    SET title = EXCLUDED.title, chunk_count = EXCLUDED.chunk_count
                """,
                doc["doc_id"], doc["title"], doc["filename"],
                doc["page_count"], doc["chunk_count"], doc["size_bytes"],
                _parse_dt(doc["created_at"]),
            )
    except Exception as exc:
        logger.warning("docs_save_document failed: %s", exc)


async def docs_save_chunks(doc_id: str, chunks: list[dict]) -> None:
    """Insert chunks for a document (clears old ones first)."""
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("DELETE FROM docs_chunks WHERE doc_id = $1", doc_id)
            await conn.executemany(
                "INSERT INTO docs_chunks (doc_id, chunk_index, content, embedding) VALUES ($1, $2, $3, $4::jsonb)",
                [
                    (doc_id, c["chunk_index"], c["content"], json.dumps(c["embedding"]))
                    for c in chunks
                ],
            )
    except Exception as exc:
        logger.warning("docs_save_chunks failed: %s", exc)


async def docs_list_documents() -> list[dict]:
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT doc_id, title, filename, page_count, chunk_count, size_bytes, created_at FROM docs_documents ORDER BY created_at DESC"
            )
        return [
            {
                "doc_id": r["doc_id"], "title": r["title"], "filename": r["filename"],
                "page_count": r["page_count"], "chunk_count": r["chunk_count"],
                "size_bytes": r["size_bytes"], "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("docs_list_documents failed: %s", exc)
        return []


async def docs_delete_document(doc_id: str) -> bool:
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute("DELETE FROM docs_documents WHERE doc_id = $1", doc_id)
        return result != "DELETE 0"
    except Exception as exc:
        logger.warning("docs_delete_document failed: %s", exc)
        return False


async def docs_get_all_chunks() -> list[dict]:
    """Load all chunks with their embeddings for in-Python similarity search."""
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content, c.embedding,
                       d.title AS doc_title
                FROM   docs_chunks c
                JOIN   docs_documents d ON d.doc_id = c.doc_id
                ORDER  BY c.doc_id, c.chunk_index
                """
            )
        return [
            {
                "chunk_id": r["chunk_id"], "doc_id": r["doc_id"],
                "chunk_index": r["chunk_index"], "content": r["content"],
                "embedding": json.loads(r["embedding"]),
                "doc_title": r["doc_title"],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("docs_get_all_chunks failed: %s", exc)
        return []


async def list_sessions(limit: int = 50) -> list[dict]:
    """Return recent sessions (lightweight — no full result blob)."""
    if _pool is None:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT session_id,
                       input,
                       status,
                       created_at,
                       data->>'result' IS NOT NULL AS has_result
                FROM   sessions
                ORDER  BY created_at DESC
                LIMIT  $1
                """,
                limit,
            )
        return [
            {
                "session_id": r["session_id"],
                "input": r["input"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
                "has_result": r["has_result"],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("DB list_sessions failed (non-fatal): %s", exc)
        return []
