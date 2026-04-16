"""
Research tools for the ali_researcher agent.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
from pypdf import PdfReader

from ..storage.research_store import research_store
from ..storage.session_store import session_store
from ..storage import db as _db

logger = logging.getLogger(__name__)

_SEMSCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
_CROSSREF_BASE = "https://api.crossref.org/works"
_GITHUB_API_BASE = "https://api.github.com"
_SS_FIELDS = (
    "title,authors,year,abstract,citationCount,externalIds,url,"
    "referenceCount,influentialCitationCount,venue,publicationVenue"
)

# ---------------------------------------------------------------------------
# Semantic Scholar rate-limit guard
# ---------------------------------------------------------------------------
# Free tier: ~100 req/5 min (≈ 1 req/3 s to be safe).
# With S2_API_KEY: 1 req/s officially, but still be conservative.
# We use a semaphore (1 concurrent) + a minimum delay between calls.

_S2_LOCK = asyncio.Lock()           # serialise all S2 calls
_S2_LAST_CALL: float = 0.0          # epoch time of last completed call
_S2_MIN_INTERVAL: float = float(os.environ.get("S2_MIN_INTERVAL", "1.2"))  # seconds


def _s2_headers() -> dict[str, str]:
    """Return headers for Semantic Scholar API, injecting key if configured."""
    h: dict[str, str] = {"User-Agent": "ali_researcher/1.0"}
    key = os.environ.get("S2_API_KEY", "").strip()
    if key:
        h["x-api-key"] = key
    return h


async def _s2_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Rate-limited GET to the Semantic Scholar API with exponential-backoff retry.

    • Serialises all calls through _S2_LOCK with a minimum inter-call interval
      so we never fire more than ~1 req/s.
    • On 429 the lock is released BEFORE sleeping, so other coroutines don't
      pile up behind the backoff wait.
    • Retries up to 4 times with backoff: 8 s → 24 s → 72 s → 216 s.
    """
    global _S2_LAST_CALL

    for attempt in range(4):
        # ── 1. Acquire lock, enforce spacing, fire request ───────────────────
        retry_after: float | None = None
        try:
            async with _S2_LOCK:
                now = asyncio.get_event_loop().time()
                gap = _S2_MIN_INTERVAL - (now - _S2_LAST_CALL)
                if gap > 0:
                    await asyncio.sleep(gap)

                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    resp = await client.get(url, params=params, headers=_s2_headers())
                    _S2_LAST_CALL = asyncio.get_event_loop().time()

                if resp.status_code == 429:
                    # Respect Retry-After but cap at 60s so sessions don't stall
                    raw = float(resp.headers.get("Retry-After", 10 * (2 ** attempt)))
                    retry_after = min(raw, 60.0)
                else:
                    resp.raise_for_status()
                    return resp.json()

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            raw = float(exc.response.headers.get("Retry-After", 10 * (2 ** attempt)))
            retry_after = min(raw, 60.0)

        # ── 2. Sleep OUTSIDE the lock so other callers aren't blocked ────────
        if retry_after is not None:
            logger.warning(
                "Semantic Scholar 429 — sleeping %.0fs before retry %d/4", retry_after, attempt + 1
            )
            await asyncio.sleep(retry_after)

    # Exhausted retries — return empty dict so callers get [] gracefully
    logger.error("Semantic Scholar API rate-limit: giving up after 4 attempts for %s", url)
    return {}


_COMMON_STOPWORDS = {
    "the", "and", "for", "with", "that", "from", "this", "into", "using",
    "their", "have", "been", "were", "which", "such", "also", "than",
    "these", "paper", "papers", "study", "approach", "model", "models",
}


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return json.dumps(str(obj))


def _truncate(text: str, max_chars: int = 2000) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _coerce_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", text)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None
    try:
        return int(text)
    except ValueError:
        return None


def _coerce_citation_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    match = re.search(r"\d+", text)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return 0
    return 0


def _extract_arxiv_id(value: str) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", value)
    if match:
        return match.group(1)
    match = re.search(r"arxiv[:/ ]([a-z\-]+/\d{7})(v\d+)?", value, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _extract_doi(value: str) -> str | None:
    if not value:
        return None
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", value, re.IGNORECASE)
    return match.group(1) if match else None


def _sentence_split(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) > 20]


def _pick_sentences(text: str, keywords: list[str], max_items: int = 5) -> list[str]:
    scored: list[tuple[int, str]] = []
    for sentence in _sentence_split(text):
        lower_sentence = sentence.lower()
        score = sum(1 for keyword in keywords if keyword in lower_sentence)
        if score:
            scored.append((score, sentence))
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return [sentence for _, sentence in scored[:max_items]]


def _top_keywords(texts: list[str], max_items: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text.lower()):
            if token not in _COMMON_STOPWORDS:
                counter[token] += 1
    return [token for token, _ in counter.most_common(max_items)]


def _paper_identity(paper: dict[str, Any]) -> str:
    return (
        str(paper.get("id") or "")
        or str(paper.get("doi") or "")
        or str(paper.get("arxiv_id") or "")
        or _normalize_title(str(paper.get("title") or ""))
    )


def _dedupe_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for paper in papers:
        identity = _paper_identity(paper)
        if not identity:
            continue
        current = merged.get(identity, {})
        combined = {**current, **paper}
        combined["authors"] = list(dict.fromkeys((current.get("authors") or []) + (paper.get("authors") or [])))
        combined["tags"] = list(dict.fromkeys((current.get("tags") or []) + (paper.get("tags") or [])))
        combined["citation_count"] = max(int(current.get("citation_count") or 0), int(paper.get("citation_count") or 0))
        merged[identity] = combined
    return list(merged.values())


def _paper_to_bibtex_key(paper: dict[str, Any]) -> str:
    first_author = "unknown"
    authors = paper.get("authors") or []
    if authors:
        first_author = re.sub(r"[^a-zA-Z0-9]+", "", str(authors[0]).split()[-1].lower()) or "unknown"
    year = str(paper.get("year") or "nd")
    title_word = re.sub(r"[^a-zA-Z0-9]+", "", (paper.get("title") or "untitled").split(" ")[0].lower())
    return f"{first_author}{year}{title_word}"


async def _http_get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _trim_arxiv_query(query: str, max_words: int = 8) -> str:
    """
    arXiv performs poorly (slow / 429) on queries longer than ~8 words.
    Keep only the first max_words content words, discarding stop-words at
    the end so the trimmed query stays meaningful.
    """
    words = query.split()
    if len(words) <= max_words:
        return query
    trimmed = words[:max_words]
    # Drop trailing stop-words so we don't end on "and", "for", etc.
    stops = {"and", "or", "for", "with", "the", "a", "an", "of", "in", "on", "to"}
    while trimmed and trimmed[-1].lower() in stops:
        trimmed.pop()
    result = " ".join(trimmed) if trimmed else " ".join(words[:max_words])
    logger.debug("arXiv query trimmed: %r → %r", query, result)
    return result


async def search_arxiv(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    year_from: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search arXiv for academic papers.

    sort_by:  "relevance" (default) | "recent" (newest submissions first)
    year_from: if set, only return papers published in that year or later.
               Uses post-filtering because arXiv date-query syntax is fragile
               when combined with keyword queries.
    """
    import arxiv

    # arXiv 429s on very long queries — trim to 8 keywords
    effective_query = _trim_arxiv_query(query, max_words=8)

    # Cap total results: arXiv's internal page size is always 100 regardless,
    # so requesting more than 15 just means waiting for multiple pages.
    max_results = min(max_results, 15)

    criterion = (
        arxiv.SortCriterion.SubmittedDate
        if sort_by == "recent"
        else arxiv.SortCriterion.Relevance
    )

    def _sync_search() -> list[dict[str, Any]]:
        search = arxiv.Search(query=effective_query, max_results=max_results, sort_by=criterion)
        results: list[dict[str, Any]] = []
        for paper in search.results():
            paper_year = paper.published.year if paper.published else None
            if year_from and paper_year and paper_year < year_from:
                continue
            arxiv_id = paper.entry_id.split("/")[-1]
            results.append(
                {
                    "id": arxiv_id,
                    "title": paper.title,
                    "authors": [str(author) for author in paper.authors],
                    "year": paper_year,
                    "abstract": paper.summary,
                    "url": paper.entry_id,
                    "arxiv_id": arxiv_id,
                    "doi": paper.doi,
                    "citation_count": 0,
                    "tags": [c.term if hasattr(c, "term") else str(c) for c in getattr(paper, "categories", [])],
                    "source": "arxiv",
                    "pdf_url": getattr(paper, "pdf_url", None),
                }
            )
            if len(results) >= max_results:
                break
        return results

    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_search)
    except Exception as exc:
        logger.error("search_arxiv failed: %s", exc)
        return []


async def get_arxiv_paper(arxiv_id: str) -> dict[str, Any]:
    import arxiv

    clean_id = (arxiv_id or "").split("v")[0]

    def _sync_fetch() -> dict[str, Any]:
        search = arxiv.Search(id_list=[clean_id])
        for paper in search.results():
            return {
                "id": clean_id,
                "title": paper.title,
                "authors": [str(author) for author in paper.authors],
                "year": paper.published.year if paper.published else None,
                "abstract": paper.summary,
                "url": paper.entry_id,
                "arxiv_id": clean_id,
                "doi": paper.doi,
                "citation_count": 0,
                "tags": [c.term if hasattr(c, "term") else str(c) for c in getattr(paper, "categories", [])],
                "source": "arxiv",
                "pdf_url": getattr(paper, "pdf_url", None),
            }
        return {}

    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_fetch)
    except Exception as exc:
        logger.error("get_arxiv_paper failed: %s", exc)
        return {}


async def search_semantic_scholar(
    query: str,
    max_results: int = 10,
    year_from: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search Semantic Scholar for academic papers.

    year_from: if set, only return papers from that year onwards.
               Passed as the native ``year`` API parameter (e.g. "2022-").
    """
    params: dict[str, Any] = {"query": query, "limit": max_results, "fields": _SS_FIELDS}
    if year_from:
        params["year"] = f"{year_from}-"

    try:
        data = await _s2_get(f"{_SEMSCHOLAR_BASE}/paper/search", params)
        papers: list[dict[str, Any]] = []
        for item in data.get("data", []):
            ext = item.get("externalIds") or {}
            papers.append(
                {
                    "id": item.get("paperId", ""),
                    "title": item.get("title", ""),
                    "authors": [author.get("name", "") for author in item.get("authors", [])],
                    "year": item.get("year"),
                    "abstract": item.get("abstract") or "",
                    "url": item.get("url") or f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
                    "arxiv_id": ext.get("ArXiv"),
                    "doi": ext.get("DOI"),
                    "citation_count": item.get("citationCount", 0),
                    "tags": [item.get("venue") or item.get("publicationVenue", {}).get("name", "")] if item.get("venue") or item.get("publicationVenue") else [],
                    "source": "semantic_scholar",
                }
            )
        return papers
    except Exception as exc:
        logger.error("search_semantic_scholar failed: %s", exc)
        return []


async def _get_semantic_scholar_paper(paper_id: str) -> dict[str, Any]:
    try:
        data = await _s2_get(
            f"{_SEMSCHOLAR_BASE}/paper/{paper_id}",
            {"fields": _SS_FIELDS},
        )
        ext = data.get("externalIds") or {}
        return {
            "id": data.get("paperId", paper_id),
            "title": data.get("title", ""),
            "authors": [author.get("name", "") for author in data.get("authors", [])],
            "year": data.get("year"),
            "abstract": data.get("abstract") or "",
            "url": data.get("url") or f"https://www.semanticscholar.org/paper/{data.get('paperId', paper_id)}",
            "arxiv_id": ext.get("ArXiv"),
            "doi": ext.get("DOI"),
            "citation_count": data.get("citationCount", 0),
            "reference_count": data.get("referenceCount", 0),
            "influential_citation_count": data.get("influentialCitationCount", 0),
            "tags": [data.get("venue")] if data.get("venue") else [],
            "source": "semantic_scholar",
        }
    except Exception as exc:
        logger.error("_get_semantic_scholar_paper failed: %s", exc)
        return {}


def _normalize_s2_id(paper_id: str) -> str:
    """Convert arXiv IDs (with or without version) to S2-compatible format."""
    arxiv_id = _extract_arxiv_id(paper_id)
    if arxiv_id:
        return f"arXiv:{arxiv_id}"
    return paper_id


async def get_paper_citations(paper_id: str, source: str = "semantic_scholar", max_results: int = 25) -> list[dict[str, Any]]:
    if source != "semantic_scholar":
        return []

    s2_id = _normalize_s2_id(paper_id)
    try:
        data = await _s2_get(
            f"{_SEMSCHOLAR_BASE}/paper/{s2_id}/citations",
            {"fields": _SS_FIELDS, "limit": max_results},
        )
        citations: list[dict[str, Any]] = []
        for item in data.get("data", []):
            citing = item.get("citingPaper") or {}
            ext = citing.get("externalIds") or {}
            if not citing:
                continue
            citations.append(
                {
                    "id": citing.get("paperId", ""),
                    "title": citing.get("title", ""),
                    "authors": [author.get("name", "") for author in citing.get("authors", [])],
                    "year": citing.get("year"),
                    "abstract": citing.get("abstract") or "",
                    "url": citing.get("url") or f"https://www.semanticscholar.org/paper/{citing.get('paperId', '')}",
                    "arxiv_id": ext.get("ArXiv"),
                    "doi": ext.get("DOI"),
                    "citation_count": citing.get("citationCount", 0),
                    "tags": [],
                    "cites": paper_id,
                    "source": "semantic_scholar",
                }
            )
        return citations
    except Exception as exc:
        logger.error("get_paper_citations failed: %s", exc)
        return []


async def get_references(paper_id: str, source: str = "semantic_scholar", max_results: int = 25) -> list[dict[str, Any]]:
    if source != "semantic_scholar":
        return []

    s2_id = _normalize_s2_id(paper_id)
    try:
        data = await _s2_get(
            f"{_SEMSCHOLAR_BASE}/paper/{s2_id}/references",
            {"fields": _SS_FIELDS, "limit": max_results},
        )
        references: list[dict[str, Any]] = []
        for item in data.get("data", []):
            cited = item.get("citedPaper") or {}
            ext = cited.get("externalIds") or {}
            if not cited:
                continue
            references.append(
                {
                    "id": cited.get("paperId", ""),
                    "title": cited.get("title", ""),
                    "authors": [author.get("name", "") for author in cited.get("authors", [])],
                    "year": cited.get("year"),
                    "abstract": cited.get("abstract") or "",
                    "url": cited.get("url") or f"https://www.semanticscholar.org/paper/{cited.get('paperId', '')}",
                    "arxiv_id": ext.get("ArXiv"),
                    "doi": ext.get("DOI"),
                    "citation_count": cited.get("citationCount", 0),
                    "tags": [],
                    "referenced_by": paper_id,
                    "source": "semantic_scholar",
                }
            )
        return references
    except Exception as exc:
        logger.error("get_references failed: %s", exc)
        return []


async def get_related_papers(
    paper_id: str,
    year_from: int | None = None,
    max_results: int = 15,
) -> list[dict[str, Any]]:
    """
    Find papers semantically similar to a given paper using the Semantic Scholar
    Recommendations API. Ideal for discovering recent follow-up work.

    paper_id: Semantic Scholar paper ID or arXiv ID (e.g. "2301.07041")
    year_from: only return papers published in this year or later
    max_results: max papers to return (capped at 500 by the API)
    """
    s2_id = _normalize_s2_id(paper_id)
    try:
        data = await _s2_get(
            f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{s2_id}",
            {"fields": _SS_FIELDS, "limit": min(max_results * 3, 100)},
        )
        papers: list[dict[str, Any]] = []
        for item in data.get("recommendedPapers", []):
            ext = item.get("externalIds") or {}
            year = item.get("year")
            if year_from and year and year < year_from:
                continue
            papers.append(
                {
                    "id": item.get("paperId", ""),
                    "title": item.get("title", ""),
                    "authors": [a.get("name", "") for a in item.get("authors", [])],
                    "year": year,
                    "abstract": item.get("abstract") or "",
                    "url": item.get("url") or f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
                    "arxiv_id": ext.get("ArXiv"),
                    "doi": ext.get("DOI"),
                    "citation_count": item.get("citationCount", 0),
                    "tags": [item.get("venue")] if item.get("venue") else [],
                    "source": "semantic_scholar",
                    "recommended_from": paper_id,
                }
            )
            if len(papers) >= max_results:
                break
        # Sort by year descending so newest appear first
        papers.sort(key=lambda p: (p.get("year") or 0), reverse=True)
        return papers
    except Exception as exc:
        logger.error("get_related_papers failed for %s: %s", paper_id, exc)
        return []


_SEARXNG_INSTANCES = [
    os.environ.get("SEARXNG_URL", ""),   # local instance first if configured
    "https://searxng.world",
    "https://searx.be",
    "https://search.mdosch.de",
]


async def search_web(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search the web via SearXNG (local instance preferred, public fallback)."""
    params = {
        "q": query,
        "format": "json",
        "engines": "google,bing,duckduckgo",
        "categories": "general",
        "language": "en",
    }
    headers = {"User-Agent": "ali_researcher/1.0 (academic research tool)"}

    for instance in _SEARXNG_INSTANCES:
        if not instance:
            continue
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(f"{instance}/search", params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            results = data.get("results", [])[:max_results]
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "source": "web",
                }
                for r in results
            ]
        except Exception as exc:
            logger.warning("SearXNG instance %s failed: %s — trying next", instance, exc)

    logger.error("All SearXNG instances failed for query: %s", query)
    return []


async def search_google_scholar(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Search Google Scholar for academic papers (free, no API key)."""
    def _sync_scholar() -> list[dict[str, Any]]:
        from scholarly import scholarly as _scholarly
        results: list[dict[str, Any]] = []
        search_gen = _scholarly.search_pubs(query)
        for _ in range(max_results):
            try:
                pub = next(search_gen)
                bib = pub.get("bib", {})
                results.append({
                    "id": pub.get("author_id", [bib.get("title", "")])[0] if pub.get("author_id") else bib.get("title", ""),
                    "title": bib.get("title", ""),
                    "authors": bib.get("author", []) if isinstance(bib.get("author"), list) else [bib.get("author", "")],
                    "year": _coerce_year(bib.get("pub_year")),
                    "abstract": bib.get("abstract", ""),
                    "url": pub.get("pub_url") or pub.get("eprint_url", ""),
                    "arxiv_id": None,
                    "doi": None,
                    "citation_count": _coerce_citation_count(pub.get("num_citations", 0)),
                    "tags": [],
                    "venue": bib.get("venue", ""),
                    "source": "google_scholar",
                })
            except StopIteration:
                break
            except Exception:
                continue
        return results

    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_scholar)
    except Exception as exc:
        logger.error("search_google_scholar failed: %s", exc)
        return []


async def search_code(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    try:
        data = await _http_get_json(
            f"{_GITHUB_API_BASE}/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": max_results},
            headers={"Accept": "application/vnd.github+json", "User-Agent": "ali_researcher/1.0"},
        )
        return [
            {
                "name": repo.get("full_name", ""),
                "url": repo.get("html_url", ""),
                "description": repo.get("description") or "",
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language"),
                "updated_at": repo.get("updated_at"),
                "topics": repo.get("topics", []),
            }
            for repo in data.get("items", [])
        ]
    except Exception as exc:
        logger.error("search_code failed: %s", exc)
        return []


async def parse_pdf(source: str, max_pages: int = 12) -> dict[str, Any]:
    try:
        if source.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(source)
                response.raise_for_status()
                reader = PdfReader(io.BytesIO(response.content))
        else:
            reader = PdfReader(source)

        pages = reader.pages[:max_pages]
        page_texts = [page.extract_text() or "" for page in pages]
        full_text = "\n".join(page_texts).strip()
        section_lines = [
            line.strip()
            for line in full_text.splitlines()
            if line.strip() and len(line.strip()) < 100 and re.match(r"^(\d+\.?\s+)?[A-Z][A-Za-z0-9 ,:/\-()]+$", line.strip())
        ]
        references = [
            line.strip()
            for line in full_text.splitlines()
            if re.match(r"^\[\d+\]", line.strip()) or re.match(r"^\d+\.\s", line.strip())
        ][:30]
        return {
            "source": source,
            "page_count": len(reader.pages),
            "parsed_pages": len(pages),
            "text_excerpt": _truncate(full_text, 6000),
            "sections": section_lines[:20],
            "references": references,
        }
    except Exception as exc:
        logger.error("parse_pdf failed: %s", exc)
        return {"source": source, "error": str(exc)}


async def resolve_paper_id(identifier: str) -> dict[str, Any]:
    arxiv_id = _extract_arxiv_id(identifier)
    if arxiv_id:
        return {"input": identifier, "resolved": await get_arxiv_paper(arxiv_id), "resolver": "arxiv"}

    doi = _extract_doi(identifier)
    if doi:
        try:
            data = await _http_get_json(f"{_CROSSREF_BASE}/{quote_plus(doi)}", headers={"User-Agent": "ali_researcher/1.0"})
            item = data.get("message", {})
            return {
                "input": identifier,
                "resolver": "crossref",
                "resolved": {
                    "id": doi,
                    "doi": doi,
                    "title": (item.get("title") or [""])[0],
                    "year": ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0],
                    "authors": [" ".join(filter(None, [author.get("given"), author.get("family")])).strip() for author in item.get("author", [])],
                    "url": item.get("URL", ""),
                    "abstract": item.get("abstract") or "",
                    "source": "crossref",
                },
            }
        except Exception as exc:
            logger.warning("resolve_paper_id Crossref failed: %s", exc)

    if identifier.startswith(("http://", "https://")):
        parsed = urlparse(identifier)
        return {"input": identifier, "resolver": "url", "resolved": {"url": identifier, "host": parsed.netloc}}

    papers = await search_papers(identifier, max_results=5)
    return {"input": identifier, "resolver": "search", "resolved": papers[0] if papers else None, "candidates": papers}


async def search_papers(query: str, max_results: int = 12) -> list[dict[str, Any]]:
    arxiv_results, s2_results, scholar_results = await asyncio.gather(
        search_arxiv(query, max_results=max_results),
        search_semantic_scholar(query, max_results=max_results),
        search_google_scholar(query, max_results=max_results),
        return_exceptions=True,
    )
    papers: list[dict[str, Any]] = []
    for result in (arxiv_results, s2_results, scholar_results):
        if isinstance(result, list):
            papers.extend(result)
    deduped = _dedupe_papers(papers)
    deduped.sort(
        key=lambda paper: (
            _coerce_citation_count(paper.get("citation_count")),
            _coerce_year(paper.get("year")) or 0,
        ),
        reverse=True,
    )
    return deduped[:max_results]


async def get_paper_metadata(paper_id: str, source: str = "auto") -> dict[str, Any]:
    clean_source = source.lower()
    if clean_source in {"auto", "arxiv"}:
        arxiv_id = _extract_arxiv_id(paper_id)
        if arxiv_id:
            paper = await get_arxiv_paper(arxiv_id)
            if paper:
                return paper
    if clean_source in {"auto", "semantic_scholar", "s2"}:
        paper = await _get_semantic_scholar_paper(paper_id)
        if paper:
            return paper
    resolved = await resolve_paper_id(paper_id)
    return resolved.get("resolved") or {}


async def extract_claims(text: str, max_claims: int = 5) -> list[str]:
    claims = _pick_sentences(text, ["we propose", "we present", "we show", "our method", "achieves", "outperform"], max_claims)
    return claims or _sentence_split(text)[:max_claims]


async def extract_methodology(text: str) -> dict[str, Any]:
    sentences = _pick_sentences(text, ["method", "approach", "architecture", "framework", "pipeline", "training", "algorithm"], 8)
    keywords = _top_keywords(sentences or _sentence_split(text)[:12], 10)
    return {"methodology_summary": sentences[:5], "keywords": keywords}


async def extract_results(text: str) -> dict[str, Any]:
    sentences = _pick_sentences(text, ["result", "accuracy", "bleu", "f1", "benchmark", "improve", "gain", "dataset"], 8)
    metrics = re.findall(r"\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?\s*(?:f1|bleu|rouge|accuracy)\b", text, re.IGNORECASE)
    return {"result_summary": sentences[:5], "metrics": metrics[:12]}


async def extract_limitations(text: str) -> list[str]:
    limitations = _pick_sentences(text, ["limitation", "future work", "however", "although", "fails", "challenge", "expensive"], 6)
    return limitations or _sentence_split(text)[-3:]


async def compare_papers(papers: list[dict[str, Any]], focus: str = "") -> dict[str, Any]:
    comparison = []
    for paper in papers:
        comparison.append(
            {
                "id": paper.get("id"),
                "title": paper.get("title"),
                "year": paper.get("year"),
                "citation_count": paper.get("citation_count", 0),
                "strengths": _top_keywords([paper.get("abstract", ""), paper.get("relevance_reason", "")], 4),
                "focus_match": focus.lower() in (paper.get("abstract", "") + " " + paper.get("title", "")).lower() if focus else None,
            }
        )
    return {"focus": focus, "comparison": comparison}


async def find_gaps(papers: list[dict[str, Any]], topic: str = "") -> list[str]:
    if not papers:
        return ["No papers available yet, so the first gap is basic literature coverage."]

    years = [paper.get("year") for paper in papers if isinstance(paper.get("year"), int)]
    tags = Counter(tag for paper in papers for tag in paper.get("tags", []) if tag)
    abstracts = " ".join(str(paper.get("abstract", "")) for paper in papers)
    gaps: list[str] = []

    if years and max(years) - min(years) > 5:
        gaps.append(f"The topic spans {min(years)}-{max(years)}, so a timeline analysis is needed to isolate what changed recently.")
    if len(tags) < 3:
        gaps.append("Source coverage is narrow; the literature sample does not yet span multiple subcommunities or venues.")
    if "efficient" not in abstracts.lower():
        gaps.append("Efficiency and deployment trade-offs are underrepresented in the current paper set.")
    if "evaluation" not in abstracts.lower() and "benchmark" not in abstracts.lower():
        gaps.append("Evaluation methodology is not consistently surfaced, so benchmark comparability remains unclear.")
    if topic:
        gaps.append(f"Implementation evidence for '{topic}' should be checked against open-source repos and reproducibility reports.")

    return gaps[:5]


async def timeline_topic(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        year = paper.get("year")
        if isinstance(year, int):
            grouped[year].append(paper)
    return [
        {
            "year": year,
            "paper_count": len(items),
            "top_paper": max(items, key=lambda item: item.get("citation_count", 0)).get("title", ""),
        }
        for year, items in sorted(grouped.items())
    ]


async def generate_report(
    topic: str,
    papers: list[dict[str, Any]],
    citation_links: list[dict[str, Any]] | None = None,
    notes_namespace: str | None = None,
) -> dict[str, Any]:
    clean_papers = _dedupe_papers(papers)
    reading_list = await build_reading_list(clean_papers, max_items=min(8, len(clean_papers) or 8))
    roadmap = await build_implementation_plan(topic, clean_papers)
    gaps = await find_gaps(clean_papers, topic)
    notes = research_store.get_notes(notes_namespace or "default")
    top_titles = ", ".join(paper.get("title", "") for paper in reading_list[:3])
    summary = (
        f"This report surveys {len(clean_papers)} papers related to {topic}. "
        f"The strongest anchors in the current set are {top_titles or 'the retrieved papers'}. "
        f"The literature points to recurring themes around {_top_keywords([paper.get('abstract', '') for paper in clean_papers], 6)}."
    )
    return {
        "summary": summary,
        "papers": clean_papers,
        "citation_links": citation_links or [],
        "gap_analysis": gaps,
        "implementation_roadmap": roadmap,
        "key_concepts": _top_keywords([paper.get("title", "") + " " + paper.get("abstract", "") for paper in clean_papers], 10),
        "notes_used": notes,
    }


async def build_reading_list(papers: list[dict[str, Any]], max_items: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(
        papers,
        key=lambda paper: (float(paper.get("relevance_score") or 0.0), int(paper.get("citation_count") or 0), int(paper.get("year") or 0)),
        reverse=True,
    )
    return ranked[:max_items]


async def build_implementation_plan(topic: str, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    concepts = _top_keywords([paper.get("abstract", "") for paper in papers], 6)
    return [
        {
            "step": "Define the target task",
            "description": f"Turn '{topic}' into a crisp benchmark task, success metric, and acceptance criteria before implementation starts.",
            "difficulty": "easy",
        },
        {
            "step": "Recreate the strongest baseline",
            "description": f"Use the most cited or most relevant paper as the baseline implementation and preserve its core ingredients: {', '.join(concepts[:4]) or 'core method choices'}.",
            "difficulty": "medium",
        },
        {
            "step": "Stress-test data and evaluation",
            "description": "Compare datasets, splits, and evaluation methodology across the literature so improvements are not caused by incomparable setups.",
            "difficulty": "medium",
        },
        {
            "step": "Prototype the novelty",
            "description": "Implement the smallest differentiating experiment suggested by the gap analysis, then ablate the most uncertain design choices.",
            "difficulty": "hard",
        },
    ]


async def generate_bibliography(papers: list[dict[str, Any]], format: str = "bibtex") -> str:
    clean_format = format.lower()
    if clean_format == "json":
        return _safe_json(papers)
    if clean_format == "markdown":
        lines = []
        for paper in papers:
            authors = ", ".join(paper.get("authors", [])[:4]) or "Unknown authors"
            year = paper.get("year") or "n.d."
            lines.append(f"- **{paper.get('title', 'Untitled')}** ({year}) — {authors}. {paper.get('url', '')}")
        return "\n".join(lines)

    entries = []
    for paper in papers:
        key = _paper_to_bibtex_key(paper)
        authors = " and ".join(paper.get("authors", []))
        entries.append(
            "@article{"
            + key
            + ",\n"
            + f"  title = {{{paper.get('title', '')}}},\n"
            + f"  author = {{{authors}}},\n"
            + f"  year = {{{paper.get('year') or ''}}},\n"
            + f"  url = {{{paper.get('url', '')}}},\n"
            + f"  doi = {{{paper.get('doi') or ''}}}\n"
            + "}"
        )
    return "\n\n".join(entries)


async def citation_check(summary: str, papers: list[dict[str, Any]]) -> dict[str, Any]:
    sentences = _sentence_split(summary)
    paper_terms = set()
    for paper in papers:
        paper_terms.update(_top_keywords([paper.get("title", ""), paper.get("abstract", "")], 6))

    unsupported = []
    for sentence in sentences:
        normalized = {token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", sentence.lower()) if token not in _COMMON_STOPWORDS}
        if normalized and not normalized.intersection(paper_terms):
            unsupported.append(sentence)

    return {
        "sentence_count": len(sentences),
        "unsupported_sentences": unsupported[:8],
        "supported_ratio": 0.0 if not sentences else round((len(sentences) - len(unsupported)) / len(sentences), 3),
    }


async def plan_research(topic: str, depth: str = "standard") -> dict[str, Any]:
    steps = [
        "Resolve the seed paper or topic into canonical identifiers.",
        "Search multiple scholarly sources and deduplicate results.",
        "Read the most relevant papers and extract methods, results, and limitations.",
        "Map citations, implementation evidence, and open problems.",
        "Synthesize findings into a report and roadmap.",
    ]
    if depth == "deep":
        steps.insert(3, "Expand into references/citations until coverage is broad enough.")
    return {"topic": topic, "depth": depth, "steps": steps}


async def save_note(namespace: str, note: str, key: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    return research_store.save_note(namespace, note, key=key, tags=tags)


async def get_notes(namespace: str) -> list[dict[str, Any]]:
    return research_store.get_notes(namespace)


async def paper_catalog_upsert(namespace: str, papers: list[dict[str, Any]]) -> dict[str, Any]:
    return research_store.upsert_papers(namespace, papers)


async def cache_store(key: str, value: Any) -> dict[str, Any]:
    return research_store.cache_store(key, value)


async def cache_lookup(key: str) -> dict[str, Any]:
    return research_store.cache_lookup(key)


async def source_coverage(papers: list[dict[str, Any]]) -> dict[str, Any]:
    sources = Counter(str(paper.get("source") or "unknown") for paper in papers)
    years = sorted({paper.get("year") for paper in papers if isinstance(paper.get("year"), int)})
    return {
        "paper_count": len(papers),
        "sources": dict(sources),
        "year_span": [years[0], years[-1]] if years else [],
        "sufficient": len(papers) >= 6 and len(sources) >= 2,
    }


async def budget_status(session_id: str, max_tool_calls: int = 12) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        return {"session_id": session_id, "error": "unknown session"}

    tool_logs = [log for log in session.progress.logs if log.message.startswith("Using tool:")]
    return {
        "session_id": session_id,
        "status": session.status,
        "tool_calls_used": len(tool_logs),
        "max_tool_calls": max_tool_calls,
        "remaining_tool_calls": max(0, max_tool_calls - len(tool_logs)),
        "progress_percentage": session.progress.percentage,
        "log_count": len(session.progress.logs),
    }


async def quality_review(report: dict[str, Any], papers: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    if not report.get("summary"):
        issues.append("Missing executive summary.")
    if len(papers) < 5:
        issues.append("Fewer than 5 papers in the evidence base.")
    if not report.get("gap_analysis"):
        issues.append("No gap analysis provided.")
    if not report.get("implementation_roadmap"):
        issues.append("No implementation roadmap provided.")
    citation_status = await citation_check(str(report.get("summary", "")), papers)
    if citation_status.get("supported_ratio", 0) < 0.4:
        issues.append("Summary appears weakly grounded in the retrieved paper set.")
    return {"issues": issues, "ready_for_user": not issues, "citation_status": citation_status}


async def fetch_url(url: str, max_chars: int = 8000) -> dict[str, Any]:
    """
    Fetch the text content of any public URL — GitHub raw files, READMEs, docs.

    For github.com URLs, automatically rewrites to raw.githubusercontent.com so
    the agent gets plain text instead of HTML.  Returns the first *max_chars*
    characters of the response body.
    """
    # Rewrite GitHub blob URLs → raw content
    raw_url = url
    gh_blob = re.match(
        r"https://github\.com/([^/]+/[^/]+)/blob/([^/]+)/(.*)", url
    )
    if gh_blob:
        raw_url = f"https://raw.githubusercontent.com/{gh_blob.group(1)}/{gh_blob.group(2)}/{gh_blob.group(3)}"

    # Rewrite github.com/<owner>/<repo> (root) → raw README
    gh_root = re.match(r"https://github\.com/([^/]+/[^/]+?)/?$", url)
    if gh_root and not gh_blob:
        # Try to fetch README via GitHub API
        api_url = f"https://api.github.com/repos/{gh_root.group(1)}/readme"
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    api_url,
                    headers={"Accept": "application/vnd.github.raw", "User-Agent": "ali_researcher/1.0"},
                )
                if resp.status_code == 200:
                    content = resp.text[:max_chars]
                    return {"url": url, "content": content, "chars": len(content), "source": "github_readme"}
        except Exception:
            pass  # fall through to generic fetch

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                raw_url,
                headers={"User-Agent": "ali_researcher/1.0"},
            )
            resp.raise_for_status()
            text = resp.text[:max_chars]
            return {"url": raw_url, "content": text, "chars": len(text), "status_code": resp.status_code}
    except Exception as exc:
        return {"url": raw_url, "content": "", "chars": 0, "error": str(exc)}


async def search_session_memory(query: str, limit: int = 10) -> dict[str, Any]:
    """Search papers seen in previous research sessions stored in PostgreSQL."""
    results = await _db.search_papers_memory(query, limit=limit)
    return {
        "query": query,
        "total_found": len(results),
        "papers": results,
        "note": "These papers were collected in prior sessions — use them to avoid re-fetching known sources.",
    }


async def compact_context(text: str, max_chars: int = 4000) -> dict[str, Any]:
    sentences = _sentence_split(text)
    summary = " ".join(sentences[: min(len(sentences), 12)])
    compacted = _truncate(summary, max_chars)
    return {"original_chars": len(text), "summary": compacted, "compressed_chars": len(compacted)}


def _tool_spec(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


TOOL_SPECS: list[dict[str, Any]] = [
    _tool_spec("search_arxiv", "Search arXiv for academic papers. Use sort_by='recent' to get newest papers first. Use year_from to restrict to papers from a given year onwards.", {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 10}, "sort_by": {"type": "string", "enum": ["relevance", "recent"], "default": "relevance"}, "year_from": {"type": "integer", "description": "Only return papers from this year onwards (e.g. 2022)"}}, ["query"]),
    _tool_spec("get_arxiv_paper", "Fetch a specific paper from arXiv by ID.", {"arxiv_id": {"type": "string"}}, ["arxiv_id"]),
    _tool_spec("search_semantic_scholar", "Search Semantic Scholar for academic papers. Use year_from to restrict results to recent papers.", {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 10}, "year_from": {"type": "integer", "description": "Only return papers from this year onwards (e.g. 2022)"}}, ["query"]),
    _tool_spec("get_paper_citations", "Fetch papers that cite a given Semantic Scholar paper ID — these are NEWER papers that built on this work.", {"paper_id": {"type": "string"}, "source": {"type": "string", "default": "semantic_scholar"}, "max_results": {"type": "integer", "default": 25}}, ["paper_id"]),
    _tool_spec("get_references", "Fetch references for a given Semantic Scholar paper ID — these are OLDER papers cited by this work.", {"paper_id": {"type": "string"}, "source": {"type": "string", "default": "semantic_scholar"}, "max_results": {"type": "integer", "default": 25}}, ["paper_id"]),
    _tool_spec("get_related_papers", "Find semantically similar papers using Semantic Scholar recommendations — ideal for discovering recent follow-up work. Returns results sorted by year descending.", {"paper_id": {"type": "string", "description": "Semantic Scholar paper ID or arXiv ID"}, "year_from": {"type": "integer", "description": "Only include papers from this year onwards"}, "max_results": {"type": "integer", "default": 15}}, ["paper_id"]),
    _tool_spec("search_web", "Search the web for tutorials, news, and supplementary information.", {"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
    _tool_spec("search_google_scholar", "Search Google Scholar for academic papers — use this for citation counts, related work, and papers not on arXiv.", {"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
    _tool_spec("search_code", "Search GitHub repositories for implementations and code resources.", {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 10}}, ["query"]),
    _tool_spec("parse_pdf", "Parse a local PDF path or PDF URL and extract text, sections, and references.", {"source": {"type": "string"}, "max_pages": {"type": "integer", "default": 12}}, ["source"]),
    _tool_spec("resolve_paper_id", "Resolve a DOI, arXiv URL, DOI URL, or title-like string into a canonical paper record.", {"identifier": {"type": "string"}}, ["identifier"]),
    _tool_spec("search_papers", "Aggregate multiple academic paper sources and deduplicate results.", {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 12}}, ["query"]),
    _tool_spec("get_paper_metadata", "Fetch metadata for a paper from arXiv or Semantic Scholar.", {"paper_id": {"type": "string"}, "source": {"type": "string", "default": "auto"}}, ["paper_id"]),
    _tool_spec("extract_claims", "Extract likely headline claims from text.", {"text": {"type": "string"}, "max_claims": {"type": "integer", "default": 5}}, ["text"]),
    _tool_spec("extract_methodology", "Extract methodology-oriented summary points from text.", {"text": {"type": "string"}}, ["text"]),
    _tool_spec("extract_results", "Extract results and metrics from text.", {"text": {"type": "string"}}, ["text"]),
    _tool_spec("extract_limitations", "Extract limitations and future-work style caveats from text.", {"text": {"type": "string"}}, ["text"]),
    _tool_spec("compare_papers", "Compare a set of papers by year, citations, and abstract-derived strengths.", {"papers": {"type": "array", "items": {"type": "object"}}, "focus": {"type": "string"}}, ["papers"]),
    _tool_spec("find_gaps", "Infer research gaps from a set of papers.", {"papers": {"type": "array", "items": {"type": "object"}}, "topic": {"type": "string"}}, ["papers"]),
    _tool_spec("timeline_topic", "Build a year-by-year topic timeline from a set of papers.", {"papers": {"type": "array", "items": {"type": "object"}}}, ["papers"]),
    _tool_spec("generate_report", "Generate a draft structured research report from collected evidence.", {"topic": {"type": "string"}, "papers": {"type": "array", "items": {"type": "object"}}, "citation_links": {"type": "array", "items": {"type": "object"}}, "notes_namespace": {"type": "string"}}, ["topic", "papers"]),
    _tool_spec("build_reading_list", "Create a ranked reading list from collected papers.", {"papers": {"type": "array", "items": {"type": "object"}}, "max_items": {"type": "integer"}}, ["papers"]),
    _tool_spec("build_implementation_plan", "Create a practical implementation plan from a topic and paper set.", {"topic": {"type": "string"}, "papers": {"type": "array", "items": {"type": "object"}}}, ["topic", "papers"]),
    _tool_spec("generate_bibliography", "Export collected papers as BibTeX, Markdown, or JSON.", {"papers": {"type": "array", "items": {"type": "object"}}, "format": {"type": "string"}}, ["papers"]),
    _tool_spec("citation_check", "Check whether a summary appears grounded in the supplied papers.", {"summary": {"type": "string"}, "papers": {"type": "array", "items": {"type": "object"}}}, ["summary", "papers"]),
    _tool_spec("plan_research", "Create a step-by-step research plan for a topic.", {"topic": {"type": "string"}, "depth": {"type": "string"}}, ["topic"]),
    _tool_spec("save_note", "Save a persistent research note inside the in-memory store.", {"namespace": {"type": "string"}, "note": {"type": "string"}, "key": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, ["namespace", "note"]),
    _tool_spec("get_notes", "Read previously saved research notes for a namespace.", {"namespace": {"type": "string"}}, ["namespace"]),
    _tool_spec("paper_catalog_upsert", "Insert or update papers inside the research catalog.", {"namespace": {"type": "string"}, "papers": {"type": "array", "items": {"type": "object"}}}, ["namespace", "papers"]),
    _tool_spec("cache_store", "Store arbitrary JSON-serialisable values in the research cache.", {"key": {"type": "string"}, "value": {"type": "string"}}, ["key", "value"]),
    _tool_spec("cache_lookup", "Look up a value from the research cache.", {"key": {"type": "string"}}, ["key"]),
    _tool_spec("source_coverage", "Measure the breadth of source and year coverage in a paper set.", {"papers": {"type": "array", "items": {"type": "object"}}}, ["papers"]),
    _tool_spec("budget_status", "Inspect current tool-call budget and progress for a session.", {"session_id": {"type": "string"}, "max_tool_calls": {"type": "integer"}}, ["session_id"]),
    _tool_spec("quality_review", "Perform a deterministic quality check over a draft report.", {"report": {"type": "object"}, "papers": {"type": "array", "items": {"type": "object"}}}, ["report", "papers"]),
    _tool_spec("compact_context", "Compress long text into a smaller summary payload.", {"text": {"type": "string"}, "max_chars": {"type": "integer"}}, ["text"]),
    _tool_spec("search_session_memory", "Search papers seen in prior research sessions (cross-session memory). Call this early to avoid re-fetching known sources.", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, ["query"]),
    _tool_spec("fetch_url", "Fetch the text content of any public URL — GitHub READMEs, raw source files, docs pages. Auto-rewrites GitHub blob URLs to raw content.", {"url": {"type": "string"}, "max_chars": {"type": "integer", "default": 8000}}, ["url"]),
]


_TOOL_MAP = {
    "search_arxiv": search_arxiv,
    "get_arxiv_paper": get_arxiv_paper,
    "search_semantic_scholar": search_semantic_scholar,
    "get_paper_citations": get_paper_citations,
    "get_references": get_references,
    "get_related_papers": get_related_papers,
    "search_web": search_web,
    "search_google_scholar": search_google_scholar,
    "search_code": search_code,
    "parse_pdf": parse_pdf,
    "resolve_paper_id": resolve_paper_id,
    "search_papers": search_papers,
    "get_paper_metadata": get_paper_metadata,
    "extract_claims": extract_claims,
    "extract_methodology": extract_methodology,
    "extract_results": extract_results,
    "extract_limitations": extract_limitations,
    "compare_papers": compare_papers,
    "find_gaps": find_gaps,
    "timeline_topic": timeline_topic,
    "generate_report": generate_report,
    "build_reading_list": build_reading_list,
    "build_implementation_plan": build_implementation_plan,
    "generate_bibliography": generate_bibliography,
    "citation_check": citation_check,
    "plan_research": plan_research,
    "save_note": save_note,
    "get_notes": get_notes,
    "paper_catalog_upsert": paper_catalog_upsert,
    "cache_store": cache_store,
    "cache_lookup": cache_lookup,
    "source_coverage": source_coverage,
    "budget_status": budget_status,
    "quality_review": quality_review,
    "compact_context": compact_context,
    "search_session_memory": search_session_memory,
    "fetch_url": fetch_url,
}


async def execute_tool(name: str, input_data: dict[str, Any]) -> str:
    fn = _TOOL_MAP.get(name)
    if fn is None:
        raise ValueError(f"Unknown tool: {name!r}")
    result = await fn(**input_data)
    return _safe_json(result)
