from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    timestamp: str
    message: str
    level: Literal["info", "success", "warning", "error"]


class Progress(BaseModel):
    percentage: int = Field(default=0, ge=0, le=100)
    logs: list[LogEntry] = Field(default_factory=list)


class Paper(BaseModel):
    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    abstract: str = ""
    url: str = ""
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    relevance_reason: str = ""
    citation_count: int = 0
    tags: list[str] = Field(default_factory=list)


class CitationLink(BaseModel):
    source: str
    target: str


class RoadmapStep(BaseModel):
    step: str
    description: str
    difficulty: Literal["easy", "medium", "hard"]


class ResearchResult(BaseModel):
    summary: str = ""
    papers: list[Paper] = Field(default_factory=list)
    citation_links: list[CitationLink] = Field(default_factory=list)
    gap_analysis: list[str] = Field(default_factory=list)
    implementation_roadmap: list[RoadmapStep] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)


class ResearchSession(BaseModel):
    session_id: str
    status: Literal["running", "completed", "error"]
    input: str
    created_at: str
    progress: Progress = Field(default_factory=Progress)
    result: Optional[ResearchResult] = None


class StartResearchRequest(BaseModel):
    input: str
    depth: Literal["quick", "standard", "deep"] = "standard"
