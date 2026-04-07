"""
Artifact store — saves generated files per session to disk under outputs/.

Directory layout:
  outputs/
    <session_id>/
      summary.md
      papers.json
      report.md          ← full formatted Markdown report
      bibliography.bib
      provenance.json    ← metadata: when, what agent, paper count, etc.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"


def _session_dir(session_id: str) -> Path:
    d = _OUTPUTS_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_research_artifacts(session_id: str, result_data: dict, agent_type: str = "research") -> list[str]:
    """
    Write all artifacts for a completed session to disk.
    Returns list of filenames created.
    """
    d = _session_dir(session_id)
    created: list[str] = []

    summary = str(result_data.get("summary", ""))
    papers = result_data.get("papers", [])
    gaps = result_data.get("gap_analysis", [])
    roadmap = result_data.get("implementation_roadmap", [])
    concepts = result_data.get("key_concepts", [])

    # summary.md
    (d / "summary.md").write_text(summary, encoding="utf-8")
    created.append("summary.md")

    # papers.json
    (d / "papers.json").write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
    created.append("papers.json")

    # report.md — full formatted document
    lines = [f"# Research Report\n\n## Summary\n\n{summary}\n"]
    if concepts:
        lines.append("## Key Concepts\n\n" + "  ".join(f"`{c}`" for c in concepts) + "\n")
    if papers:
        lines.append("## Papers\n")
        for p in papers:
            authors = ", ".join(p.get("authors", [])[:3])
            year = p.get("year", "")
            url = p.get("url", "")
            title = p.get("title", "Untitled")
            score = p.get("relevance_score", 0)
            lines.append(f"### [{title}]({url})\n")
            lines.append(f"**{authors}** ({year}) · relevance {int(score*100)}%\n")
            if p.get("abstract"):
                lines.append(f"> {p['abstract'][:300]}…\n")
            if p.get("relevance_reason"):
                lines.append(f"*Why relevant:* {p['relevance_reason']}\n")
    if gaps:
        lines.append("## Research Gaps\n\n" + "\n".join(f"- {g}" for g in gaps) + "\n")
    if roadmap:
        lines.append("## Implementation Roadmap\n")
        for step in roadmap:
            diff = step.get("difficulty", "medium")
            lines.append(f"### {step.get('step', '')} `[{diff}]`\n{step.get('description', '')}\n")
    (d / "report.md").write_text("\n".join(lines), encoding="utf-8")
    created.append("report.md")

    # bibliography.bib
    bib_entries = []
    for p in papers:
        authors_raw = p.get("authors", [])
        first = (authors_raw[0].split()[-1].lower() if authors_raw else "unknown")
        year = p.get("year", "nd")
        first_word = (p.get("title", "untitled").split()[0].lower())
        key = f"{first}{year}{first_word}"
        bib_entries.append(
            "@article{" + key + ",\n"
            + f"  title = {{{p.get('title', '')}}},\n"
            + f"  author = {{{' and '.join(authors_raw)}}},\n"
            + f"  year = {{{year}}},\n"
            + f"  url = {{{p.get('url', '')}}},\n"
            + f"  doi = {{{p.get('doi') or ''}}}\n"
            + "}"
        )
    (d / "bibliography.bib").write_text("\n\n".join(bib_entries), encoding="utf-8")
    created.append("bibliography.bib")

    # provenance.json
    provenance = {
        "session_id": session_id,
        "agent_type": agent_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_count": len(papers),
        "gap_count": len(gaps),
        "roadmap_steps": len(roadmap),
    }
    (d / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    created.append("provenance.json")

    logger.info("Artifacts for session %s: %s", session_id, created)
    return created


def list_artifacts(session_id: str) -> list[dict[str, Any]]:
    d = _OUTPUTS_DIR / session_id
    if not d.exists():
        return []
    result = []
    for f in sorted(d.iterdir()):
        if f.is_file():
            stat = f.stat()
            result.append({
                "filename": f.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
    return result


def read_artifact(session_id: str, filename: str) -> bytes | None:
    path = _OUTPUTS_DIR / session_id / filename
    if not path.exists() or not path.is_file():
        return None
    # Safety: prevent path traversal
    try:
        path.relative_to(_OUTPUTS_DIR)
    except ValueError:
        return None
    return path.read_bytes()


def list_all_sessions_with_artifacts() -> list[dict[str, Any]]:
    if not _OUTPUTS_DIR.exists():
        return []
    result = []
    for d in sorted(_OUTPUTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir():
            files = [f.name for f in d.iterdir() if f.is_file()]
            provenance_path = d / "provenance.json"
            meta: dict = {}
            if provenance_path.exists():
                try:
                    meta = json.loads(provenance_path.read_text())
                except Exception:
                    pass
            result.append({
                "session_id": d.name,
                "files": files,
                **meta,
            })
    return result
