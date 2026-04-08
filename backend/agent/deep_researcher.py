"""
Deep Research — true multi-agent pipeline:

  Orchestrator  →  [Researcher-1 | Researcher-2 | … | Researcher-N]  (parallel)
                →  Synthesizer  (merges all findings)
                →  Verifier     (checks claims against evidence)

Each researcher is a full Claude conversation scoped to one subtopic.
All share the same tool library but run concurrently via asyncio.gather.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import openai

from ..models.deep_research_schemas import (
    DeepResearchResult, DeepResearchSession, SubResearchResult,
    VerificationReport, VerifiedClaim,
)
from ..models.schemas import CitationLink, Paper, ResearchResult, RoadmapStep
from ..storage.deep_store import deep_store
from ..storage import db as _db
from .tools import TOOL_SPECS, execute_tool
from .researcher import _extract_json, parse_result   # reuse helpers

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are a research director. Given a broad topic, decompose it into
{n} focused subtopics for parallel investigation. Each subtopic should be:
- Distinct (minimal overlap)
- Focused enough for 8-10 tool calls
- Together they must give complete coverage of the topic

Return ONLY this JSON:
{{"subtopics": ["subtopic 1", "subtopic 2", ...]}}"""

RESEARCHER_PROMPT = """You are a specialist researcher focused on: **{subtopic}**

Your parent research question is: {parent_topic}

Search for papers, extract key findings, and return a JSON report. Be focused — only cover your assigned subtopic.

Minimum workflow expectations:
- Start with search_session_memory when useful.
- Use search_papers AND search_google_scholar for coverage.
- Use at least one source-specific retrieval step for the strongest papers.
- For the most important papers, fetch metadata/citations and parse_pdf whenever you can access a PDF or arXiv paper.
- In deep mode, aim for at least 6 solid papers for your subtopic, and avoid relying mostly on inferred entries.
- Do not write broad conceptual summaries unless they are grounded in papers you actually inspected.

Provenance rules: set source, read_status, venue per paper.

Return ONLY this JSON:
{{
  "subtopic": "{subtopic}",
  "key_findings": "2-3 sentence summary of what you found for this subtopic",
  "papers": [{{...same schema as standard research...}}],
  "citation_links": [{{"source": "id1", "target": "id2"}}]
}}"""

SYNTHESIZER_PROMPT = """You are a senior researcher synthesizing findings from {n} parallel investigators.

You have received their individual reports. Your job:
1. Merge all papers (deduplicate by arxiv_id/doi/title)
2. Write a comprehensive executive summary that integrates all subtopics
3. Identify cross-cutting themes, contradictions, and gaps
4. Build a unified implementation roadmap

The combined papers from all researchers are provided as context. Return the standard research JSON."""

VERIFIER_PROMPT = """You are a rigorous fact-checker for a research synthesis.

For each factual claim in the summary, verify it is supported by at least one paper in the evidence base.
Flag any claim that cannot be traced to a specific paper.

Return ONLY this JSON:
{{
  "verified_claims": [
    {{"claim": "...", "supported_by": ["paper_id_1"], "confidence": 0.95, "verdict": "supported"}}
  ],
  "unsupported_sentences": ["sentence that has no paper backing it"],
  "overall_confidence": 0.87
}}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client() -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI()


async def _run_llm(client: openai.AsyncOpenAI, messages: list[dict],
                   max_tokens: int = 4000, tools: list | None = None) -> Any:
    kwargs: dict[str, Any] = dict(
        model=os.getenv("LLM_MODEL", "gpt-5.4-nano"),
        max_completion_tokens=max_tokens,
        messages=messages,  # type: ignore[arg-type]
    )
    if tools:
        kwargs["tools"] = tools  # type: ignore[assignment]
    return await client.chat.completions.create(**kwargs)


async def _tool_loop(client: openai.AsyncOpenAI, messages: list[dict],
                     max_calls: int, log_fn) -> str:
    """Run a tool-use loop and return final text content."""
    calls = 0
    while calls <= max_calls:
        resp = await _run_llm(client, messages, tools=TOOL_SPECS)
        choice = resp.choices[0]
        asst: dict = {"role": "assistant", "content": choice.message.content}
        if choice.message.tool_calls:
            asst["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]
        messages.append(asst)

        if choice.finish_reason == "stop":
            return choice.message.content or ""

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                calls += 1
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                await log_fn(f"  tool: {tc.function.name}", "info")
                try:
                    out = await execute_tool(tc.function.name, args)
                except Exception as exc:
                    out = json.dumps({"error": str(exc)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
            continue
        break

    # Budget exhausted — ask for wrap-up
    messages.append({"role": "user", "content": "Budget reached. Return the JSON report now."})
    resp = await _run_llm(client, messages, tools=TOOL_SPECS)
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Stage 1 — orchestrator decomposes the topic
# ---------------------------------------------------------------------------

async def _orchestrate(client: openai.AsyncOpenAI, topic: str, n: int) -> list[str]:
    prompt = ORCHESTRATOR_PROMPT.format(n=n)
    resp = await _run_llm(client, [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Decompose this research topic into {n} subtopics: {topic}"},
    ], max_tokens=800)
    text = resp.choices[0].message.content or ""
    data = _extract_json(text)
    if data and isinstance(data.get("subtopics"), list):
        subtopics = [str(s) for s in data["subtopics"][:n]]
        if subtopics:
            return subtopics
    # Fallback: generate generic subtopics
    return [f"{topic} — part {i+1}" for i in range(n)]


# ---------------------------------------------------------------------------
# Stage 2 — parallel researcher per subtopic
# ---------------------------------------------------------------------------

async def _run_researcher(
    client: openai.AsyncOpenAI,
    researcher_id: int,
    subtopic: str,
    parent_topic: str,
    session_id: str,
    depth: str,
    max_tool_calls: int,
) -> SubResearchResult:
    sub = SubResearchResult(subtopic=subtopic, researcher_id=researcher_id, status="running")

    async def _log(msg: str, level: str = "info") -> None:
        await deep_store.add_log(session_id, f"[R{researcher_id}] {msg}", level)

    await _log(f"Starting subtopic: {subtopic}")
    system = RESEARCHER_PROMPT.format(subtopic=subtopic, parent_topic=parent_topic)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content":
            f"Research this subtopic thoroughly: {subtopic}\n"
            f"Context: part of a larger investigation into '{parent_topic}'\n"
            f"Depth: {depth}\n"
            "Be evidence-first. Prefer papers you actually read over inferred citations."},
    ]
    try:
        text = await _tool_loop(client, messages, max_tool_calls, _log)
        data = _extract_json(text)
        if data:
            result = parse_result(data, session_id)
            sub.papers = result.papers
            sub.citation_links = result.citation_links
            sub.key_findings = str(data.get("key_findings", ""))
        sub.status = "done"
        await _log(f"Done — {len(sub.papers)} papers found", "success")
    except Exception as exc:
        sub.status = "error"
        sub.error = str(exc)
        await _log(f"Error: {exc}", "error")
    return sub


# ---------------------------------------------------------------------------
# Stage 3 — synthesizer merges all findings
# ---------------------------------------------------------------------------

async def _synthesize(
    client: openai.AsyncOpenAI,
    topic: str,
    researchers: list[SubResearchResult],
    session_id: str,
) -> ResearchResult:
    await deep_store.add_log(session_id, "Synthesizing findings from all researchers…", "info")

    # Merge and deduplicate papers
    seen: dict[str, Paper] = {}
    all_links: list[CitationLink] = []
    for r in researchers:
        for p in r.papers:
            key = p.arxiv_id or p.doi or p.id
            if key not in seen:
                seen[key] = p
        all_links.extend(r.citation_links)

    merged_papers = list(seen.values())
    findings_context = "\n\n".join(
        f"**Subtopic {r.researcher_id}: {r.subtopic}**\nKey findings: {r.key_findings}\nPapers: {len(r.papers)}"
        for r in researchers if r.status == "done"
    )
    papers_json = json.dumps([p.model_dump() for p in merged_papers[:30]])

    messages: list[dict] = [
        {"role": "system", "content": SYNTHESIZER_PROMPT.format(n=len(researchers))},
        {"role": "user", "content":
            f"Topic: {topic}\n\n"
            f"Researcher findings:\n{findings_context}\n\n"
            f"All papers (deduplicated, {len(merged_papers)} total):\n{papers_json}\n\n"
            "Produce the unified JSON report now."},
    ]
    text = await _tool_loop(client, messages, 6,
                            lambda m, l="info": deep_store.add_log(session_id, f"[Synth] {m}", l))
    data = _extract_json(text)
    if data:
        result = parse_result(data, session_id)
        # Ensure we keep all merged papers if synthesizer returned fewer
        if len(result.papers) < len(merged_papers) // 2:
            result.papers = merged_papers
        if not result.citation_links:
            result.citation_links = all_links
        return result
    # Fallback: construct minimal result from merged data
    from ..agent.tools import find_gaps, build_implementation_plan
    gaps = await find_gaps([p.model_dump() for p in merged_papers], topic)
    roadmap = await build_implementation_plan(topic, [p.model_dump() for p in merged_papers])
    return ResearchResult(
        summary=f"Deep research on '{topic}' gathered {len(merged_papers)} papers across "
                f"{len(researchers)} subtopics. " +
                " ".join(r.key_findings for r in researchers if r.key_findings),
        papers=merged_papers,
        citation_links=all_links,
        gap_analysis=gaps,
        implementation_roadmap=[RoadmapStep(**s) for s in roadmap],
    )


# ---------------------------------------------------------------------------
# Stage 4 — verifier checks synthesis claims
# ---------------------------------------------------------------------------

async def _verify(
    client: openai.AsyncOpenAI,
    synthesis: ResearchResult,
    session_id: str,
) -> VerificationReport:
    await deep_store.add_log(session_id, "Running verifier on synthesis…", "info")
    paper_index = {p.id: p.title for p in synthesis.papers}
    messages: list[dict] = [
        {"role": "system", "content": VERIFIER_PROMPT},
        {"role": "user", "content":
            f"Summary to verify:\n{synthesis.summary}\n\n"
            f"Evidence base ({len(synthesis.papers)} papers):\n"
            + json.dumps([{"id": p.id, "title": p.title, "abstract": p.abstract[:300]}
                          for p in synthesis.papers[:20]])},
    ]
    resp = await _run_llm(client, messages, max_tokens=3000)
    text = resp.choices[0].message.content or ""
    data = _extract_json(text)
    if not data:
        return VerificationReport(overall_confidence=0.7)

    valid_verdicts = {"supported", "partial", "unsupported"}
    claims = []
    for raw in data.get("verified_claims", []):
        if not isinstance(raw, dict):
            continue
        verdict = str(raw.get("verdict", "partial")).lower()
        if verdict not in valid_verdicts:
            verdict = "partial"
        try:
            conf = float(raw.get("confidence", 0.7))
        except (TypeError, ValueError):
            conf = 0.7
        claims.append(VerifiedClaim(
            claim=str(raw.get("claim", "")),
            supported_by=[str(x) for x in (raw.get("supported_by") or [])],
            confidence=max(0.0, min(1.0, conf)),
            verdict=verdict,  # type: ignore[arg-type]
        ))
    try:
        overall = float(data.get("overall_confidence", 0.7))
    except (TypeError, ValueError):
        overall = 0.7

    return VerificationReport(
        verified_claims=claims,
        unsupported_sentences=[str(x) for x in data.get("unsupported_sentences", [])],
        overall_confidence=max(0.0, min(1.0, overall)),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_deep_research(
    session_id: str,
    user_input: str,
    depth: str = "deep",
    num_researchers: int = 3,
) -> None:
    client = _make_client()
    max_calls_per_researcher = {"standard": 10, "deep": 18}.get(depth, 12)

    await deep_store.add_log(session_id, f"Deep research started: {user_input}", "info")
    await deep_store.set_progress(session_id, 5)

    try:
        # Stage 1 — decompose
        await deep_store.add_log(session_id, f"Decomposing topic into {num_researchers} subtopics…", "info")
        subtopics = await _orchestrate(client, user_input, num_researchers)
        await deep_store.add_log(session_id, f"Subtopics: {' | '.join(subtopics)}", "success")
        await deep_store.set_progress(session_id, 10)

        # Update session with subtopics
        session = deep_store.get_session(session_id)
        if session and session.result is None:
            session.result = DeepResearchResult(subtopics=subtopics)
            await deep_store.update_session(session)

        # Stage 2 — parallel researchers
        await deep_store.add_log(session_id, f"Launching {num_researchers} parallel researchers…", "info")
        tasks = [
            _run_researcher(client, i + 1, subtopic, user_input, session_id, depth, max_calls_per_researcher)
            for i, subtopic in enumerate(subtopics)
        ]
        researchers: list[SubResearchResult] = await asyncio.gather(*tasks)
        done = sum(1 for r in researchers if r.status == "done")
        await deep_store.add_log(session_id, f"{done}/{len(researchers)} researchers completed", "success")
        await deep_store.set_progress(session_id, 60)

        # Stage 3 — synthesis
        synthesis = await _synthesize(client, user_input, researchers, session_id)
        await deep_store.set_progress(session_id, 80)

        # Stage 4 — verification
        verification = await _verify(client, synthesis, session_id)
        supported = sum(1 for c in verification.verified_claims if c.verdict == "supported")
        await deep_store.add_log(
            session_id,
            f"Verification: {supported}/{len(verification.verified_claims)} claims supported, "
            f"confidence {verification.overall_confidence:.0%}",
            "success",
        )
        await deep_store.set_progress(session_id, 95)

        # Finalise
        result = DeepResearchResult(
            subtopics=subtopics,
            researchers=list(researchers),
            synthesis=synthesis,
            verification=verification,
        )
        session = deep_store.get_session(session_id)
        if session:
            session.result = result
            session.status = "completed"
            session.progress.percentage = 100
            await deep_store.update_session(session)

        await deep_store.add_log(
            session_id,
            f"Deep research complete — {len(synthesis.papers)} papers, "
            f"{len(researchers)} researchers, confidence {verification.overall_confidence:.0%}",
            "success",
        )

        # Save to cross-session memory
        try:
            await _db.save_papers_memory([p.model_dump() for p in synthesis.papers], session_id)
        except Exception as exc:
            logger.warning("save_papers_memory failed: %s", exc)

    except Exception as exc:
        logger.exception("run_deep_research failed for %s: %s", session_id, exc)
        session = deep_store.get_session(session_id)
        if session:
            session.status = "error"
            await deep_store.update_session(session)
        await deep_store.add_log(session_id, f"Fatal error: {exc}", "error")
    finally:
        await deep_store.notify_complete(session_id)
