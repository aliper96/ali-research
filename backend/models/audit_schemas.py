from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

from .schemas import LogEntry, Progress


class AuditClaim(BaseModel):
    claim: str
    status: Literal["verified", "partially_verified", "unverified", "contradicted"]
    evidence: str = ""
    evidence_url: str = ""


class AuditResult(BaseModel):
    paper_title: str = ""
    paper_url: str = ""
    repo_url: str = ""
    repo_found: bool = False
    claims: list[AuditClaim] = Field(default_factory=list)
    verdict: Literal["matches", "partial_match", "mismatch", "no_repo_found"] = "no_repo_found"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    audit_notes: str = ""


class AuditSession(BaseModel):
    session_id: str
    status: Literal["running", "completed", "error"]
    input: str
    created_at: str
    progress: Progress = Field(default_factory=Progress)
    result: Optional[AuditResult] = None


class StartAuditRequest(BaseModel):
    input: str  # arXiv ID, DOI, URL, or paper title
