from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..models.review_schemas import EditorReport, ReviewerReport, ReviewSession
from ..models.schemas import LogEntry, Progress
from . import db


class ReviewStore:
    """In-memory + PostgreSQL store for peer-review sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, ReviewSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def create_session(
        self,
        paper_title: str,
        paper_abstract: str,
        filename: str,
        num_reviewers: int,
    ) -> ReviewSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        reviewer_reports = [
            ReviewerReport(reviewer_id=i + 1) for i in range(num_reviewers)
        ]
        session = ReviewSession(
            session_id=session_id,
            paper_title=paper_title,
            paper_abstract=paper_abstract,
            filename=filename,
            num_reviewers=num_reviewers,
            reviewer_reports=reviewer_reports,
            created_at=now,
            progress=Progress(percentage=0, logs=[]),
        )
        self._sessions[session_id] = session
        self._queues[session_id] = asyncio.Queue()
        await self._persist(session)
        return session

    def get_session(self, session_id: str) -> Optional[ReviewSession]:
        return self._sessions.get(session_id)

    async def get_or_load_session(self, session_id: str) -> Optional[ReviewSession]:
        if session_id in self._sessions:
            return self._sessions[session_id]
        data = await db.load_review_session(session_id)
        if data is None:
            return None
        session = ReviewSession.model_validate(data)
        self._sessions[session_id] = session
        self._queues.setdefault(session_id, asyncio.Queue())
        return session

    async def mark_complete(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.status = "completed"
            session.progress.percentage = 100
            await self._persist(session)

    async def mark_error(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.status = "error"
            await self._persist(session)

    # ------------------------------------------------------------------
    # Reviewer updates
    # ------------------------------------------------------------------

    async def update_reviewer(
        self, session_id: str, report: ReviewerReport
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        for i, r in enumerate(session.reviewer_reports):
            if r.reviewer_id == report.reviewer_id:
                session.reviewer_reports[i] = report
                break
        else:
            session.reviewer_reports.append(report)

        # Update progress %: each done reviewer = portion of 80%
        done = sum(1 for r in session.reviewer_reports if r.status == "done")
        session.progress.percentage = min(10 + int(done / session.num_reviewers * 80), 90)

        self._sessions[session_id] = session
        await self._persist(session)
        # Push SSE update
        queue = self._queues.get(session_id)
        if queue:
            await queue.put(
                {
                    "type": "reviewer_update",
                    "reviewer_id": report.reviewer_id,
                    "status": report.status,
                    "recommendation": report.recommendation,
                    "overall_score": report.overall_score,
                    "percentage": session.progress.percentage,
                }
            )
            await asyncio.sleep(0)

    async def set_editor_report(
        self, session_id: str, report: EditorReport
    ) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.editor_report = report
            session.progress.percentage = 95
            self._sessions[session_id] = session
            await self._persist(session)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    async def add_log(
        self, session_id: str, message: str, level: str = "info"
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        entry = LogEntry(timestamp=now, message=message, level=level)  # type: ignore[arg-type]
        session.progress.logs.append(entry)
        self._sessions[session_id] = session
        await self._persist(session)

        queue = self._queues.get(session_id)
        if queue:
            await queue.put(
                {
                    "type": "log",
                    "log": entry.model_dump(),
                    "percentage": session.progress.percentage,
                }
            )
            await asyncio.sleep(0)

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
        db_rows = await db.list_review_sessions(limit)
        if not db_rows:
            return [
                {
                    "session_id": s.session_id,
                    "paper_title": s.paper_title,
                    "status": s.status,
                    "created_at": s.created_at,
                    "num_reviewers": s.num_reviewers,
                    "recommendation": s.editor_report.final_recommendation
                    if s.editor_report
                    else None,
                }
                for s in sorted(
                    self._sessions.values(), key=lambda x: x.created_at, reverse=True
                )[:limit]
            ]
        return db_rows

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _persist(self, session: ReviewSession) -> None:
        await db.save_review_session(session.model_dump())


review_store = ReviewStore()
