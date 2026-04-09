"""
Draft — convert a completed research session into a structured document.
Supports formats: brief, paper, blog.
"""
from __future__ import annotations
import json, logging, os
import openai
from .researcher import _extract_json

logger = logging.getLogger(__name__)

DRAFT_PROMPTS = {
    "brief": """Convert these research findings into a concise executive brief (1-2 pages).
Structure: Background → Key Findings → Implications → Recommended Actions.
Use clear headings, bullet points for key facts, and plain language.""",

    "paper": """Convert these research findings into a structured academic paper draft.
Structure: Abstract → Introduction → Related Work → Methodology Overview → Results & Analysis → Discussion → Conclusion → References.
Use formal academic tone. Include inline citations like [Author, Year].""",

    "blog": """Convert these research findings into an engaging technical blog post.
Structure: Hook → What is this about → Key papers and what they found → Why it matters → What to read next.
Use accessible language, avoid jargon, include concrete examples.""",
}

async def run_draft(session_result: dict, format: str = "brief", title: str = "") -> dict:
    """
    session_result: the ResearchResult dict from a completed session.
    Returns: {"title": ..., "format": ..., "content": "full markdown document", "word_count": N}
    """
    client = openai.AsyncOpenAI()
    model = os.getenv("LLM_MODEL", "gpt-5.4-nano")
    prompt = DRAFT_PROMPTS.get(format, DRAFT_PROMPTS["brief"])

    papers_summary = json.dumps([
        {"title": p.get("title"), "authors": p.get("authors", [])[:2],
         "year": p.get("year"), "key_finding": p.get("relevance_reason", ""),
         "url": p.get("url")}
        for p in session_result.get("papers", [])[:20]
    ], indent=2)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content":
            f"Title suggestion: {title or 'Research findings'}\n\n"
            f"Summary:\n{session_result.get('summary', '')}\n\n"
            f"Key concepts: {', '.join(session_result.get('key_concepts', []))}\n\n"
            f"Papers ({len(session_result.get('papers', []))}):\n{papers_summary}\n\n"
            f"Gaps: {'; '.join(session_result.get('gap_analysis', []))}\n\n"
            "Write the full document in Markdown now."},
    ]
    resp = await client.responses.create(
        model=model,
        instructions=messages[0]["content"],
        input=messages[1]["content"],
        max_output_tokens=6000,
    )
    content = resp.output_text or ""
    # Extract title from first heading if present
    import re
    heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    doc_title = heading.group(1) if heading else (title or "Research Draft")
    return {
        "title": doc_title,
        "format": format,
        "content": content,
        "word_count": len(content.split()),
    }
