from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

from .schemas import LogEntry, Progress


class WebSource(BaseModel):
    title: str
    url: str
    snippet: str = ""
    content: str = ""
    published_date: Optional[str] = None
    domain: str = ""


class WebSearchResult(BaseModel):
    answer: str = ""
    sources: list[WebSource] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    queries_used: list[str] = Field(default_factory=list)


class WebSearchSession(BaseModel):
    session_id: str
    status: Literal["running", "completed", "error"]
    input: str
    created_at: str
    progress: Progress = Field(default_factory=Progress)
    result: Optional[WebSearchResult] = None


class StartWebSearchRequest(BaseModel):
    input: str
    recency: Literal["any", "day", "week", "month"] = "any"
