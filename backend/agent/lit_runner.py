"""
Literature Review workflow — structured lit review distinct from general research.

Produces: chronological timeline, methodology table, consensus themes,
state-of-the-art section, open problems, and reading list.
"""
from __future__ import annotations
import json, logging, os, re
from .researcher import _extract_json, parse_result, _extract_json
from .tools import TOOL_SPECS, execute_tool
from ..storage import db as _db
from ..storage.artifact_store import save_research_artifacts
import openai, asyncio

logger = logging.getLogger(__name__)

LIT_SYSTEM_PROMPT = """You are a systematic literature reviewer. Given a research topic, produce a structured literature review.

Your workflow:
1. search_session_memory — check prior sessions for known papers
2. search_papers + search_arxiv + search_semantic_scholar — gather 15-25 papers minimum
3. timeline_topic — build chronological picture of the field
4. For each major paper: extract_methodology, extract_results
5. compare_papers — compare the strongest papers directly
6. find_gaps — identify open problems
7. citation_check — verify your summary claims

Literature review structure to produce:
- **State of the art**: what methods/approaches dominate today
- **Historical progression**: how the field evolved year by year
- **Methodology comparison**: table of approaches and their trade-offs
- **Consensus**: what the community agrees on
- **Controversies**: active debates and disagreements
- **Open problems**: what remains unsolved
- **Recommended reading list**: ranked 5-10 papers for a newcomer

Return the standard research JSON but make the summary follow this structure explicitly."""

async def run_lit_review(session_id: str, user_input: str, depth: str = "deep") -> None:
    from ..storage.lit_store import lit_store
    client = openai.AsyncOpenAI()
    model = os.getenv("LLM_MODEL", "gpt-5.4-nano")
    max_calls = {"standard": 14, "deep": 22}.get(depth, 14)

    await lit_store.add_log(session_id, f"Literature review started: {user_input}", "info")
    await lit_store.set_progress(session_id, 5)

    messages: list[dict] = [
        {"role": "system", "content": LIT_SYSTEM_PROMPT},
        {"role": "user", "content":
            f"Conduct a systematic literature review on: {user_input}\n"
            f"Depth: {depth}. Session: {session_id}\n"
            "Be thorough — gather at least 15 papers and follow the structured review format."},
    ]
    tool_calls = 0

    async def _call():
        return await client.chat.completions.create(
            model=model, max_completion_tokens=8000,
            tools=TOOL_SPECS, messages=messages)  # type: ignore[arg-type]

    try:
        while tool_calls <= max_calls:
            resp = await _call()
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
                data = _extract_json(choice.message.content or "")
                if data:
                    result = parse_result(data, session_id)
                    session = lit_store.get_session(session_id)
                    if session:
                        session.result = result
                        session.status = "completed"
                        session.progress.percentage = 100
                        await lit_store.update_session(session)
                    await lit_store.add_log(session_id, f"Lit review complete — {len(result.papers)} papers", "success")
                    try:
                        await _db.save_papers_memory([p.model_dump() for p in result.papers], session_id)
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, save_research_artifacts, session_id, data, "lit_review")
                    except Exception as exc:
                        logger.warning("Post-lit cleanup failed: %s", exc)
                else:
                    session = lit_store.get_session(session_id)
                    if session:
                        session.status = "error"
                        await lit_store.update_session(session)
                break

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls += 1
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    await lit_store.add_log(session_id, f"Using tool: {tc.function.name}", "info")
                    await lit_store.set_progress(session_id, min(5 + int(tool_calls / max_calls * 85), 90))
                    try:
                        out = await execute_tool(tc.function.name, args)
                    except Exception as exc:
                        out = json.dumps({"error": str(exc)})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
                continue
            break
        else:
            messages.append({"role": "user", "content": "Max tool calls reached. Return the lit review JSON now."})
            resp = await _call()
            data = _extract_json(resp.choices[0].message.content or "")
            if data:
                result = parse_result(data, session_id)
                session = lit_store.get_session(session_id)
                if session:
                    session.result = result
                    session.status = "completed"
                    session.progress.percentage = 100
                    await lit_store.update_session(session)

    except Exception as exc:
        logger.exception("run_lit_review failed: %s", exc)
        session = lit_store.get_session(session_id)
        if session:
            session.status = "error"
            await lit_store.update_session(session)
        await lit_store.add_log(session_id, f"Fatal error: {exc}", "error")
    finally:
        await lit_store.notify_complete(session_id)
