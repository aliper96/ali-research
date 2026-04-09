"""
PDF export for research & review sessions — uses fpdf2 (pure Python, no system deps).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from ..models.schemas import ResearchResult
    from ..models.review_schemas import ReviewSession, EditorReport, ReviewerReport

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


# ---------------------------------------------------------------------------
# Review PDF
# ---------------------------------------------------------------------------

_REC_LABEL = {
    "accept":         "Accept",
    "minor_revision": "Minor Revision",
    "major_revision": "Major Revision",
    "reject":         "Reject",
}
_REC_COLOR: dict[str, tuple[int, int, int]] = {
    "accept":         (22,  163,  74),
    "minor_revision": (14,  165, 233),
    "major_revision": (202, 138,   4),
    "reject":         (185,  28,  28),
}


def _score_bar(pdf: _PDF, label: str, value: float, page_w: float) -> None:
    """Draw a labelled score bar (0-10)."""
    half = (page_w - 6) / 2
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(half * 0.55, 5, _safe(label))
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*_INDIGO)
    pdf.cell(half * 0.25, 5, f"{value:.1f}/10", align="R")
    # mini bar
    bar_w = half * 0.20
    bar_x = pdf.get_x() + 2
    bar_y = pdf.get_y() + 1.5
    pdf.set_fill_color(*_LGRAY)
    pdf.rect(bar_x, bar_y, bar_w, 2.5, "F")
    filled = bar_w * (value / 10)
    pdf.set_fill_color(*_INDIGO)
    if filled > 0:
        pdf.rect(bar_x, bar_y, filled, 2.5, "F")
    pdf.ln(5)
    pdf.set_text_color(0, 0, 0)


def _bullet_list(pdf: _PDF, items: list[str], page_w: float,
                 color: tuple[int, int, int], symbol: str = "•") -> None:
    bw = 6
    for item in items:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*color)
        pdf.cell(bw, 5.5, symbol)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(50, 50, 60)
        pdf.multi_cell(page_w - bw, 5.5, _safe(item))
    pdf.set_text_color(0, 0, 0)


def generate_review_pdf(session_id: str, session: "ReviewSession") -> bytes:
    """Generate a formatted PDF for a completed peer review session."""
    from ..models.review_schemas import EditorReport  # local import to avoid circular

    date_str = datetime.now().strftime("%B %d, %Y")
    page_w = 210 - _LM - _RM

    pdf = _PDF()
    pdf.sid = session_id
    pdf.set_margins(_LM, _TM, _RM)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ── Title ───────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*_INDIGO)
    pdf.multi_cell(page_w, 9, _safe(session.paper_title or "Untitled Paper", 200))
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(page_w, 5.5,
                   f"Session: {session_id}  |  Generated: {date_str}  |  ali_researcher  ·  Peer Review")
    pdf.ln(3)

    # Stats bar
    done_count = sum(1 for r in session.reviewer_reports if r.status == "done")
    pdf.set_fill_color(*_INDIGO_L)
    pdf.set_text_color(*_INDIGO)
    pdf.set_font("Helvetica", "B", 9)
    stats = (f"  {done_count}/{session.num_reviewers} reviewers"
             f"   |   status: {session.status}")
    if session.editor_report:
        rec = session.editor_report.final_recommendation
        stats += f"   |   decision: {_REC_LABEL.get(rec, rec)}"
    pdf.cell(page_w, 9, stats, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    # ── Editor's Decision ────────────────────────────────────────────────────
    ed: EditorReport | None = session.editor_report
    if ed:
        _section(pdf, "Editor's Decision")

        rec = ed.final_recommendation
        rec_r, rec_g, rec_b = _REC_COLOR.get(rec, _GRAY)

        # Recommendation badge row
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(rec_r, rec_g, rec_b)
        pdf.cell(0, 7, _REC_LABEL.get(rec, rec), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

        # Metadata row
        meta_parts = []
        if ed.novelty_verdict:   meta_parts.append(f"Novelty: {_safe(ed.novelty_verdict)}")
        if ed.publishability:    meta_parts.append(f"Publishability: {_safe(ed.publishability)}")
        meta_parts.append(f"Reviewer agreement: {int(ed.reviewer_agreement * 100)}%")
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 6, "  |  ".join(meta_parts), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

        # Score grid (2 columns)
        scores = [
            ("Novelty",      ed.novelty_score),
            ("Technical",    ed.technical_score),
            ("Clarity",      ed.clarity_score),
            ("Contribution", ed.contribution_score),
        ]
        col_w = page_w / 2
        for i, (lbl, val) in enumerate(scores):
            if i % 2 == 0 and i > 0:
                pdf.ln(1)
            _score_bar(pdf, lbl, val, col_w)
        pdf.ln(3)

        # Consensus summary
        if ed.consensus_summary:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_fill_color(248, 248, 255)
            y0 = pdf.get_y()
            pdf.multi_cell(page_w, 5.8, _safe(ed.consensus_summary), fill=True)
            pdf.set_draw_color(*_INDIGO)
            pdf.set_line_width(1.0)
            pdf.line(_LM, y0, _LM, pdf.get_y())
            pdf.set_line_width(0.2)
            pdf.ln(4)

        # Action items
        if ed.action_items:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_GRAY)
            pdf.cell(0, 6, "Required actions for authors:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            for i, item in enumerate(ed.action_items, 1):
                bw = 8
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(*_INDIGO)
                pdf.cell(bw, 5.5, f"{i}.")
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(50, 50, 60)
                pdf.multi_cell(page_w - bw, 5.5, _safe(item))
            pdf.set_text_color(0, 0, 0)
            pdf.ln(3)

        # Consolidated issues / strengths
        if ed.major_issues:
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(185, 28, 28)
            pdf.cell(0, 6, f"MAJOR ISSUES ({len(ed.major_issues)})", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            _bullet_list(pdf, ed.major_issues, page_w, (185, 28, 28), "✗")
            pdf.ln(2)
        if ed.minor_issues:
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(202, 138, 4)
            pdf.cell(0, 6, f"MINOR ISSUES ({len(ed.minor_issues)})", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            _bullet_list(pdf, ed.minor_issues, page_w, (202, 138, 4), "!")
            pdf.ln(2)
        if ed.strengths:
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(22, 163, 74)
            pdf.cell(0, 6, f"STRENGTHS ({len(ed.strengths)})", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            _bullet_list(pdf, ed.strengths, page_w, (22, 163, 74), "+")
            pdf.ln(2)

    # ── Individual Reviewer Reports ──────────────────────────────────────────
    done_reports = [r for r in session.reviewer_reports if r.status == "done"]
    if done_reports:
        pdf.add_page()
        _section(pdf, f"Individual Reviews ({len(done_reports)})")

        for idx, report in enumerate(done_reports):
            if pdf.get_y() > 248:
                pdf.add_page()

            rec = report.recommendation
            rec_r, rec_g, rec_b = _REC_COLOR.get(rec, _GRAY)

            # Reviewer header
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_INDIGO)
            pdf.cell(0, 7, f"Reviewer {report.reviewer_id}", new_x="LMARGIN", new_y="NEXT")

            if report.persona:
                pdf.set_font("Helvetica", "I", 8.5)
                pdf.set_text_color(*_GRAY)
                pdf.cell(0, 5, _safe(report.persona, 120), new_x="LMARGIN", new_y="NEXT")

            # Rec + overall score
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(rec_r, rec_g, rec_b)
            pdf.cell(0, 5.5, f"{_REC_LABEL.get(rec, rec)}  ·  Overall: {report.overall_score:.1f}/10",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

            # Score bars (2-column layout)
            scores = [
                ("Novelty",      report.novelty_score),
                ("Technical",    report.technical_score),
                ("Clarity",      report.clarity_score),
                ("Contribution", report.contribution_score),
            ]
            col_w = page_w / 2
            for lbl, val in scores:
                _score_bar(pdf, lbl, val, col_w)
            pdf.ln(2)

            # Summary
            if report.summary:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(50, 50, 60)
                pdf.multi_cell(page_w, 5.5, _safe(report.summary, 600))
                pdf.set_text_color(0, 0, 0)
                pdf.ln(2)

            # Issues / Strengths
            if report.major_issues:
                pdf.set_font("Helvetica", "B", 8.5)
                pdf.set_text_color(185, 28, 28)
                pdf.cell(0, 5, "Major issues:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                _bullet_list(pdf, report.major_issues, page_w, (185, 28, 28), "✗")
            if report.minor_issues:
                pdf.set_font("Helvetica", "B", 8.5)
                pdf.set_text_color(202, 138, 4)
                pdf.cell(0, 5, "Minor issues:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                _bullet_list(pdf, report.minor_issues, page_w, (202, 138, 4), "!")
            if report.strengths:
                pdf.set_font("Helvetica", "B", 8.5)
                pdf.set_text_color(22, 163, 74)
                pdf.cell(0, 5, "Strengths:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                _bullet_list(pdf, report.strengths, page_w, (22, 163, 74), "+")
            if report.missing_citations:
                pdf.set_font("Helvetica", "B", 8.5)
                pdf.set_text_color(14, 165, 233)
                pdf.cell(0, 5, "Missing citations:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                _bullet_list(pdf, report.missing_citations, page_w, _GRAY)

            pdf.ln(3)
            if idx < len(done_reports) - 1:
                _divider(pdf)
                pdf.ln(2)

    # ── Abstract ─────────────────────────────────────────────────────────────
    if session.paper_abstract:
        pdf.add_page()
        _section(pdf, "Paper Abstract")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(50, 50, 60)
        pdf.multi_cell(page_w, 5.8, _safe(session.paper_abstract, 3000))
        pdf.set_text_color(0, 0, 0)

    return bytes(pdf.output())
