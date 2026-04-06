from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

from .schemas import LogEntry, Progress


Recommendation = Literal["accept", "minor_revision", "major_revision", "reject"]


class ReviewerReport(BaseModel):
    reviewer_id: int
    persona: str = ""
    status: Literal["pending", "running", "done", "error"] = "pending"
    # Scores 0–10
    novelty_score: float = Field(default=0.0, ge=0.0, le=10.0)
    technical_score: float = Field(default=0.0, ge=0.0, le=10.0)
    clarity_score: float = Field(default=0.0, ge=0.0, le=10.0)
    contribution_score: float = Field(default=0.0, ge=0.0, le=10.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=10.0)
    recommendation: Recommendation = "major_revision"
    strengths: list[str] = Field(default_factory=list)
    major_issues: list[str] = Field(default_factory=list)
    minor_issues: list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    related_papers_found: list[str] = Field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None


class EditorReport(BaseModel):
    final_recommendation: Recommendation = "major_revision"
    novelty_score: float = 0.0
    technical_score: float = 0.0
    clarity_score: float = 0.0
    contribution_score: float = 0.0
    overall_score: float = 0.0
    consensus_summary: str = ""
    major_issues: list[str] = Field(default_factory=list)
    minor_issues: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    reviewer_agreement: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty_verdict: str = ""      # e.g. "Incremental", "Solid", "Strong"
    publishability: str = ""       # e.g. "Top venue", "Workshop", "Not ready"


class ReviewSession(BaseModel):
    session_id: str
    status: Literal["running", "completed", "error"] = "running"
    paper_title: str = ""
    paper_abstract: str = ""
    filename: str = ""
    num_reviewers: int = 3
    reviewer_reports: list[ReviewerReport] = Field(default_factory=list)
    editor_report: Optional[EditorReport] = None
    created_at: str = ""
    progress: Progress = Field(default_factory=Progress)
