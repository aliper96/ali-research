from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..models.schemas import LogEntry, Progress, ResearchSession
from . import db


class SessionStore:
    """
    Write-through session store: primary data lives in memory for speed,
    every create/status-change is persisted to PostgreSQL (if available).

    Session lifecycle
    -----------------
    1. ``create_session``       — allocates session + queue, writes to DB.
    2. ``add_log``              — appends log + pushes SSE event (no DB write,
                                  logs are transient).
    3. ``set_progress``         — updates % + pushes SSE event (no DB write).
    4. ``update_session``       — persists full session to DB (called on
                                  status change / result set).
    5. ``notify_complete``      — pushes completion sentinel to SSE queue.
    6. ``get_or_load_session``  — memory first, DB fallback (for reloads after
                                  restart).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ResearchSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    async def create_session(self, input_text: str) -> ResearchSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = ResearchSession(
            session_id=session_id,
            status="running",
            input=input_text,
            created_at=now,
            progress=Progress(percentage=0, logs=[]),
        )
        self._sessions[session_id] = session
        self._queues[session_id] = asyncio.Queue()
        await db.save_session(session.model_dump())
        return session

    def get_session(self, session_id: str) -> Optional[ResearchSession]:
        """Sync look-up — memory only. Use get_or_load_session in routes."""
        return self._sessions.get(session_id)

    async def get_or_load_session(self, session_id: str) -> Optional[ResearchSession]:
        """Memory first; falls back to PostgreSQL for sessions after restart."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        data = await db.load_session(session_id)
        if data is None:
            return None
        session = ResearchSession.model_validate(data)
        self._sessions[session_id] = session          # cache in memory
        return session

    async def update_session(self, session: ResearchSession) -> None:
        """Update memory + persist to DB (call on status/result changes)."""
        self._sessions[session.session_id] = session
        await db.save_session(session.model_dump())

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    async def add_log(
        self,
        session_id: str,
        message: str,
        level: str = "info",
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return

        now = datetime.now(timezone.utc).isoformat()
        entry = LogEntry(timestamp=now, message=message, level=level)  # type: ignore[arg-type]
        session.progress.logs.append(entry)
        self._sessions[session_id] = session

        await self.notify_log(session_id, entry)

    async def set_progress(self, session_id: str, percentage: int) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return

        session.progress.percentage = max(0, min(100, percentage))
        self._sessions[session_id] = session

        queue = self._queues.get(session_id)
        if queue is not None:
            await queue.put(
                {
                    "type": "progress",
                    "percentage": session.progress.percentage,
                }
            )
            await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # SSE queue management
    # ------------------------------------------------------------------

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(session_id)

    def create_queue(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[session_id] = q
        return q

    async def notify_log(self, session_id: str, log_entry: LogEntry) -> None:
        session = self._sessions.get(session_id)
        queue = self._queues.get(session_id)
        if session is None or queue is None:
            return

        await queue.put(
            {
                "type": "log",
                "log": log_entry.model_dump(),
                "percentage": session.progress.percentage,
            }
        )
        await asyncio.sleep(0)

    async def notify_complete(self, session_id: str) -> None:
        queue = self._queues.get(session_id)
        if queue is not None:
            await queue.put({"type": "complete"})
            await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        """Recent sessions from DB, supplemented with any in-memory ones."""
        db_sessions = await db.list_sessions(limit)
        # If DB is unavailable, return in-memory sessions
        if not db_sessions:
            return [
                {
                    "session_id": s.session_id,
                    "input": s.input,
                    "status": s.status,
                    "created_at": s.created_at,
                    "has_result": s.result is not None,
                }
                for s in sorted(
                    self._sessions.values(),
                    key=lambda x: x.created_at,
                    reverse=True,
                )[:limit]
            ]
        return db_sessions


# Module-level singleton used throughout the application.
session_store = SessionStore()
