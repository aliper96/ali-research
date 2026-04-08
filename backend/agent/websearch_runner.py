"""
Perplexity-like web search runner — powered by SearXNG (no API keys).

Flow:
1. Generate 3-5 search queries from the user question via LLM
2. Search the web via SearXNG (local instance or public fallback)
3. Fetch full page content from the top results using a smart strategy:
   - DIRECT_ONLY domains (GitHub, arXiv, Wikipedia, docs…): httpx + trafilatura, no Jina
   - JINA_PREFERRED domains (Reddit, Medium, SPAs…): Jina first, direct as fallback
   - Unknown domains: try direct first; if content is thin, Jina as fallback
4. LLM synthesizes a comprehensive structured answer with inline [N] citations
   in the SAME LANGUAGE as the user's question
5. Returns WebSearchResult with answer, sources, follow-up questions
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from urllib.parse import urlparse

import httpx
import openai

from ..models.websearch_schemas import WebSearchResult, WebSource
from ..storage.websearch_store import websearch_store

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 4000   # chars per source passed to LLM
_MAX_SNIPPET_CHARS = 600    # fallback when page fetch fails
_JINA_MIN_CHARS   = 200     # Jina result is considered "failed" below this
_DIRECT_GOOD_CHARS = 500    # direct result is considered "good enough" above this

# ---------------------------------------------------------------------------
# Jina routing policy
# ---------------------------------------------------------------------------

# These domains return good content via plain httpx — never waste Jina on them.
_DIRECT_ONLY_DOMAINS: frozenset[str] = frozenset({
    # GitHub — handled via blob→raw rewrite + direct fetch
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "gist.github.com",
    # arXiv / academic papers
    "arxiv.org",
    "export.arxiv.org",
    "ar5iv.labs.arxiv.org",
    # Wikipedia
    "en.wikipedia.org",
    "es.wikipedia.org",
    "fr.wikipedia.org",
    "de.wikipedia.org",
    "wikipedia.org",
    # Official docs (static HTML)
    "developer.mozilla.org",
    "docs.python.org",
    "docs.rs",              # Rust docs
    "pkg.go.dev",           # Go docs
    "nodejs.org",
    "kotlinlang.org",
    "docs.oracle.com",
    "cppreference.com",
    "learn.microsoft.com",
    # Package registries
    "pypi.org",
    "npmjs.com",
    "crates.io",
    # HuggingFace (model cards are static)
    "huggingface.co",
    # Stack Overflow / Stack Exchange
    "stackoverflow.com",
    "stackexchange.com",
    "superuser.com",
    "serverfault.com",
    # Papers / journals
    "semanticscholar.org",
    "paperswithcode.com",
    "aclanthology.org",
    "openreview.net",
})

# These domains need JavaScript rendering — go straight to Jina, skip direct.
_JINA_PREFERRED_DOMAINS: frozenset[str] = frozenset({
    "reddit.com",
    "old.reddit.com",
    "new.reddit.com",
    "medium.com",
    "towardsdatascience.com",
    "betterprogramming.pub",
    "levelup.gitconnected.com",
    "substack.com",
    "hackernoon.com",
    "dev.to",
    "hashnode.com",
    "notion.site",
    "notion.so",
})


def _normalize_domain(url: str) -> str:
    """Return the bare domain, stripping www. and any subpath."""
    try:
        host = urlparse(url).netloc.lower()
        return host.removeprefix("www.")
    except Exception:
        return ""


def _rewrite_github_url(url: str) -> str:
    """
    Convert github.com blob/tree URLs to raw.githubusercontent.com so we can
    fetch the actual file content instead of the rendered HTML wrapper.

    github.com/<owner>/<repo>/blob/<branch>/<path>
      → raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>
    """
    blob_match = re.match(
        r"https?://github\.com/([^/]+/[^/]+)/blob/([^?#]+)",
        url,
        re.IGNORECASE,
    )
    if blob_match:
        repo_path = blob_match.group(1)
        file_path = blob_match.group(2)
        return f"https://raw.githubusercontent.com/{repo_path}/{file_path}"
    return url


def _is_direct_only(domain: str) -> bool:
    """True if this domain should NEVER use Jina."""
    if domain in _DIRECT_ONLY_DOMAINS:
        return True
    # Catch all *.wikipedia.org, *.github.io, etc.
    if domain.endswith((".wikipedia.org", ".github.io", ".arxiv.org")):
        return True
    # Catch all substack personal sites (<blog>.substack.com handled separately)
    return False


def _is_jina_preferred(domain: str) -> bool:
    """True if this domain is known to need JS rendering."""
    if domain in _JINA_PREFERRED_DOMAINS:
        return True
    # Personal substack blogs: <anything>.substack.com
    if domain.endswith(".substack.com"):
        return True
    return False

_SEARXNG_INSTANCES = [
    os.environ.get("SEARXNG_URL", ""),  # local instance if configured
    "https://searxng.world",
    "https://searx.be",
    "https://search.mdosch.de",
]

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Alias kept for the SearXNG result builder — delegates to _normalize_domain."""
    return _normalize_domain(url)


def _strip_html(html: str) -> str:
    """Minimal HTML → plain text. Used only when trafilatura is unavailable."""
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_with_trafilatura(html: str, url: str) -> str:
    """Use trafilatura for clean article extraction when available."""
    try:
        import trafilatura  # type: ignore
        result = trafilatura.extract(
            html,
            url=url,
            include_links=False,
            include_images=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
        )
        return result or ""
    except ImportError:
        return _strip_html(html)
    except Exception:
        return _strip_html(html)


async def _fetch_via_jina(url: str) -> str:
    """
    Fetch a page via Jina Reader (r.jina.ai).
    Renders JavaScript server-side and returns clean markdown.
    Free tier: ~200 req/day per IP.
    With JINA_API_KEY in .env: no rate limit (paid, very cheap).
    """
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "text/plain, text/markdown",
        "X-Return-Format": "markdown",
        "User-Agent": "ali_researcher/1.0",
    }
    api_key = os.environ.get("JINA_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = await client.get(jina_url)
            resp.raise_for_status()
            return resp.text.strip()[:_MAX_CONTENT_CHARS]
    except Exception as exc:
        logger.debug("Jina Reader failed for %s: %s", url, exc)
        return ""


async def _fetch_direct(url: str) -> str:
    """
    Direct httpx fetch + trafilatura extraction.
    Also handles JSON responses (GitHub API, package registries, etc.)
    by pretty-printing them as readable text.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers=_FETCH_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "json" in ct or url.startswith("https://api.github.com"):
                # Pretty-print JSON (GitHub API, npm registry, etc.)
                try:
                    data = resp.json()
                    return json.dumps(data, indent=2, ensure_ascii=False)[:_MAX_CONTENT_CHARS]
                except Exception:
                    return resp.text[:_MAX_CONTENT_CHARS]
            if "html" not in ct and "text" not in ct:
                return ""
            text = await asyncio.to_thread(_extract_with_trafilatura, resp.text, url)
            return text[:_MAX_CONTENT_CHARS]
    except Exception as exc:
        logger.debug("Direct fetch failed %s: %s", url, exc)
        return ""


async def _fetch_page(url: str) -> str:
    """
    Smart fetch strategy — picks the right tool for each domain:

    DIRECT_ONLY  (GitHub, arXiv, Wikipedia, official docs, SO):
        → plain httpx + trafilatura.  Never touches Jina.

    JINA_PREFERRED  (Reddit, Medium, Substack, SPAs):
        → Jina first.  Falls back to direct if Jina returns < _JINA_MIN_CHARS.

    UNKNOWN domains:
        → direct first (fast, free).
          If result is thin (< _DIRECT_GOOD_CHARS), try Jina as fallback.
          Return whichever is longer.
    """
    # Step 0: rewrite GitHub blob URLs → raw content before anything
    original_url = url
    url = _rewrite_github_url(url)
    domain = _normalize_domain(url)
    if not domain:
        domain = _normalize_domain(original_url)

    logger.debug("_fetch_page domain=%s url=%s", domain, url)

    # ── Direct-only domains ────────────────────────────────────────────────
    if _is_direct_only(domain):
        return await _fetch_direct(url)

    # ── Jina-preferred domains ─────────────────────────────────────────────
    if _is_jina_preferred(domain):
        jina_text = await _fetch_via_jina(url)
        if len(jina_text) >= _JINA_MIN_CHARS:
            return jina_text
        # Jina was poor — try direct as safety net
        logger.debug("Jina-preferred %s returned little (%d chars), falling back to direct", domain, len(jina_text))
        direct_text = await _fetch_direct(url)
        return direct_text if len(direct_text) >= len(jina_text) else jina_text

    # ── Unknown domain: direct → Jina fallback ────────────────────────────
    direct_text = await _fetch_direct(url)
    if len(direct_text) >= _DIRECT_GOOD_CHARS:
        # Direct gave plenty of content — no need for Jina
        return direct_text

    # Direct was thin (JS-heavy page, paywall, empty HTML, etc.) — try Jina
    logger.debug("Direct fetch thin (%d chars) for %s — trying Jina fallback", len(direct_text), domain)
    jina_text = await _fetch_via_jina(url)
    return jina_text if len(jina_text) > len(direct_text) else direct_text


# ---------------------------------------------------------------------------
# SearXNG search
# ---------------------------------------------------------------------------

async def _searxng_search(query: str, max_results: int = 8) -> list[WebSource]:
    params = {
        "q": query,
        "format": "json",
        "engines": "google,bing,duckduckgo",
        "categories": "general",
    }
    headers = {"User-Agent": "ali_researcher/1.0"}

    for instance in _SEARXNG_INSTANCES:
        if not instance:
            continue
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(f"{instance}/search", params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            results = data.get("results", [])[:max_results]
            return [
                WebSource(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", "")[:_MAX_SNIPPET_CHARS],
                    content="",
                    domain=_extract_domain(r.get("url", "")),
                    published_date=r.get("publishedDate"),
                )
                for r in results
                if r.get("url")
            ]
        except Exception as exc:
            logger.debug("SearXNG %s failed: %s — trying next", instance, exc)

    logger.warning("All SearXNG instances failed for: %s", query)
    return []


async def _search_and_fetch(query: str, max_results: int = 6) -> list[WebSource]:
    """Search SearXNG then fetch content from all results in parallel."""
    sources = await _searxng_search(query, max_results=max_results)
    if not sources:
        return []
    contents = await asyncio.gather(*[_fetch_page(s.url) for s in sources])
    for source, content in zip(sources, contents):
        # If page fetch failed (JS-rendered, blocked, etc.) keep the snippet
        source.content = content if content.strip() else source.snippet
    return sources


# ---------------------------------------------------------------------------
# Deduplication — by URL only (NOT by domain)
# Multiple pages from github.com, reddit.com, etc. are all valuable
# ---------------------------------------------------------------------------

def _deduplicate(sources: list[WebSource]) -> list[WebSource]:
    seen_urls: set[str] = set()
    out: list[WebSource] = []
    for s in sources:
        if s.url in seen_urls:
            continue
        seen_urls.add(s.url)
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# Query generation
# Generate queries in English for better search coverage,
# but tell the synthesizer to answer in the user's language.
# ---------------------------------------------------------------------------

_QUERY_GEN_PROMPT = (
    "You are a search query expert.\n\n"
    "Given the user's question, generate 3-5 diverse search queries that together "
    "fully cover all aspects needed to answer it.\n\n"
    "Rules:\n"
    "- Generate queries in English (best for search engines) even if the question "
    "is in another language — the answer will be translated back.\n"
    "- Be specific and use technical terms.\n"
    "- Include the current year ({year}) for time-sensitive topics.\n"
    "- For GitHub/code questions, include 'github', 'open source', 'repository'.\n\n"
    "Return ONLY a JSON array of strings:\n"
    '[\"query 1\", \"query 2\", \"query 3\"]'
)


async def _generate_queries(client: openai.AsyncOpenAI, model: str, question: str) -> list[str]:
    from datetime import date
    year = date.today().year
    try:
        resp = await client.chat.completions.create(
            model=model,
            max_completion_tokens=400,
            messages=[
                {"role": "system", "content": _QUERY_GEN_PROMPT.format(year=year)},
                {"role": "user", "content": question},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            queries = json.loads(match.group())
            if isinstance(queries, list) and queries:
                return [str(q) for q in queries[:5]]
    except Exception as exc:
        logger.warning("Query generation failed: %s", exc)
    return [question]


# ---------------------------------------------------------------------------
# Answer synthesis
# ---------------------------------------------------------------------------

_SYNTHESIS_PROMPT = """\
You are a sharp, opinionated research assistant — like a knowledgeable friend who just did the research for you.
Synthesize a direct, useful answer from the web sources provided.

CRITICAL RULES:
1. **ALWAYS respond in the EXACT SAME LANGUAGE as the user's question.** \
If the question is in Spanish, answer in Spanish. If in English, answer in English. Never change the language.
2. Cite every factual claim inline as [1], [2], etc. (1-based, matching the source list).
3. **Be opinionated and direct**: say "X is the best option if..." not just "X exists".
4. Lead with a one-sentence summary of the best answer, then go into detail.
5. Use markdown for structure: ### headers, bullet lists, **bold** for key terms, `code` for repo names/commands.
6. Be specific — name actual tools, repos, GitHub URLs, versions, formats mentioned in sources.
7. End with a short paragraph offering to help further based on the user's specific case.
8. Do not hallucinate — only state what sources support. If a source has little content, use its title/snippet.
9. Suggest 3 short follow-up questions in the same language as the question.

Return ONLY this JSON (no other text):
{"answer": "your direct markdown answer with [N] citations", \
"follow_up_questions": ["Q1?", "Q2?", "Q3?"]}"""


def _build_context(sources: list[WebSource]) -> str:
    parts = []
    for i, s in enumerate(sources, 1):
        body = s.content or s.snippet
        parts.append(
            f"[{i}] TITLE: {s.title}\n"
            f"URL: {s.url}\n"
            f"DOMAIN: {s.domain}\n"
            f"CONTENT:\n{body[:_MAX_CONTENT_CHARS]}"
        )
    return "\n\n---\n\n".join(parts)


async def _synthesize(
    client: openai.AsyncOpenAI,
    model: str,
    question: str,
    sources: list[WebSource],
) -> tuple[str, list[str]]:
    try:
        resp = await client.chat.completions.create(
            model=model,
            max_completion_tokens=4000,
            messages=[
                {"role": "system", "content": _SYNTHESIS_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User question (answer in THIS language): {question}\n\n"
                        f"Sources:\n{_build_context(sources)}"
                    ),
                },
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        # Extract JSON — handle possible markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            data = json.loads(match.group())
            return (
                str(data.get("answer", text)),
                [str(q) for q in data.get("follow_up_questions", [])],
            )
        return text, []
    except Exception as exc:
        logger.error("Synthesis failed: %s", exc)
        return "Unable to synthesize an answer from the retrieved sources.", []


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_websearch(
    session_id: str,
    user_input: str,
    recency: str = "any",
) -> None:
    model = os.getenv("LLM_MODEL", "gpt-5.4-nano")
    client = openai.AsyncOpenAI()

    async def _log(msg: str, level: str = "info") -> None:
        await websearch_store.add_log(session_id, msg, level)

    try:
        await _log(f"Starting web search: {user_input}", "info")
        await websearch_store.set_progress(session_id, 5)

        # 1. Generate English search queries
        await _log("Generating search queries…", "info")
        queries = await _generate_queries(client, model, user_input)
        await _log(f"Queries: {' | '.join(queries)}", "info")
        await websearch_store.set_progress(session_id, 15)

        # 2. Search + fetch in parallel
        await _log(f"Searching ({len(queries)} queries) + fetching page content…", "info")
        results_per_query = await asyncio.gather(
            *[_search_and_fetch(q, max_results=6) for q in queries]
        )

        all_sources: list[WebSource] = []
        for sources in results_per_query:
            all_sources.extend(sources)

        all_sources = _deduplicate(all_sources)
        await _log(f"Found {len(all_sources)} unique sources", "success")
        await websearch_store.set_progress(session_id, 60)

        if not all_sources:
            await _log("No sources found — SearXNG may be unavailable", "warning")
            session = websearch_store.get_session(session_id)
            if session:
                session.result = WebSearchResult(
                    answer="No results found. SearXNG may be temporarily unavailable — try again in a moment.",
                    sources=[],
                    follow_up_questions=[],
                    queries_used=queries,
                )
                session.status = "completed"
                await websearch_store.update_session(session)
            return

        # 3. Synthesize answer (top 10 sources)
        await _log("Synthesizing answer…", "info")
        await websearch_store.set_progress(session_id, 75)

        top_sources = all_sources[:10]
        answer, follow_ups = await _synthesize(client, model, user_input, top_sources)
        await websearch_store.set_progress(session_id, 95)

        # 4. Save result
        session = websearch_store.get_session(session_id)
        if session:
            session.result = WebSearchResult(
                answer=answer,
                sources=top_sources,
                follow_up_questions=follow_ups,
                queries_used=queries,
            )
            session.status = "completed"
            await websearch_store.update_session(session)

        await _log("Web search complete", "success")
        await websearch_store.set_progress(session_id, 100)

    except Exception as exc:
        logger.exception("run_websearch failed %s: %s", session_id, exc)
        session = websearch_store.get_session(session_id)
        if session:
            session.status = "error"
            await websearch_store.update_session(session)
        await _log(f"Fatal error: {exc}", "error")
    finally:
        await websearch_store.notify_complete(session_id)
