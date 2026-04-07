from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field
from .schemas import Paper, CitationLink, LogEntry, Progress, ResearchResult


class SubResearchResult(BaseModel):
    subtopic: str
    researcher_id: int
    status: Literal["pending", "running", "done", "error"] = "pending"
    papers: list[Paper] = Field(default_factory=list)
    key_findings: str = ""
    citation_links: list[CitationLink] = Field(default_factory=list)
    error: str = ""


class VerifiedClaim(BaseModel):
    claim: str
    supported_by: list[str] = Field(default_factory=list)   # paper ids
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    verdict: Literal["supported", "partial", "unsupported"] = "partial"


class VerificationReport(BaseModel):
    verified_claims: list[VerifiedClaim] = Field(default_factory=list)
    unsupported_sentences: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DeepResearchResult(BaseModel):
    subtopics: list[str] = Field(default_factory=list)
    researchers: list[SubResearchResult] = Field(default_factory=list)
    synthesis: Optional[ResearchResult] = None
    verification: Optional[VerificationReport] = None


class DeepResearchSession(BaseModel):
    session_id: str
    status: Literal["running", "completed", "error"]
    input: str
    depth: str = "deep"
    created_at: str
    progress: Progress = Field(default_factory=Progress)
    result: Optional[DeepResearchResult] = None


class StartDeepResearchRequest(BaseModel):
    input: str
    depth: Literal["standard", "deep"] = "deep"
    num_researchers: int = Field(default=3, ge=2, le=5)
