"""
Main agentic research loop for ali_researcher.

``run_research`` drives a multi-turn Claude conversation that uses the
research tools defined in ``tools.py``, then parses the final JSON report
into a ``ResearchResult``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import os

import openai

from ..models.schemas import CitationLink, Paper, ResearchResult, RoadmapStep
from ..storage.session_store import session_store
from ..storage.graph_store import graph_store
from ..storage import db as _db
from ..storage.artifact_store import save_research_artifacts
from .tools import TOOL_SPECS, execute_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert academic researcher. Given a paper or topic, you will:
1. Resolve the seed topic or identifier into a canonical paper/query when possible
2. Search for the most relevant papers using scholarly and web/code tools
3. Extract methodology, results, limitations, references, and citation relationships
4. Track coverage, budget, and notes when useful
5. Synthesize your findings into a comprehensive research report

You have access to tools for:
- paper retrieval: search_arxiv, get_arxiv_paper, search_semantic_scholar, search_google_scholar, search_papers, get_paper_metadata, get_references, get_paper_citations, resolve_paper_id
- supplemental sources: search_web, search_code, parse_pdf
- analysis: extract_claims, extract_methodology, extract_results, extract_limitations, compare_papers, find_gaps, timeline_topic, citation_check, quality_review, compact_context
- synthesis/planning: plan_research, generate_report, build_reading_list, build_implementation_plan, generate_bibliography
- memory/state: save_note, get_notes, paper_catalog_upsert, cache_store, cache_lookup, source_coverage, budget_status
- cross-session: search_session_memory (searches papers from ALL prior research sessions — call this FIRST to find known sources before searching APIs)

── TARGET PAPER COUNTS (MANDATORY) ────────────────────────────────────────────
quick: at least 5 papers | standard: at least 10 papers | deep: at least 20 papers

You MUST reach the target before writing the final JSON. If you are below target,
run more searches with different query formulations — do NOT synthesise too early.

── QUERY EXPANSION FOR NICHE / COMPOUND TOPICS ────────────────────────────────
When a topic is a compound word, acronym, or very specific term that returns < 5
results, you MUST try multiple alternative formulations. Examples:

  "LEARNHEURISTICS"  → "learning heuristics", "learned heuristics",
                        "heuristic learning", "neural heuristics",
                        "machine learning metaheuristics", "deep learning combinatorial optimization"

  "GNNs for routing" → "graph neural network vehicle routing",
                        "GNN combinatorial optimization", "deep learning TSP"

Rules for query expansion:
1. Break compound words into components and search each variation.
2. Try synonyms, parent categories, and closely related fields.
3. If a term sounds like an acronym or a niche system name, also search for it
   on Semantic Scholar and with search_web to find the defining paper.
4. Do NOT declare "no papers found" after a single query — always try 3–5
   reformulations before concluding a topic is truly uncovered.
5. Use get_references / get_paper_citations on any paper you DO find to discover
   related works that might not appear in direct keyword searches.

── PREFERRED WORKFLOW ──────────────────────────────────────────────────────────
1. search_session_memory — check prior sessions first
2. plan_research — list 3–5 query variations you will use
3. search_papers (primary query) + search_semantic_scholar or search_google_scholar
4. If result count < target: run search_arxiv / search_papers with 2–3 alternative queries
5. get_references + get_paper_citations on the top 2–3 papers found
6. get_paper_metadata / parse_pdf for the most important papers
7. analysis tools (find_gaps, extract_methodology) on best texts
8. final synthesis into the required JSON

── PROVENANCE FIELDS ───────────────────────────────────────────────────────────
- "source": "arxiv" | "semantic_scholar" | "google_scholar" | "web" | "crossref"
- "read_status": "full_text" | "abstract_only" | "inferred"
- "venue": conference/journal name if known, null if unknown

At the end, you MUST return a JSON object with this exact structure (and nothing else after it):
{
  "summary": "2-3 paragraph executive summary",
  "papers": [
    {
      "id": "unique_id",
      "title": "Paper title",
      "authors": ["Author One", "Author Two"],
      "year": 2023,
      "abstract": "Paper abstract...",
      "url": "https://...",
      "arxiv_id": "2301.00001",
      "doi": null,
      "relevance_score": 0.95,
      "relevance_reason": "Why this paper is relevant",
      "citation_count": 150,
      "tags": ["cs.LG", "cs.AI"],
      "source": "arxiv",
      "read_status": "full_text",
      "venue": "NeurIPS 2023"
    }
  ],
  "citation_links": [{"source": "paper_id_1", "target": "paper_id_2"}],
  "gap_analysis": ["Research gap 1", "Research gap 2"],
  "implementation_roadmap": [
    {"step": "Step name", "description": "Detailed description", "difficulty": "easy"}
  ],
  "key_concepts": ["concept1", "concept2"]
}"""

# ---------------------------------------------------------------------------
# Result parser
# ---------------------------------------------------------------------------

def _coerce_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _coerce_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _coerce_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return str(val)


def _coerce_list_of_str(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x) for x in val if x is not None]


def parse_result(data: dict, session_id: str) -> ResearchResult:
    """
    Safely construct a ``ResearchResult`` from raw LLM JSON output.

    Every field is coerced defensively so a malformed response never raises
    an unhandled exception.
    """
    # --- papers ---
    papers: list[Paper] = []
    for raw in data.get("papers", []):
        if not isinstance(raw, dict):
            continue
        try:
            score = _coerce_float(raw.get("relevance_score"), 0.5)
            score = max(0.0, min(1.0, score))
            valid_sources = {"arxiv", "semantic_scholar", "google_scholar", "web", "crossref"}
            valid_read_statuses = {"full_text", "abstract_only", "inferred"}
            raw_source = _coerce_str(raw.get("source")).lower() or None
            raw_read_status = _coerce_str(raw.get("read_status")).lower() or None
            paper = Paper(
                id=_coerce_str(raw.get("id"), f"paper_{len(papers)}"),
                title=_coerce_str(raw.get("title"), "Untitled"),
                authors=_coerce_list_of_str(raw.get("authors")),
                year=_coerce_int(raw.get("year"), 0) or None,
                abstract=_coerce_str(raw.get("abstract")),
                url=_coerce_str(raw.get("url")),
                arxiv_id=_coerce_str(raw.get("arxiv_id")) or None,
                doi=_coerce_str(raw.get("doi")) or None,
                relevance_score=score,
                relevance_reason=_coerce_str(raw.get("relevance_reason")),
                citation_count=_coerce_int(raw.get("citation_count")),
                tags=_coerce_list_of_str(raw.get("tags")),
                source=raw_source if raw_source in valid_sources else None,  # type: ignore[arg-type]
                read_status=raw_read_status if raw_read_status in valid_read_statuses else None,  # type: ignore[arg-type]
                venue=_coerce_str(raw.get("venue")) or None,
            )
            papers.append(paper)
        except Exception as exc:
            logger.warning("Skipping malformed paper entry: %s", exc)

    # --- citation_links ---
    citation_links: list[CitationLink] = []
    for raw in data.get("citation_links", []):
        if not isinstance(raw, dict):
            continue
        try:
            src = _coerce_str(raw.get("source"))
            tgt = _coerce_str(raw.get("target"))
            if src and tgt and src != tgt:
                citation_links.append(CitationLink(source=src, target=tgt))
        except Exception as exc:
            logger.warning("Skipping malformed citation link: %s", exc)

    # --- implementation_roadmap ---
    roadmap: list[RoadmapStep] = []
    valid_difficulties = {"easy", "medium", "hard"}
    for raw in data.get("implementation_roadmap", []):
        if not isinstance(raw, dict):
            continue
        try:
            difficulty = _coerce_str(raw.get("difficulty"), "medium").lower()
            if difficulty not in valid_difficulties:
                difficulty = "medium"
            roadmap.append(
                RoadmapStep(
                    step=_coerce_str(raw.get("step"), "Step"),
                    description=_coerce_str(raw.get("description")),
                    difficulty=difficulty,  # type: ignore[arg-type]
                )
            )
        except Exception as exc:
            logger.warning("Skipping malformed roadmap step: %s", exc)

    return ResearchResult(
        summary=_coerce_str(data.get("summary")),
        papers=papers,
        citation_links=citation_links,
        gap_analysis=_coerce_list_of_str(data.get("gap_analysis")),
        implementation_roadmap=roadmap,
        key_concepts=_coerce_list_of_str(data.get("key_concepts")),
    )


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict | None:
    """
    Try to pull a JSON object out of *text*.

    Attempts:
    1. Fenced code block  ```json ... ```
    2. The last ``{ ... }`` block found by regex
    3. Direct ``json.loads`` on the whole text
    """
    # 1. Fenced code block
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Greedy brace matching — find outermost { ... }
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break  # malformed – fall through

    # 3. Whole text
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Main agentic loop
# ---------------------------------------------------------------------------

async def run_research(
    session_id: str,
    user_input: str,
    depth: str = "standard",
) -> None:
    """
    Drive the agentic research loop for *session_id*.

    This function is designed to be run as a background task; it updates the
    session store (and SSE queues) as it progresses and never raises to the
    caller.
    """
    model = os.getenv("LLM_MODEL", "gpt-5.4-nano")
    client = openai.AsyncOpenAI()  # reads OPENAI_API_KEY from env

    await session_store.add_log(session_id, f"Starting research on: {user_input}", "info")
    await session_store.set_progress(session_id, 5)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Research this topic/paper: {user_input}\n\n"
                f"Session ID: {session_id}\n"
                f"Depth: {depth}\n\n"
                f"IMPORTANT: You must find AT LEAST "
                f"{ {'quick':5,'standard':10,'deep':20}.get(depth,10) } papers before synthesising.\n"
                "If the exact topic has few results, EXPAND your queries — break compound words, "
                "try synonyms, parent fields, and related terminology. "
                "Use get_references and get_paper_citations on any paper you find "
                "to discover more related works.\n\n"
                "Use the tools to gather information, then return the final JSON report. "
                "If you use budget_status, pass this exact session ID."
            ),
        },
    ]

    max_tool_calls = {"quick": 8, "standard": 18, "deep": 28}.get(depth, 18)
    tool_call_count = 0

    async def _call_model(msgs: list[dict]) -> Any:
        return await client.chat.completions.create(
            model=model,
            extra_body={"max_completion_tokens": 8000},
            tools=TOOL_SPECS,  # type: ignore[arg-type]
            messages=msgs,  # type: ignore[arg-type]
        )

    async def _populate_graph(result: ResearchResult) -> None:
        """Store papers + citations in Memgraph and run graph algorithms."""
        if not graph_store.is_available():
            return
        try:
            loop = asyncio.get_event_loop()
            def _sync_populate():
                graph_store.clear_session(session_id)
                for paper in result.papers:
                    graph_store.upsert_paper(paper.model_dump(), session_id)
                for link in result.citation_links:
                    graph_store.upsert_citation(link.source, link.target)
                # Also connect papers that share tags as RELATED_TO
                tag_map: dict[str, list[str]] = {}
                for paper in result.papers:
                    for tag in paper.tags:
                        tag_map.setdefault(tag, []).append(paper.id)
                for ids in tag_map.values():
                    for i in range(len(ids)):
                        for j in range(i + 1, len(ids)):
                            graph_store.upsert_related(ids[i], ids[j], score=0.6)
            await loop.run_in_executor(None, _sync_populate)
            await session_store.add_log(session_id, "Knowledge graph built in Memgraph", "success")
        except Exception as exc:
            logger.warning("Graph population failed (non-fatal): %s", exc)

    async def _populate_global_graph(result: ResearchResult) -> None:
        """Merge this session's papers into the shared GlobalPaper graph."""
        if not graph_store.is_available():
            return
        try:
            loop = asyncio.get_event_loop()
            def _sync_global():
                for paper in result.papers:
                    graph_store.upsert_global_paper(paper.model_dump())
                for link in result.citation_links:
                    graph_store.upsert_global_citation(link.source, link.target)
                tag_map: dict[str, list[str]] = {}
                for paper in result.papers:
                    for tag in paper.tags:
                        tag_map.setdefault(tag, []).append(paper.id)
                for ids in tag_map.values():
                    for i in range(len(ids)):
                        for j in range(i + 1, len(ids)):
                            graph_store.upsert_global_related(ids[i], ids[j], score=0.6)
            await loop.run_in_executor(None, _sync_global)
            await session_store.add_log(session_id, "Global knowledge graph updated", "success")
        except Exception as exc:
            logger.warning("Global graph population failed (non-fatal): %s", exc)

    async def _verify_urls(papers: list) -> None:
        """HTTP HEAD-check every paper URL; mark url_verified on each Paper in-place."""
        sem = asyncio.Semaphore(10)

        async def _check(paper) -> None:
            url = paper.url
            if not url:
                paper.url_verified = False
                return
            async with sem:
                try:
                    async with __import__("httpx").AsyncClient(
                        timeout=6.0, follow_redirects=True
                    ) as client:
                        resp = await client.head(url)
                        paper.url_verified = resp.status_code < 400
                except Exception:
                    paper.url_verified = False

        await asyncio.gather(*[_check(p) for p in papers], return_exceptions=True)
        bad = [p.title for p in papers if p.url_verified is False]
        if bad:
            await session_store.add_log(
                session_id,
                f"URL check: {len(papers) - len(bad)}/{len(papers)} links live. Dead: {', '.join(bad[:3])}{'…' if len(bad) > 3 else ''}",
                "warning",
            )
        else:
            await session_store.add_log(session_id, f"URL check: all {len(papers)} links verified.", "success")

    async def _finalise(result_text: str) -> bool:
        """Parse JSON, update session, return True on success."""
        result_data = _extract_json(result_text)
        if result_data is not None:
            result = parse_result(result_data, session_id)
            await session_store.add_log(session_id, "Verifying source URLs…", "info")
            await _verify_urls(result.papers)
            session = session_store.get_session(session_id)
            if session is not None:
                session.result = result
                session.status = "completed"
                session.progress.percentage = 100
                await session_store.update_session(session)
            await session_store.add_log(session_id, "Research complete!", "success")
            await _populate_graph(result)
            await _populate_global_graph(result)
            # Persist papers to cross-session memory
            try:
                await _db.save_papers_memory(
                    [p.model_dump() for p in result.papers], session_id
                )
            except Exception as exc:
                logger.warning("save_papers_memory failed (non-fatal): %s", exc)
            # Save artifacts to disk
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, save_research_artifacts, session_id, result_data, "research"
                )
            except Exception as exc:
                logger.warning("save_research_artifacts failed (non-fatal): %s", exc)
            return True
        logger.warning("No JSON found in final response for session %s", session_id)
        await session_store.add_log(
            session_id, "Warning: could not parse JSON report from model response.", "warning"
        )
        session = session_store.get_session(session_id)
        if session is not None:
            session.status = "error"
            await session_store.update_session(session)
        return False

    try:
        while tool_call_count <= max_tool_calls:
            await session_store.add_log(session_id, f"Calling {model}…", "info")

            response = await _call_model(messages)
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            # Append the assistant message to keep the conversation valid.
            # OpenAI expects the full message object (with tool_calls if present).
            assistant_msg: dict = {"role": "assistant", "content": choice.message.content}
            if choice.message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in choice.message.tool_calls
                ]
            messages.append(assistant_msg)

            # ------------------------------------------------------------------
            # Terminal turn
            # ------------------------------------------------------------------
            if finish_reason == "stop":
                await _finalise(choice.message.content or "")
                await session_store.notify_complete(session_id)
                break

            # ------------------------------------------------------------------
            # Tool-use turn
            # ------------------------------------------------------------------
            if finish_reason == "tool_calls" and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_call_count += 1
                    tool_name = tc.function.name
                    try:
                        tool_input = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_input = {}

                    await session_store.add_log(session_id, f"Using tool: {tool_name}", "info")
                    progress_pct = min(5 + int(tool_call_count / max_tool_calls * 85), 90)
                    await session_store.set_progress(session_id, progress_pct)

                    try:
                        result_str = await execute_tool(tool_name, tool_input)
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": result_str}
                        )
                        await session_store.add_log(
                            session_id, f"Tool '{tool_name}' completed", "success"
                        )
                    except Exception as exc:
                        logger.exception("Tool %r raised: %s", tool_name, exc)
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": f"Error: {exc}"}
                        )
                        await session_store.add_log(
                            session_id, f"Tool '{tool_name}' failed: {exc}", "error"
                        )
                continue

            # Unexpected finish reason
            logger.warning("Unexpected finish_reason %r for session %s", finish_reason, session_id)
            break

        else:
            # Max tool calls exhausted – ask the model to wrap up.
            await session_store.add_log(
                session_id, "Maximum tool calls reached; asking model to synthesise results.", "warning"
            )
            depth_targets = {"quick": 5, "standard": 10, "deep": 20}
            target = depth_targets.get(depth, 10)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"You have reached the maximum number of tool calls. "
                        f"Target for this depth ('{depth}') is {target} papers. "
                        "Include every paper you found across all tool calls — even if you "
                        "only have an abstract or title, include it with read_status='abstract_only'. "
                        "Return the final JSON report now."
                    ),
                }
            )
            response = await _call_model(messages)
            choice = response.choices[0]
            await _finalise(choice.message.content or "")
            await session_store.notify_complete(session_id)

    except Exception as exc:
        logger.exception("run_research raised for session %s: %s", session_id, exc)
        session = session_store.get_session(session_id)
        if session is not None:
            session.status = "error"
            await session_store.update_session(session)
        await session_store.add_log(session_id, f"Fatal error: {exc}", "error")
        await session_store.notify_complete(session_id)
