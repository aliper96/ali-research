"""
PDF export for research & review sessions — uses fpdf2 (pure Python, no system deps).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from ..models.schemas import ResearchResult
    from ..models.review_schemas import ReviewSession

_INDIGO   = (79, 70, 229)
_INDIGO_L = (237, 238, 255)   # light indigo fill
_GRAY     = (110, 110, 120)
_LGRAY    = (210, 210, 215)
_DIFF: dict[str, tuple[int, int, int]] = {
    "easy":   (22,  163,  74),
    "medium": (161, 112,   0),
    "hard":   (185,  28,  28),
}
_LM = 18   # left margin mm
_RM = 18   # right margin mm
_TM = 14   # top margin mm


def _safe(text: str, maxlen: int = 0) -> str:
    """Sanitize to latin-1 for fpdf and optionally truncate."""
    cleaned = (text or "").encode("latin-1", errors="replace").decode("latin-1")
    if maxlen and len(cleaned) > maxlen:
        cleaned = cleaned[:maxlen].rstrip() + "..."
    return cleaned


class _PDF(FPDF):
    sid: str = ""

    def header(self) -> None:
        self.set_fill_color(*_INDIGO)
        self.rect(0, 0, 210, 2.5, "F")
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*_GRAY)
        self.cell(0, 6, f"ali_researcher  ·  session {self.sid[:8]}  ·  page {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


def _section(pdf: _PDF, title: str) -> None:
    """Draw a section heading with an indigo underline."""
    pdf.set_font("Helvetica", "B", 11.5)
    pdf.set_text_color(*_INDIGO)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_INDIGO)
    pdf.set_line_width(0.5)
    pdf.line(_LM, pdf.get_y(), 210 - _RM, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.set_draw_color(*_LGRAY)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)


def _divider(pdf: _PDF) -> None:
    pdf.set_draw_color(*_LGRAY)
    pdf.line(_LM, pdf.get_y(), 210 - _RM, pdf.get_y())
    pdf.ln(3)


def generate_research_pdf(
    session_id: str,
    topic: str,
    result: "ResearchResult",
) -> bytes:
    date_str = datetime.now().strftime("%B %d, %Y")
    page_w = 210 - _LM - _RM   # usable width

    pdf = _PDF()
    pdf.sid = session_id
    pdf.set_margins(_LM, _TM, _RM)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ── Title ───────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*_INDIGO)
    pdf.multi_cell(page_w, 9, _safe(topic, 200))
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(page_w, 5.5,
                   f"Session: {session_id}  |  Generated: {date_str}  |  ali_researcher")
    pdf.ln(3)

    # Stats bar
    pdf.set_fill_color(*_INDIGO_L)
    pdf.set_text_color(*_INDIGO)
    pdf.set_font("Helvetica", "B", 9)
    stats = (f"  {len(result.papers)} papers"
             f"   |   {len(result.gap_analysis)} research gaps"
             f"   |   {len(result.implementation_roadmap)} roadmap steps")
    pdf.cell(page_w, 9, stats, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    # ── Summary ─────────────────────────────────────────────────────────────
    if result.summary:
        _section(pdf, "Summary")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_fill_color(248, 248, 255)
        y0 = pdf.get_y()
        pdf.multi_cell(page_w, 5.8, _safe(result.summary), fill=True)
        # Accent bar on left
        pdf.set_draw_color(*_INDIGO)
        pdf.set_line_width(1.0)
        pdf.line(_LM, y0, _LM, pdf.get_y())
        pdf.set_line_width(0.2)
        pdf.ln(4)

    # ── Key Concepts ─────────────────────────────────────────────────────────
    if result.key_concepts:
        _section(pdf, "Key Concepts")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(page_w, 6, "  |  ".join(_safe(c) for c in result.key_concepts))
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

    # ── Papers ───────────────────────────────────────────────────────────────
    _section(pdf, f"Papers ({len(result.papers)})")

    for idx, paper in enumerate(result.papers, 1):
        if pdf.get_y() > 252:
            pdf.add_page()

        # Resolve the best URL for this paper
        paper_url = (
            paper.url
            or (f"https://arxiv.org/abs/{paper.arxiv_id}" if paper.arxiv_id else "")
            or (f"https://doi.org/{paper.doi}" if paper.doi else "")
        )

        # Number + title (title is a clickable link when URL available)
        num_w = 8
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(num_w, 6, f"{idx}.")
        pdf.set_font("Helvetica", "B", 10)
        title_text = _safe(paper.title, 160) + (f" ({paper.year})" if paper.year else "")
        if paper_url:
            pdf.set_text_color(50, 40, 200)   # blue-indigo for linked titles
            pdf.multi_cell(page_w - num_w, 6, title_text, link=paper_url)
        else:
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(page_w - num_w, 6, title_text)
        pdf.set_text_color(0, 0, 0)

        # Authors
        if paper.authors:
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*_GRAY)
            authors_str = ", ".join(paper.authors[:6])
            if len(paper.authors) > 6:
                authors_str += " et al."
            pdf.multi_cell(page_w, 5, _safe(authors_str))

        # Meta: venue · citations · source · arxiv
        meta: list[str] = []
        if paper.venue:          meta.append(_safe(paper.venue, 60))
        if paper.citation_count: meta.append(f"{paper.citation_count:,} citations")
        if paper.source:         meta.append(paper.source)
        if paper.arxiv_id:       meta.append(f"arXiv:{paper.arxiv_id}")
        if meta:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*_GRAY)
            pdf.multi_cell(page_w, 5, "  |  ".join(meta))
            pdf.set_text_color(0, 0, 0)

        # URL as a visible clickable link (shown shortened)
        if paper_url:
            display_url = _safe(paper_url, 90)
            pdf.set_text_color(67, 56, 202)
            pdf.set_font("Helvetica", "", 7.5)
            pdf.multi_cell(page_w, 4.5, display_url, link=paper_url)
            pdf.set_text_color(0, 0, 0)

        # Abstract preview
        if paper.abstract:
            pdf.set_font("Helvetica", "I", 8.5)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(page_w, 5, _safe(paper.abstract, 320))
            pdf.set_text_color(0, 0, 0)

        pdf.ln(3)
        if idx < len(result.papers):
            _divider(pdf)

    # ── Research Gaps ─────────────────────────────────────────────────────────
    if result.gap_analysis:
        pdf.add_page()
        _section(pdf, "Research Gaps")
        for i, gap in enumerate(result.gap_analysis, 1):
            num_w = 8
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_INDIGO)
            pdf.cell(num_w, 6, f"{i}.")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(page_w - num_w, 6, _safe(gap))
            pdf.ln(2)

    # ── Implementation Roadmap ────────────────────────────────────────────────
    if result.implementation_roadmap:
        if not result.gap_analysis:
            pdf.add_page()
        else:
            pdf.ln(5)
        _section(pdf, "Implementation Roadmap")

        for i, step in enumerate(result.implementation_roadmap, 1):
            if pdf.get_y() > 255:
                pdf.add_page()

            diff = step.difficulty.lower()
            dr, dg, db = _DIFF.get(diff, _GRAY)
            num_w = 8

            # Step num
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*_INDIGO)
            pdf.cell(num_w, 6, f"{i}.")

            # Difficulty badge colour
            pdf.set_text_color(dr, dg, db)
            pdf.set_font("Helvetica", "B", 8)
            badge = f"[{diff}] "
            badge_w = pdf.get_string_width(badge) + 2
            pdf.cell(badge_w, 6, badge)

            # Step name
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.multi_cell(page_w - num_w - badge_w, 6, _safe(step.step, 100))

            # Description
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*_GRAY)
            pdf.multi_cell(page_w, 5.5, _safe(step.description))
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)

    return bytes(pdf.output())
