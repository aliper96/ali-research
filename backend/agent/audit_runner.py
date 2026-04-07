"""
Audit agent: compare a paper's claims against its public codebase.

Given an arXiv ID, DOI, URL, or title:
1. Fetch the paper and extract key claims
2. Search GitHub for the paper's public repository
3. Read repo README + key files
4. For each claim, find supporting/contradicting evidence
5. Return structured AuditResult
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import openai

from ..models.audit_schemas import AuditClaim, AuditResult, AuditSession
from ..models.schemas import LogEntry
from ..storage.audit_store import audit_store
from .tools import TOOL_SPECS, execute_tool

logger = logging.getLogger(__name__)

AUDIT_SYSTEM_PROMPT = """You are a rigorous paper auditor. Your job is to compare a research paper's key claims against its public codebase.

Workflow:
1. Use resolve_paper_id or get_arxiv_paper to fetch the paper metadata and abstract.
2. Use extract_claims to pull the paper's main verifiable claims (focus on reproducibility claims: "we achieve X% on Y benchmark", "our method runs in O(n)", "code is available at ...").
3. Use search_code to find the paper's GitHub repository (try: "<first author last name> <year> <key term from title>").
4. If a repo is found:
   a. Use fetch_url with the repo root URL (e.g. "https://github.com/owner/repo") to read the README.
   b. Use fetch_url on key source files you find referenced (e.g. "https://github.com/owner/repo/blob/main/train.py").
   c. Look for benchmark results, model cards, or experiment scripts that confirm/deny the paper's claims.
5. For each claim, assess based on what you actually read: does the repo contain evidence supporting, partially supporting, contradicting, or not addressing this claim?
6. Return a JSON audit report.

Be honest. Mark claims as "unverified" if the repo doesn't address them, not "contradicted" unless you find explicit contradictions.

At the end, return ONLY this JSON object:
{
  "paper_title": "Full paper title",
  "paper_url": "https://...",
  "repo_url": "https://github.com/...",
  "repo_found": true,
  "claims": [
    {
      "claim": "The claim text from the paper",
      "status": "verified|partially_verified|unverified|contradicted",
      "evidence": "What you found in the repo supporting or contradicting this claim",
      "evidence_url": "https://github.com/.../file#L42"
    }
  ],
  "verdict": "matches|partial_match|mismatch|no_repo_found",
  "confidence": 0.85,
  "audit_notes": "Overall notes about reproducibility and code quality"
}"""


def _extract_json(text: str) -> dict | None:
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
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
                        return json.loads(text[start: i + 1])
                    except json.JSONDecodeError:
                        break
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _parse_audit_result(data: dict) -> AuditResult:
    valid_statuses = {"verified", "partially_verified", "unverified", "contradicted"}
    valid_verdicts = {"matches", "partial_match", "mismatch", "no_repo_found"}

    claims: list[AuditClaim] = []
    for raw in data.get("claims", []):
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status", "unverified")).lower()
        if status not in valid_statuses:
            status = "unverified"
        claims.append(AuditClaim(
            claim=str(raw.get("claim", "")),
            status=status,  # type: ignore[arg-type]
            evidence=str(raw.get("evidence", "")),
            evidence_url=str(raw.get("evidence_url", "")),
        ))

    verdict = str(data.get("verdict", "no_repo_found")).lower()
    if verdict not in valid_verdicts:
        verdict = "no_repo_found"

    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    return AuditResult(
        paper_title=str(data.get("paper_title", "")),
        paper_url=str(data.get("paper_url", "")),
        repo_url=str(data.get("repo_url", "")),
        repo_found=bool(data.get("repo_found", False)),
        claims=claims,
        verdict=verdict,  # type: ignore[arg-type]
        confidence=confidence,
        audit_notes=str(data.get("audit_notes", "")),
    )


async def run_audit(session_id: str, user_input: str) -> None:
    model = os.getenv("LLM_MODEL", "gpt-5.4-nano")
    client = openai.AsyncOpenAI()

    await audit_store.add_log(session_id, f"Starting audit for: {user_input}", "info")
    await audit_store.set_progress(session_id, 5)

    messages: list[dict] = [
        {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Audit this paper: {user_input}\n\n"
                "Extract its key claims, find its public repository, and verify each claim against the code. "
                "Return the JSON audit report when done."
            ),
        },
    ]

    max_tool_calls = 12
    tool_call_count = 0

    async def _call_model(msgs: list[dict]) -> Any:
        return await client.chat.completions.create(
            model=model,
            max_completion_tokens=4000,
            tools=TOOL_SPECS,  # type: ignore[arg-type]
            messages=msgs,  # type: ignore[arg-type]
        )

    async def _finalise(result_text: str) -> bool:
        result_data = _extract_json(result_text)
        if result_data is not None:
            result = _parse_audit_result(result_data)
            session = audit_store.get_session(session_id)
            if session is not None:
                session.result = result
                session.status = "completed"
                session.progress.percentage = 100
                await audit_store.update_session(session)
            verified = sum(1 for c in result.claims if c.status == "verified")
            await audit_store.add_log(
                session_id,
                f"Audit complete — verdict: {result.verdict}, {verified}/{len(result.claims)} claims verified.",
                "success",
            )
            return True
        await audit_store.add_log(session_id, "Warning: could not parse audit JSON.", "warning")
        session = audit_store.get_session(session_id)
        if session is not None:
            session.status = "error"
            await audit_store.update_session(session)
        return False

    try:
        while tool_call_count <= max_tool_calls:
            await audit_store.add_log(session_id, f"Calling {model}…", "info")
            response = await _call_model(messages)
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            assistant_msg: dict = {"role": "assistant", "content": choice.message.content}
            if choice.message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in choice.message.tool_calls
                ]
            messages.append(assistant_msg)

            if finish_reason == "stop":
                await _finalise(choice.message.content or "")
                await audit_store.notify_complete(session_id)
                break

            if finish_reason == "tool_calls" and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_call_count += 1
                    tool_name = tc.function.name
                    try:
                        tool_input = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_input = {}

                    await audit_store.add_log(session_id, f"Using tool: {tool_name}", "info")
                    await audit_store.set_progress(session_id, min(5 + int(tool_call_count / max_tool_calls * 85), 90))

                    try:
                        result_str = await execute_tool(tool_name, tool_input)
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})
                    except Exception as exc:
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"Error: {exc}"})
                continue

            break

        else:
            messages.append({"role": "user", "content": "Maximum tool calls reached. Return the JSON audit report now."})
            response = await _call_model(messages)
            await _finalise(response.choices[0].message.content or "")
            await audit_store.notify_complete(session_id)

    except Exception as exc:
        logger.exception("run_audit raised for session %s: %s", session_id, exc)
        session = audit_store.get_session(session_id)
        if session is not None:
            session.status = "error"
            await audit_store.update_session(session)
        await audit_store.add_log(session_id, f"Fatal error: {exc}", "error")
        await audit_store.notify_complete(session_id)
