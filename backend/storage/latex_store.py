from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models.latex_schemas import LatexCoachSession
from ..models.schemas import LogEntry, Progress

# Directorio de persistencia en disco
_DATA_DIR = Path(__file__).parent.parent / "data" / "latex_sessions"
_ZIPS_DIR = _DATA_DIR / "zips"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_ZIPS_DIR.mkdir(parents=True, exist_ok=True)


class LatexStore:
    """In-memory + disco store para sesiones del LaTeX Coach."""

    def __init__(self) -> None:
        self._sessions: dict[str, LatexCoachSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def create_session(self, filename: str) -> LatexCoachSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = LatexCoachSession(
            session_id=session_id,
            filename=filename,
            created_at=now,
            progress=Progress(percentage=0, logs=[]),
        )
        self._sessions[session_id] = session
        self._queues[session_id] = asyncio.Queue()
        await self._persist(session)
        return session

    def get_session(self, session_id: str) -> Optional[LatexCoachSession]:
        return self._sessions.get(session_id)

    async def get_or_load_session(self, session_id: str) -> Optional[LatexCoachSession]:
        if session_id in self._sessions:
            return self._sessions[session_id]
        # Intentar cargar de disco
        path = _DATA_DIR / f"{session_id}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                session = LatexCoachSession.model_validate(data)
                self._sessions[session_id] = session
                self._queues.setdefault(session_id, asyncio.Queue())
                return session
            except Exception:
                pass
        return None

    async def update_session(self, session: LatexCoachSession) -> None:
        self._sessions[session.session_id] = session
        await self._persist(session)
        queue = self._queues.get(session.session_id)
        if queue:
            await queue.put({
                "type": "progress",
                "percentage": session.progress.percentage,
            })
            await asyncio.sleep(0)

    async def mark_complete(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.status = "completed"
            session.progress.percentage = 100
            self._sessions[session_id] = session
            await self._persist(session)

    async def mark_error(self, session_id: str, message: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.status = "error"
            session.error = message
            self._sessions[session_id] = session
            await self._persist(session)

    # ------------------------------------------------------------------
    # Persistencia de zips en disco (necesario para annotated PDF)
    # ------------------------------------------------------------------

    def save_zip(self, session_id: str, zip_bytes: bytes) -> Path:
        path = _ZIPS_DIR / f"{session_id}.zip"
        path.write_bytes(zip_bytes)
        return path

    def get_zip_path(self, session_id: str) -> Optional[Path]:
        path = _ZIPS_DIR / f"{session_id}.zip"
        return path if path.exists() else None

    def get_zip_bytes(self, session_id: str) -> Optional[bytes]:
        path = self.get_zip_path(session_id)
        return path.read_bytes() if path else None

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    async def add_log(self, session_id: str, message: str, level: str = "info") -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        entry = LogEntry(timestamp=now, message=message, level=level)
        session.progress.logs.append(entry)
        self._sessions[session_id] = session
        await self._persist(session)

        queue = self._queues.get(session_id)
        if queue:
            await queue.put({
                "type": "log",
                "log": entry.model_dump(),
                "percentage": session.progress.percentage,
            })
            await asyncio.sleep(0)

    async def reset_session(self, session_id: str) -> Optional[LatexCoachSession]:
        """Resetea el estado de una sesión existente para re-análisis, conservando filename y zip."""
        session = await self.get_or_load_session(session_id)
        if session is None:
            return None
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        fresh = LatexCoachSession(
            session_id=session_id,
            filename=session.filename,
            created_at=now,
            progress=Progress(percentage=0, logs=[]),
        )
        self._sessions[session_id] = fresh
        # Drain existing queue instead of replacing it — SSE streams hold a reference
        # to the old queue object in their closure, so replacing it breaks SSE updates.
        if session_id in self._queues:
            q = self._queues[session_id]
            while not q.empty():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break
        else:
            self._queues[session_id] = asyncio.Queue()
        await self._persist(fresh)
        return fresh

    # ------------------------------------------------------------------
    # SSE
    # ------------------------------------------------------------------

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(session_id)

    async def notify_complete(self, session_id: str) -> None:
        queue = self._queues.get(session_id)
        if queue:
            await queue.put({"type": "complete"})
            await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        # Combinar en memoria + disco
        sessions = list(self._sessions.values())
        on_disk_ids = {p.stem for p in _DATA_DIR.glob("*.json")}
        for sid in on_disk_ids:
            if sid not in self._sessions:
                s = await self.get_or_load_session(sid)
                if s:
                    sessions.append(s)

        sessions = sorted(sessions, key=lambda s: s.created_at, reverse=True)[:limit]
        return [
            {
                "session_id": s.session_id,
                "filename": s.filename,
                "paper_title": s.paper_title,
                "status": s.status,
                "created_at": s.created_at,
                "overall_score": s.global_assessment.overall if s.global_assessment else None,
                "annotated_pdf_url": s.annotated_pdf_url,
            }
            for s in sessions
        ]

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    async def _persist(self, session: LatexCoachSession) -> None:
        path = _DATA_DIR / f"{session.session_id}.json"
        try:
            path.write_text(session.model_dump_json(), encoding="utf-8")
        except Exception:
            pass  # no romper el flujo principal si falla el disco


latex_store = LatexStore()
