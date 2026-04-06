"""
Extract title, abstract, and full text from PDF or LaTeX submissions.
Optionally parses a .bib file for reference metadata.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field


@dataclass
class ParsedPaper:
    title: str = "Unknown Title"
    abstract: str = ""
    full_text: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    bib_refs: list[str] = field(default_factory=list)   # formatted citation strings
    source_type: str = "unknown"   # "pdf" | "latex"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def parse_pdf(content: bytes) -> ParsedPaper:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n".join(pages_text).strip()

    title = _extract_pdf_title(full_text)
    abstract = _extract_pdf_abstract(full_text)

    return ParsedPaper(
        title=title,
        abstract=abstract,
        full_text=full_text[:20_000],   # cap to avoid huge context
        source_type="pdf",
    )


def _extract_pdf_title(text: str) -> str:
    """Heuristic: first non-empty line is usually the title."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 10:
            return line[:200]
    return "Unknown Title"


def _extract_pdf_abstract(text: str) -> str:
    # Try to find "Abstract" header
    m = re.search(
        r"(?i)abstract[\s\n:–-]+(.*?)(?=\n[A-Z][A-Z\s]{3,}|\n\d+\s+Introduction|\Z)",
        text,
        re.DOTALL,
    )
    if m:
        return m.group(1).strip()[:2000]
    # Fallback: second paragraph
    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 100]
    return paras[1][:2000] if len(paras) > 1 else paras[0][:2000] if paras else ""


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

def parse_latex(content: str) -> ParsedPaper:
    title = _latex_extract_cmd("title", content) or "Unknown Title"
    abstract = _latex_extract_env("abstract", content) or ""

    # Strip LaTeX markup for readable plain text
    plain = _strip_latex(content)

    # Extract main sections
    sections: dict[str, str] = {}
    sec_pattern = re.finditer(
        r"\\(?:section|subsection)\*?\{([^}]+)\}\s*(.*?)(?=\\(?:section|subsection)|\\end\{document\}|\Z)",
        content,
        re.DOTALL,
    )
    for m in sec_pattern:
        name = m.group(1).strip()
        body = _strip_latex(m.group(2))[:3000]
        sections[name] = body

    return ParsedPaper(
        title=_strip_latex(title).strip(),
        abstract=_strip_latex(abstract).strip()[:2000],
        full_text=plain[:20_000],
        sections=sections,
        source_type="latex",
    )


def _latex_extract_cmd(cmd: str, src: str) -> str:
    """Extract first argument of a LaTeX command like \\title{...}."""
    m = re.search(rf"\\{cmd}\{{([^}}]+)\}}", src, re.DOTALL)
    return m.group(1) if m else ""


def _latex_extract_env(env: str, src: str) -> str:
    m = re.search(
        rf"\\begin\{{{env}\}}(.*?)\\end\{{{env}\}}", src, re.DOTALL
    )
    return m.group(1) if m else ""


def _strip_latex(text: str) -> str:
    """Remove LaTeX commands, keeping their text arguments where possible."""
    # Remove comments
    text = re.sub(r"%.*", "", text)
    # Unwrap common single-arg commands (\textbf{x} → x)
    for _ in range(5):
        text = re.sub(r"\\(?:textbf|textit|emph|text|mathrm|mathbf|mbox|hbox|vspace|hspace)\{([^}]*)\}", r"\1", text)
    # Remove remaining commands with args
    text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", text)
    # Remove bare commands
    text = re.sub(r"\\[a-zA-Z@]+\*?", " ", text)
    # Remove environments like \begin{...}...\end{...}  keeping content
    text = re.sub(r"\\(?:begin|end)\{[^}]+\}", "", text)
    # Clean up braces and special chars
    text = re.sub(r"[{}$^_~]", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# BibTeX
# ---------------------------------------------------------------------------

def parse_bib(content: str) -> list[str]:
    """
    Parse a .bib file and return a list of human-readable citation strings
    like "Smith, J. et al. (2023). Title. Venue."
    """
    refs: list[str] = []
    entries = re.finditer(
        r"@\w+\s*\{[^,]+,([^@]+)\}",
        content,
        re.DOTALL,
    )
    for entry in entries:
        body = entry.group(1)
        fields = dict(
            re.findall(r"(\w+)\s*=\s*[\{\"](.*?)[\}\"](?:\s*,|\s*$)", body, re.DOTALL)
        )
        author = fields.get("author", "").split(" and ")[0].split(",")[0].strip()
        year = fields.get("year", "")
        title = _strip_latex(fields.get("title", ""))[:120]
        venue = fields.get("journal") or fields.get("booktitle") or fields.get("publisher") or ""
        if title:
            refs.append(f"{author} ({year}). {title}. {venue}".strip(". "))
    return refs


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def parse_paper(
    filename: str,
    file_bytes: bytes,
    bib_bytes: bytes | None = None,
) -> ParsedPaper:
    fname = filename.lower()
    if fname.endswith(".pdf"):
        paper = parse_pdf(file_bytes)
    elif fname.endswith((".tex", ".latex")):
        paper = parse_latex(file_bytes.decode("utf-8", errors="replace"))
    else:
        # Treat as plain text
        paper = ParsedPaper(
            full_text=file_bytes.decode("utf-8", errors="replace")[:20_000],
            source_type="text",
        )

    if bib_bytes:
        paper.bib_refs = parse_bib(bib_bytes.decode("utf-8", errors="replace"))

    return paper
