"""
Peer-review simulation.

run_review()       — orchestrates N reviewer agents in parallel + 1 editor agent
run_reviewer()     — single agentic reviewer (uses research tools)
run_editor()       — synthesises all reviewer reports into a final decision
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import openai

from ..models.review_schemas import (
    EditorReport,
    Recommendation,
    ReviewerReport,
)
from ..storage.review_store import review_store
from .tools import TOOL_SPECS, execute_tool

logger = logging.getLogger(__name__)

_VALID_RECOMMENDATIONS = {"accept", "minor_revision", "major_revision", "reject"}

# ---------------------------------------------------------------------------
# Reviewer personas  (1-indexed)
# ---------------------------------------------------------------------------

PERSONAS = {
    1: "a rigorous methodologist who focuses on technical soundness, reproducibility, "
       "and experimental design. You are meticulous about claims that are not backed by evidence.",
    2: "a domain expert who specialises in novelty assessment. You exhaustively search "
       "for prior work and are very critical when contributions overlap with existing literature.",
    3: "a presentation and clarity expert. You assess writing quality, logical flow, figure "
       "quality, and whether the paper is self-contained. You also check reproducibility of results.",
    4: "a big-picture evaluator who assesses the significance and impact of the work. "
       "You focus on whether the contribution moves the field forward and fits the target venue.",
    5: "a devil's advocate who rigorously challenges assumptions, looks for logical flaws, "
       "and stress-tests the experimental conclusions.",
}

# ---------------------------------------------------------------------------
# JSON schema requested from each reviewer
# ---------------------------------------------------------------------------

REVIEWER_JSON_SCHEMA = """\
{
  "novelty_score":        <float 0-10>,
  "technical_score":      <float 0-10>,
  "clarity_score":        <float 0-10>,
  "contribution_score":   <float 0-10>,
  "overall_score":        <float 0-10>,
  "recommendation":       "accept" | "minor_revision" | "major_revision" | "reject",
  "strengths":            ["..."],
  "major_issues":         ["..."],
  "minor_issues":         ["..."],
  "missing_citations":    ["Author et al. (year) – reason"],
  "related_papers_found": ["arXiv:XXXX.XXXXX – description"],
  "summary":              "2-4 sentence narrative review"
}"""

EDITOR_JSON_SCHEMA = """\
{
  "final_recommendation": "accept" | "minor_revision" | "major_revision" | "reject",
  "novelty_score":        <float 0-10>,
  "technical_score":      <float 0-10>,
  "clarity_score":        <float 0-10>,
  "contribution_score":   <float 0-10>,
  "overall_score":        <float 0-10>,
  "novelty_verdict":      "Incremental" | "Solid" | "Strong" | "Highly novel",
  "publishability":       "Not ready" | "Workshop" | "Good venue" | "Top venue",
  "consensus_summary":    "3-5 sentence editor decision rationale",
  "major_issues":         ["consolidated list"],
  "minor_issues":         ["consolidated list"],
  "strengths":            ["consolidated list"],
  "action_items":         ["specific things authors must address"],
  "reviewer_agreement":   <float 0-1>
}"""


# ---------------------------------------------------------------------------
# Helper: call model
# ---------------------------------------------------------------------------

def _get_client() -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def _call_model(client: openai.AsyncOpenAI, messages: list[dict], *, tools=True) -> Any:
    model = os.getenv("LLM_MODEL", "gpt-5.4-nano")
    return await client.chat.completions.create(
        model=model,
        extra_body={"max_completion_tokens": 6000},
        tools=TOOL_SPECS if tools else openai.NOT_GIVEN,  # type: ignore[arg-type]
        messages=messages,  # type: ignore[arg-type]
    )


def _coerce_score(value: Any, default: float = 5.0) -> float:
    try:
        return max(0.0, min(10.0, float(value)))
    except (TypeError, ValueError):
        return default


def _coerce_recommendation(value: Any, default: Recommendation = "major_revision") -> Recommendation:
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_RECOMMENDATIONS:
        return normalized  # type: ignore[return-value]
    return default


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _build_reviewer_report(
    reviewer_id: int,
    persona: str,
    data: dict[str, Any],
) -> ReviewerReport:
    return ReviewerReport(
        reviewer_id=reviewer_id,
        persona=persona,
        status="done",
        novelty_score=_coerce_score(data.get("novelty_score")),
        technical_score=_coerce_score(data.get("technical_score")),
        clarity_score=_coerce_score(data.get("clarity_score")),
        contribution_score=_coerce_score(data.get("contribution_score")),
        overall_score=_coerce_score(data.get("overall_score")),
        recommendation=_coerce_recommendation(data.get("recommendation")),
        strengths=_coerce_string_list(data.get("strengths")),
        major_issues=_coerce_string_list(data.get("major_issues")),
        minor_issues=_coerce_string_list(data.get("minor_issues")),
        missing_citations=_coerce_string_list(data.get("missing_citations")),
        related_papers_found=_coerce_string_list(data.get("related_papers_found")),
        summary=str(data.get("summary", "")),
    )


def _extract_json(text: str) -> dict | None:
    """Pull JSON object from model output."""
    # Fenced block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Greedy brace match
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


# ---------------------------------------------------------------------------
# Single reviewer agent
# ---------------------------------------------------------------------------

async def run_reviewer(
    session_id: str,
    reviewer_id: int,
    paper_title: str,
    paper_abstract: str,
    paper_text: str,
    bib_refs: list[str],
) -> ReviewerReport:
    persona = PERSONAS.get(reviewer_id, PERSONAS[1])
    report = ReviewerReport(reviewer_id=reviewer_id, persona=persona, status="running")
    await review_store.update_reviewer(session_id, report)
    await review_store.add_log(
        session_id, f"Reviewer {reviewer_id} started ({persona[:60]}…)", "info"
    )

    client = _get_client()
    max_tool_calls = 12   # enough for 3-4 searches + get_references + get_paper_citations
    tool_call_count = 0

    bib_section = (
        "\n\nAuthors cited in the submission:\n" + "\n".join(f"- {r}" for r in bib_refs[:30])
        if bib_refs
        else ""
    )

    system = (
        f"You are Reviewer {reviewer_id} for a scientific paper. "
        f"Your reviewing style: you are {persona}\n\n"
        "Your task:\n"
        "1. Carefully read the paper title, abstract, and text excerpt provided.\n"
        "2. Search for closely related work — especially papers that could challenge "
        "the novelty claims. Be strategic with your searches:\n"
        "   - Try the exact method/system name from the title\n"
        "   - Try 2-3 alternative phrasings (synonyms, parent fields, related approaches)\n"
        "   - Try author names if the work seems incremental on a known line of research\n"
        "   - Use search_semantic_scholar AND search_arxiv for better coverage\n"
        "   - Use get_references on any highly relevant paper you find to snowball more\n"
        "3. Evaluate the paper on: novelty (vs. what you found), technical soundness, "
        "clarity, and significance.\n"
        "4. Return ONLY a JSON object matching the schema below — no extra text.\n\n"
        f"Required JSON schema:\n{REVIEWER_JSON_SCHEMA}"
    )

    # Give reviewers a substantial excerpt — 4o has 128k context, 12k chars ≈ 4-5 pages
    _EXCERPT_CHARS = 12_000
    text_excerpt = paper_text[:_EXCERPT_CHARS] + (
        f"\n\n[... text truncated at {_EXCERPT_CHARS} chars ...]"
        if len(paper_text) > _EXCERPT_CHARS else ""
    )

    messages: list[dict] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"PAPER TITLE: {paper_title}\n\n"
                f"ABSTRACT:\n{paper_abstract}\n\n"
                f"FULL TEXT (excerpt):\n{text_excerpt}"
                f"{bib_section}\n\n"
                "Search for closely related work, then return your structured JSON review."
            ),
        },
    ]

    def _error_report(message: str) -> ReviewerReport:
        return ReviewerReport(
            reviewer_id=reviewer_id,
            persona=persona,
            status="error",
            error=message,
        )

    try:
        while tool_call_count < max_tool_calls:
            response = await _call_model(client, messages)
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            if finish_reason == "stop":
                data = _extract_json(choice.message.content or "")
                if data:
                    report = _build_reviewer_report(reviewer_id, persona, data)
                    await review_store.update_reviewer(session_id, report)
                    await review_store.add_log(
                        session_id,
                        f"Reviewer {reviewer_id} done — {report.recommendation} "
                        f"(overall {report.overall_score:.1f}/10)",
                        "success",
                    )
                    return report
                error_message = "Reviewer returned a final response that could not be parsed as JSON."
                report = _error_report(error_message)
                await review_store.update_reviewer(session_id, report)
                await review_store.add_log(session_id, f"Reviewer {reviewer_id} error: {error_message}", "error")
                return report

            if finish_reason == "tool_calls":
                tool_calls = choice.message.tool_calls or []
                messages.append({"role": "assistant", "content": choice.message.content, "tool_calls": [tc.model_dump() for tc in tool_calls]})
                for tc in tool_calls:
                    tool_name = tc.function.name
                    tool_call_count += 1
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                        result_str = await execute_tool(tool_name, args)
                        await review_store.add_log(
                            session_id,
                            f"Reviewer {reviewer_id} → {tool_name}",
                            "info",
                        )
                    except Exception as exc:
                        result_str = f"Error: {exc}"
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result_str}
                    )
                continue

            error_message = f"Reviewer stopped unexpectedly with finish_reason={finish_reason!r}."
            report = _error_report(error_message)
            await review_store.update_reviewer(session_id, report)
            await review_store.add_log(session_id, f"Reviewer {reviewer_id} error: {error_message}", "error")
            return report

        # If we ran out of tool calls, ask for synthesis
        messages.append(
            {
                "role": "user",
                "content": "You've used enough tools. Now return your final JSON review.",
            }
        )
        response = await _call_model(client, messages, tools=False)
        data = _extract_json(response.choices[0].message.content or "")
        if data:
            report = _build_reviewer_report(reviewer_id, persona, data)
            await review_store.update_reviewer(session_id, report)
            await review_store.add_log(
                session_id,
                f"Reviewer {reviewer_id} done — {report.recommendation} "
                f"(overall {report.overall_score:.1f}/10)",
                "success",
            )
            return report

        error_message = "Reviewer could not produce valid JSON after the synthesis prompt."
        report = _error_report(error_message)
        await review_store.update_reviewer(session_id, report)
        await review_store.add_log(session_id, f"Reviewer {reviewer_id} error: {error_message}", "error")
        return report

    except Exception as exc:
        logger.exception("Reviewer %d failed for session %s: %s", reviewer_id, session_id, exc)
        report = _error_report(str(exc))
        await review_store.update_reviewer(session_id, report)
        await review_store.add_log(session_id, f"Reviewer {reviewer_id} error: {exc}", "error")

    return report


# ---------------------------------------------------------------------------
# Editor agent
# ---------------------------------------------------------------------------

async def run_editor(
    session_id: str,
    paper_title: str,
    reviewer_reports: list[ReviewerReport],
) -> EditorReport | None:
    await review_store.add_log(session_id, "Editor agent synthesising all reviews…", "info")
    client = _get_client()

    done_reports = [report for report in reviewer_reports if report.status == "done"]
    if not done_reports:
        await review_store.add_log(session_id, "Editor skipped: no successful reviewer reports available.", "error")
        return None

    reviews_text = "\n\n".join(
        f"=== REVIEWER {r.reviewer_id} ({r.recommendation}, overall {r.overall_score:.1f}/10) ===\n"
        f"Novelty: {r.novelty_score} | Technical: {r.technical_score} | "
        f"Clarity: {r.clarity_score} | Contribution: {r.contribution_score}\n"
        f"Summary: {r.summary}\n"
        f"Strengths: {chr(10).join('- ' + s for s in r.strengths)}\n"
        f"Major issues: {chr(10).join('- ' + s for s in r.major_issues)}\n"
        f"Minor issues: {chr(10).join('- ' + s for s in r.minor_issues)}\n"
        f"Missing citations: {chr(10).join('- ' + s for s in r.missing_citations)}"
        for r in done_reports
    )

    system = (
        "You are a senior editor at a top-tier academic venue. "
        "Your job is to synthesise reviewer reports and make a final editorial decision.\n\n"
        "Be fair but rigorous. Identify consensus across reviewers and flag disagreements.\n\n"
        f"Required JSON schema:\n{EDITOR_JSON_SCHEMA}"
    )

    messages: list[dict] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"PAPER: {paper_title}\n\n"
                f"REVIEWER REPORTS:\n{reviews_text}\n\n"
                "Based on all reviews above, return your final editorial JSON decision."
            ),
        },
    ]

    try:
        response = await _call_model(client, messages, tools=False)
        data = _extract_json(response.choices[0].message.content or "")
        if data:
            editor = EditorReport(
                final_recommendation=_coerce_recommendation(data.get("final_recommendation")),
                novelty_score=_coerce_score(data.get("novelty_score")),
                technical_score=_coerce_score(data.get("technical_score")),
                clarity_score=_coerce_score(data.get("clarity_score")),
                contribution_score=_coerce_score(data.get("contribution_score")),
                overall_score=_coerce_score(data.get("overall_score")),
                novelty_verdict=str(data.get("novelty_verdict", "")),
                publishability=str(data.get("publishability", "")),
                consensus_summary=str(data.get("consensus_summary", "")),
                major_issues=_coerce_string_list(data.get("major_issues")),
                minor_issues=_coerce_string_list(data.get("minor_issues")),
                strengths=_coerce_string_list(data.get("strengths")),
                action_items=_coerce_string_list(data.get("action_items")),
                reviewer_agreement=max(0.0, min(1.0, float(data.get("reviewer_agreement", 0.5)))),
            )
            await review_store.add_log(
                session_id,
                f"Editor decision: {editor.final_recommendation} — {editor.publishability}",
                "success",
            )
            return editor
        await review_store.add_log(session_id, "Editor returned a response that could not be parsed as JSON.", "error")
    except Exception as exc:
        logger.exception("Editor failed for session %s: %s", session_id, exc)
        await review_store.add_log(session_id, f"Editor error: {exc}", "error")

    return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_review(
    session_id: str,
    paper_title: str,
    paper_abstract: str,
    paper_text: str,
    bib_refs: list[str],
    num_reviewers: int = 3,
) -> None:
    try:
        await review_store.add_log(
            session_id,
            f"Launching {num_reviewers} independent reviewer agents in parallel…",
            "info",
        )

        # Run all reviewers in parallel
        tasks = [
            run_reviewer(
                session_id, i + 1, paper_title, paper_abstract, paper_text, bib_refs
            )
            for i in range(num_reviewers)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: list[ReviewerReport] = [r for r in results if isinstance(r, ReviewerReport)]
        successful = [report for report in valid if report.status == "done"]

        if not successful:
            await review_store.add_log(session_id, "All reviewers failed.", "error")
            await review_store.mark_error(session_id)
            await review_store.notify_complete(session_id)
            return

        # Editor
        editor_report = await run_editor(session_id, paper_title, successful)
        if editor_report is None:
            await review_store.add_log(session_id, "Review failed during editorial synthesis.", "error")
            await review_store.mark_error(session_id)
            await review_store.notify_complete(session_id)
            return

        await review_store.set_editor_report(session_id, editor_report)
        await review_store.mark_complete(session_id)
        await review_store.notify_complete(session_id)

    except Exception as exc:
        logger.exception("run_review crashed for session %s: %s", session_id, exc)
        await review_store.add_log(session_id, f"Fatal error: {exc}", "error")
        await review_store.mark_error(session_id)
        await review_store.notify_complete(session_id)
