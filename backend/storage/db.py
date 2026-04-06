"""
Async PostgreSQL persistence layer (asyncpg).

Degrades gracefully: if asyncpg is not installed or DATABASE_URL is not set
the application runs fine with in-memory-only sessions.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
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
                CREATE TABLE IF NOT EXISTS review_sessions (
                    session_id   TEXT PRIMARY KEY,
                    paper_title  TEXT        NOT NULL DEFAULT '',
                    status       TEXT        NOT NULL DEFAULT 'running',
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    data         JSONB       NOT NULL
                )
                """
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
