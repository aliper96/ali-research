from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class DocChunkRef(BaseModel):
    """Lightweight chunk reference returned in Q&A answers."""
    doc_id: str
    doc_title: str
    chunk_index: int
    content: str


class DocRecord(BaseModel):
    """Metadata about an uploaded document."""
    doc_id: str
    title: str
    filename: str
    page_count: int
    chunk_count: int
    created_at: str
    size_bytes: int


class DocsQARequest(BaseModel):
    question: str
    top_k: int = 5


class DocsQAResult(BaseModel):
    question: str
    answer: str
    sources: list[DocChunkRef] = Field(default_factory=list)
