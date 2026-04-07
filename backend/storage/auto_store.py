"""Session store for autoresearch (reuses generic session + ResearchResult)."""
from __future__ import annotations
import asyncio, uuid
from datetime import datetime, timezone
from typing import Optional
from ..models.schemas import LogEntry, Progress, ResearchResult, ResearchSession
from . import db


class AutoResearchStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ResearchSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    async def create_session(self, input_text: str) -> ResearchSession:
        session_id = str(uuid.uuid4())
        session = ResearchSession(
            session_id=session_id, status="running", input=input_text,
            created_at=datetime.now(timezone.utc).isoformat(),
            progress=Progress(percentage=0, logs=[]),
        )
        self._sessions[session_id] = session
        self._queues[session_id] = asyncio.Queue()
        await db.save_generic_session("auto_research_sessions", session_id, input_text, "running",
                                      session.created_at, session.model_dump())
        return session

    def get_session(self, session_id: str) -> Optional[ResearchSession]:
        return self._sessions.get(session_id)

    async def get_or_load_session(self, session_id: str) -> Optional[ResearchSession]:
        if session_id in self._sessions:
            return self._sessions[session_id]
        data = await db.load_generic_session("auto_research_sessions", session_id)
        if data is None:
            return None
        s = ResearchSession.model_validate(data)
        self._sessions[session_id] = s
        return s

    async def update_session(self, session: ResearchSession) -> None:
        self._sessions[session.session_id] = session
        await db.save_generic_session("auto_research_sessions", session.session_id,
                                      session.input, session.status,
                                      session.created_at, session.model_dump())

    async def add_log(self, session_id: str, message: str, level: str = "info") -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        entry = LogEntry(timestamp=datetime.now(timezone.utc).isoformat(),
                         message=message, level=level)  # type: ignore[arg-type]
        session.progress.logs.append(entry)
        q = self._queues.get(session_id)
        if q:
            await q.put({"type": "log", "log": entry.model_dump(),
                         "percentage": session.progress.percentage})
            await asyncio.sleep(0)

    async def set_progress(self, session_id: str, pct: int) -> None:
        s = self._sessions.get(session_id)
        if s is None:
            return
        s.progress.percentage = max(0, min(100, pct))
        q = self._queues.get(session_id)
        if q:
            await q.put({"type": "progress", "percentage": s.progress.percentage})
            await asyncio.sleep(0)

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(session_id)

    async def notify_complete(self, session_id: str) -> None:
        q = self._queues.get(session_id)
        if q:
            await q.put({"type": "complete"})
            await asyncio.sleep(0)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return await db.list_generic_sessions("auto_research_sessions", limit)


auto_store = AutoResearchStore()
