"""
Compare — build a structured comparison matrix from a list of topics, papers, or approaches.
Returns synchronously (no SSE needed for this workflow).
"""
from __future__ import annotations
import json, logging, os
import openai
from .researcher import _extract_json
from .tools import execute_tool

logger = logging.getLogger(__name__)

COMPARE_PROMPT = """You are a technical analyst. Given a list of items to compare (papers, methods, approaches, or tools), build a structured comparison matrix.

For each item, evaluate it across these dimensions (adapt dimensions to the items):
- Core idea / approach
- Key strengths
- Key limitations
- Performance / results (if applicable)
- Use cases / when to choose this
- Recency / maturity
- Reproducibility

Return ONLY this JSON:
{
  "title": "Comparison: X vs Y vs Z",
  "items": ["item1", "item2", ...],
  "dimensions": ["Dimension 1", "Dimension 2", ...],
  "matrix": {
    "item1": {"Dimension 1": "value", "Dimension 2": "value", ...},
    "item2": {...}
  },
  "summary": "2-3 sentences on key takeaways",
  "recommendation": "When to use which approach"
}"""

async def run_compare(items: list[str], context: str = "") -> dict:
    client = openai.AsyncOpenAI()
    model = os.getenv("LLM_MODEL", "gpt-5.4-nano")

    # First, gather paper data for any arXiv IDs or known papers
    enriched_items = []
    for item in items:
        import re
        if re.search(r"\d{4}\.\d{4,5}", item):
            try:
                data = await execute_tool("get_arxiv_paper", {"arxiv_id": item})
                paper = json.loads(data)
                if paper.get("title"):
                    enriched_items.append(f"{paper['title']} (arXiv:{item})")
                    continue
            except Exception:
                pass
        enriched_items.append(item)

    messages = [
        {"role": "system", "content": COMPARE_PROMPT},
        {"role": "user", "content":
            f"Compare these items:\n" + "\n".join(f"- {i}" for i in enriched_items) +
            (f"\n\nContext: {context}" if context else "")},
    ]
    resp = await client.responses.create(
        model=model,
        instructions=messages[0]["content"],
        input=messages[1]["content"],
        max_output_tokens=4000,
    )
    text = resp.output_text or ""
    data = _extract_json(text)
    if data:
        return data
    return {"title": "Comparison", "items": items, "dimensions": [], "matrix": {},
            "summary": text[:500], "recommendation": ""}
