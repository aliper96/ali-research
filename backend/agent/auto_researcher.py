"""
AutoResearch — autonomous iterative research loop.

Each iteration:
  1. Research the current question (quick depth)
  2. Claude decides: what is the most interesting open question from these findings?
  3. Claude decides: should I keep exploring or is coverage sufficient?
  4. If continue → next iteration focuses on that open question
  5. Accumulate findings across all iterations into a growing knowledge artifact

Max iterations: configurable (default 4).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import openai

from ..models.schemas import Paper, CitationLink, ResearchResult, RoadmapStep
from ..storage import db as _db
from .tools import TOOL_SPECS, execute_tool
from .researcher import _extract_json, parse_result
from . import deep_researcher as _dr

logger = logging.getLogger(__name__)

# Lazy import to avoid circular at module load — deep_store imported inside functions

ITERATION_PROMPT = """You are an autonomous researcher on iteration {iteration}/{max_iter}.

Seed question: {seed}
Current focus: {focus}

Previous findings summary:
{prior_summary}

Papers already seen: {seen_count} papers (do NOT re-fetch these: {seen_titles})

Your job for this iteration:
1. Search for papers relevant to the CURRENT FOCUS (not papers already seen)
2. Extract key findings
3. Decide: should the next iteration keep going? If yes, what specific open question did you discover?

Return ONLY this JSON:
{{
  "papers": [...],
  "citation_links": [...],
  "key_findings": "What you found this iteration",
  "next_question": "The most interesting open question to explore next, or null if coverage is sufficient",
  "should_continue": true
}}"""

DECISION_PROMPT = """Based on iteration {iteration} findings, decide if autonomous research should continue.

Rules for stopping:
- You have explored {max_iter} iterations (hard stop)
- The next question is essentially the same as a previous one (circular)
- Coverage feels comprehensive (no major open questions remain)
- Less than 3 new papers were found this iteration

Current next_question candidate: {next_q}
Prior questions explored: {prior_questions}

Return ONLY: {{"should_continue": true/false, "reason": "brief explanation"}}"""

FINAL_SYNTHESIS_PROMPT = """You are writing the final synthesis for an autonomous research run.

Seed: {seed}
Iterations completed: {n}
Total papers: {total}

Iteration summaries:
{summaries}

Produce a comprehensive JSON report integrating ALL iterations."""


async def _run_iteration(
    client: openai.AsyncOpenAI,
    session_id: str,
    seed: str,
    focus: str,
    iteration: int,
    max_iter: int,
    prior_summary: str,
    seen_papers: dict[str, Paper],
    log_fn,
) -> dict[str, Any]:
    seen_titles = ", ".join(list(p.title[:40] for p in list(seen_papers.values())[:5]))
    system = ITERATION_PROMPT.format(
        iteration=iteration, max_iter=max_iter, seed=seed, focus=focus,
        prior_summary=prior_summary or "None yet — first iteration.",
        seen_count=len(seen_papers), seen_titles=seen_titles or "none",
    )
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Research this: {focus}"},
    ]
    calls = 0
    max_calls = 8
    while calls <= max_calls:
        resp = await _dr._run_llm(client, messages, tools=TOOL_SPECS)
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
            text = choice.message.content or ""
            data = _extract_json(text)
            return data or {}
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                calls += 1
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                await log_fn(f"  [iter {iteration}] tool: {tc.function.name}", "info")
                try:
                    out = await execute_tool(tc.function.name, args)
                except Exception as exc:
                    out = json.dumps({"error": str(exc)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
            continue
        break
    messages.append({"role": "user", "content": "Return the JSON report for this iteration now."})
    resp = await _dr._run_llm(client, messages)
    return _extract_json(resp.choices[0].message.content or "") or {}


async def run_auto_research(
    session_id: str,
    user_input: str,
    max_iterations: int = 4,
) -> None:
    from ..storage.auto_store import auto_store

    client = openai.AsyncOpenAI()

    async def _log(msg: str, level: str = "info") -> None:
        await auto_store.add_log(session_id, msg, level)

    await _log(f"AutoResearch started: {user_input}", "info")
    await auto_store.set_progress(session_id, 5)

    all_papers: dict[str, Paper] = {}
    all_links: list[CitationLink] = []
    iteration_summaries: list[str] = []
    prior_questions: list[str] = [user_input]
    focus = user_input
    prior_summary = ""

    try:
        for i in range(1, max_iterations + 1):
            await _log(f"Iteration {i}/{max_iterations}: {focus}", "info")
            await auto_store.set_progress(session_id, 5 + int(i / max_iterations * 70))

            data = await _run_iteration(
                client, session_id, seed=user_input, focus=focus,
                iteration=i, max_iter=max_iterations,
                prior_summary=prior_summary,
                seen_papers=all_papers,
                log_fn=_log,
            )

            # Merge new papers
            parsed = parse_result(data, session_id)
            new_count = 0
            for p in parsed.papers:
                key = p.arxiv_id or p.doi or p.id
                if key not in all_papers:
                    all_papers[key] = p
                    new_count += 1
            all_links.extend(parsed.citation_links)

            findings = str(data.get("key_findings", ""))
            iteration_summaries.append(f"Iter {i} [{focus}]: {findings} ({new_count} new papers)")
            prior_summary = "\n".join(iteration_summaries[-3:])

            await _log(f"Iter {i}: {new_count} new papers. {findings[:80]}…", "success")

            # Check if should continue
            next_q = data.get("next_question")
            should_continue = bool(data.get("should_continue", True))
            if not next_q or not should_continue or i >= max_iterations:
                await _log(f"Stopping after {i} iterations: {'max reached' if i >= max_iterations else 'coverage sufficient'}", "info")
                break
            if new_count < 3:
                await _log(f"Stopping: only {new_count} new papers found", "info")
                break

            prior_questions.append(str(next_q))
            focus = str(next_q)

        # Final synthesis
        await _log(f"Synthesizing {len(all_papers)} papers from {len(iteration_summaries)} iterations…", "info")
        await auto_store.set_progress(session_id, 80)

        summaries_text = "\n".join(iteration_summaries)
        all_papers_list = list(all_papers.values())
        messages: list[dict] = [
            {"role": "system", "content": FINAL_SYNTHESIS_PROMPT.format(
                seed=user_input, n=len(iteration_summaries),
                total=len(all_papers_list), summaries=summaries_text,
            )},
            {"role": "user", "content":
                f"Papers:\n{json.dumps([p.model_dump() for p in all_papers_list[:25]])}\n\n"
                "Produce the final JSON report."},
        ]
        resp = await _dr._run_llm(client, messages, max_tokens=5000, tools=TOOL_SPECS)
        data = _extract_json(resp.choices[0].message.content or "") or {}
        result = parse_result(data, session_id)
        if not result.papers:
            result.papers = all_papers_list
        if not result.citation_links:
            result.citation_links = all_links

        session = auto_store.get_session(session_id)
        if session:
            session.result = result
            session.status = "completed"
            session.progress.percentage = 100
            # Store iteration log in result summary preamble
            iter_log = "\n".join(f"- {s}" for s in iteration_summaries)
            session.result.summary = (
                f"**AutoResearch ({len(iteration_summaries)} iterations)**\n\n"
                f"**Iteration log:**\n{iter_log}\n\n"
                f"**Synthesis:**\n{result.summary}"
            )
            await auto_store.update_session(session)

        await _log(f"AutoResearch complete — {len(all_papers_list)} papers across {len(iteration_summaries)} iterations", "success")
        await auto_store.set_progress(session_id, 100)

        try:
            await _db.save_papers_memory([p.model_dump() for p in all_papers_list], session_id)
        except Exception as exc:
            logger.warning("save_papers_memory failed: %s", exc)

    except Exception as exc:
        logger.exception("run_auto_research failed for %s: %s", session_id, exc)
        session = auto_store.get_session(session_id)
        if session:
            session.status = "error"
            await auto_store.update_session(session)
        await _log(f"Fatal error: {exc}", "error")
    finally:
        await auto_store.notify_complete(session_id)
