"""Session store for literature review (reuses ResearchSession shape)."""
from __future__ import annotations
import asyncio, uuid
from datetime import datetime, timezone
from typing import Optional
from ..models.schemas import LogEntry, Progress, ResearchSession
from . import db

class LitStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ResearchSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    async def create_session(self, input_text: str) -> ResearchSession:
        sid = str(uuid.uuid4())
        s = ResearchSession(session_id=sid, status="running", input=input_text,
                            created_at=datetime.now(timezone.utc).isoformat(),
                            progress=Progress(percentage=0, logs=[]))
        self._sessions[sid] = s
        self._queues[sid] = asyncio.Queue()
        await db.save_generic_session("lit_sessions", sid, input_text, "running", s.created_at, s.model_dump())
        return s

    def get_session(self, sid: str) -> Optional[ResearchSession]:
        return self._sessions.get(sid)

    async def get_or_load_session(self, sid: str) -> Optional[ResearchSession]:
        if sid in self._sessions:
            return self._sessions[sid]
        data = await db.load_generic_session("lit_sessions", sid)
        if data is None:
            return None
        s = ResearchSession.model_validate(data)
        self._sessions[sid] = s
        return s

    async def update_session(self, s: ResearchSession) -> None:
        self._sessions[s.session_id] = s
        await db.save_generic_session("lit_sessions", s.session_id, s.input, s.status, s.created_at, s.model_dump())

    async def add_log(self, sid: str, msg: str, level: str = "info") -> None:
        s = self._sessions.get(sid)
        if s is None:
            return
        entry = LogEntry(timestamp=datetime.now(timezone.utc).isoformat(), message=msg, level=level)  # type: ignore[arg-type]
        s.progress.logs.append(entry)
        q = self._queues.get(sid)
        if q:
            await q.put({"type": "log", "log": entry.model_dump(), "percentage": s.progress.percentage})
            await asyncio.sleep(0)

    async def set_progress(self, sid: str, pct: int) -> None:
        s = self._sessions.get(sid)
        if s is None:
            return
        s.progress.percentage = max(0, min(100, pct))
        q = self._queues.get(sid)
        if q:
            await q.put({"type": "progress", "percentage": s.progress.percentage})
            await asyncio.sleep(0)

    def get_queue(self, sid: str) -> Optional[asyncio.Queue]:
        return self._queues.get(sid)

    async def notify_complete(self, sid: str) -> None:
        q = self._queues.get(sid)
        if q:
            await q.put({"type": "complete"})
            await asyncio.sleep(0)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return await db.list_generic_sessions("lit_sessions", limit)

lit_store = LitStore()
