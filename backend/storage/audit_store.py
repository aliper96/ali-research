"""In-memory + DB store for audit sessions (mirrors session_store pattern)."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..models.audit_schemas import AuditSession
from ..models.schemas import LogEntry, Progress
from . import db


class AuditStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AuditSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    async def create_session(self, input_text: str) -> AuditSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = AuditSession(
            session_id=session_id,
            status="running",
            input=input_text,
            created_at=now,
            progress=Progress(percentage=0, logs=[]),
        )
        self._sessions[session_id] = session
        self._queues[session_id] = asyncio.Queue()
        await self._save(session)
        return session

    def get_session(self, session_id: str) -> Optional[AuditSession]:
        return self._sessions.get(session_id)

    async def get_or_load_session(self, session_id: str) -> Optional[AuditSession]:
        if session_id in self._sessions:
            return self._sessions[session_id]
        data = await db.load_audit_session(session_id)
        if data is None:
            return None
        session = AuditSession.model_validate(data)
        self._sessions[session_id] = session
        return session

    async def update_session(self, session: AuditSession) -> None:
        self._sessions[session.session_id] = session
        await self._save(session)

    async def add_log(self, session_id: str, message: str, level: str = "info") -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            message=message,
            level=level,  # type: ignore[arg-type]
        )
        session.progress.logs.append(entry)
        queue = self._queues.get(session_id)
        if queue:
            await queue.put({"type": "log", "log": entry.model_dump(), "percentage": session.progress.percentage})
            await asyncio.sleep(0)

    async def set_progress(self, session_id: str, percentage: int) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.progress.percentage = max(0, min(100, percentage))
        queue = self._queues.get(session_id)
        if queue:
            await queue.put({"type": "progress", "percentage": session.progress.percentage})
            await asyncio.sleep(0)

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(session_id)

    async def notify_complete(self, session_id: str) -> None:
        queue = self._queues.get(session_id)
        if queue:
            await queue.put({"type": "complete"})
            await asyncio.sleep(0)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return await db.list_audit_sessions(limit)

    async def _save(self, session: AuditSession) -> None:
        await db.save_audit_session(session.model_dump())


audit_store = AuditStore()
