"""
Document Q&A runner — RAG over uploaded PDFs and text files.

Upload flow:
  1. Parse PDF/text with pypdf (already installed)
  2. Split into overlapping chunks (~800 chars, 150 overlap)
  3. Embed each chunk with OpenAI text-embedding-3-small
  4. Persist document + chunks in PostgreSQL (embedding as JSONB)

Q&A flow:
  1. Embed the user question
  2. Cosine similarity against all stored chunks (numpy, in-Python)
  3. Retrieve top-K chunks
  4. LLM synthesizes answer with inline [Doc Title, chunk N] citations
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import openai

from ..models.docs_schemas import DocChunkRef, DocRecord, DocsQAResult
from ..storage import db

logger = logging.getLogger(__name__)

_EMBED_MODEL = "text-embedding-3-small"
_CHUNK_SIZE = 800       # chars
_CHUNK_OVERLAP = 150    # chars
_MAX_CONTEXT_CHARS = 1200  # chars per chunk sent to LLM


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_pdf(data: bytes) -> tuple[str, int]:
    """Extract plain text and page count from PDF bytes."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n".join(pages), len(pages)


def _extract_text(data: bytes, filename: str) -> tuple[str, int]:
    """Extract text from PDF or plain-text file. Returns (text, page_count)."""
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return _extract_pdf(data)
    # Plain text / markdown / tex
    try:
        return data.decode("utf-8", errors="replace"), 1
    except Exception:
        return "", 1


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

async def _embed_texts(client: openai.AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Batch-embed texts using OpenAI. Returns list of embedding vectors."""
    # OpenAI supports up to 2048 inputs per request; chunk if needed
    batch_size = 100
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = await client.embeddings.create(model=_EMBED_MODEL, input=batch)
        all_embeddings.extend([item.embedding for item in resp.data])
    return all_embeddings


# ---------------------------------------------------------------------------
# Cosine similarity search
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


async def _retrieve_chunks(
    client: openai.AsyncOpenAI,
    question: str,
    top_k: int = 5,
) -> list[dict]:
    """Embed question, load all chunks, return top-K by cosine similarity."""
    # Embed question
    resp = await client.embeddings.create(model=_EMBED_MODEL, input=[question])
    q_vec = resp.data[0].embedding

    # Load all chunks from DB
    all_chunks = await db.docs_get_all_chunks()
    if not all_chunks:
        return []

    # Score
    scored = [
        (chunk, _cosine_similarity(q_vec, chunk["embedding"]))
        for chunk in all_chunks
        if chunk["embedding"]
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored[:top_k]]


# ---------------------------------------------------------------------------
# Answer synthesis
# ---------------------------------------------------------------------------

_QA_SYSTEM = (
    "You are a precise document assistant. Answer the question using ONLY the "
    "provided document excerpts. Cite sources inline as [Doc Title, chunk N]. "
    "If the answer is not in the documents, say so clearly.\n\n"
    "Return ONLY this JSON:\n"
    '{{"answer": "your answer with [Doc Title, chunk N] citations"}}'
)


def _build_qa_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        parts.append(
            f"[{c['doc_title']}, chunk {c['chunk_index'] + 1}]\n"
            f"{c['content'][:_MAX_CONTEXT_CHARS]}"
        )
    return "\n\n---\n\n".join(parts)


async def _synthesize_qa(
    client: openai.AsyncOpenAI,
    model: str,
    question: str,
    chunks: list[dict],
) -> str:
    context = _build_qa_context(chunks)
    try:
        resp = await client.chat.completions.create(
            model=model,
            max_completion_tokens=2000,
            messages=[
                {"role": "system", "content": _QA_SYSTEM},
                {"role": "user", "content": f"Question: {question}\n\nDocuments:\n{context}"},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            data = json.loads(match.group())
            return str(data.get("answer", text))
        return text
    except Exception as exc:
        logger.error("docs QA synthesis failed: %s", exc)
        return "Unable to synthesize an answer from the retrieved documents."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def process_upload(
    filename: str,
    data: bytes,
) -> DocRecord:
    """
    Parse, chunk, embed, and persist a document.
    Returns a DocRecord with metadata.
    Raises on fatal errors.
    """
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")  # unused but consistent
    client = openai.AsyncOpenAI()

    doc_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    # 1. Extract text
    text, page_count = await asyncio.to_thread(_extract_text, data, filename)
    if not text.strip():
        raise ValueError(f"Could not extract text from {filename!r}")

    # Derive title from filename
    title = re.sub(r"\.(pdf|txt|md|tex)$", "", filename, flags=re.IGNORECASE)
    title = re.sub(r"[-_]", " ", title).strip() or filename

    # 2. Chunk
    raw_chunks = await asyncio.to_thread(_chunk_text, text)
    if not raw_chunks:
        raise ValueError(f"Document {filename!r} produced no chunks after parsing")

    # 3. Embed
    embeddings = await _embed_texts(client, raw_chunks)

    # 4. Persist
    doc = {
        "doc_id": doc_id,
        "title": title,
        "filename": filename,
        "page_count": page_count,
        "chunk_count": len(raw_chunks),
        "size_bytes": len(data),
        "created_at": created_at,
    }
    await db.docs_save_document(doc)

    chunks = [
        {"chunk_index": i, "content": text, "embedding": emb}
        for i, (text, emb) in enumerate(zip(raw_chunks, embeddings))
    ]
    await db.docs_save_chunks(doc_id, chunks)

    logger.info("Processed doc %s: %d chunks, %d pages", doc_id, len(raw_chunks), page_count)
    return DocRecord(**doc)


async def answer_question(question: str, top_k: int = 5) -> DocsQAResult:
    """
    Retrieve relevant chunks from all stored documents and synthesize an answer.
    """
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    client = openai.AsyncOpenAI()

    chunks = await _retrieve_chunks(client, question, top_k=top_k)
    if not chunks:
        return DocsQAResult(
            question=question,
            answer="No documents are uploaded yet. Please upload some PDFs first.",
            sources=[],
        )

    answer = await _synthesize_qa(client, model, question, chunks)

    sources = [
        DocChunkRef(
            doc_id=c["doc_id"],
            doc_title=c["doc_title"],
            chunk_index=c["chunk_index"],
            content=c["content"][:300],
        )
        for c in chunks
    ]

    return DocsQAResult(question=question, answer=answer, sources=sources)
