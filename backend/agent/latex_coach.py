"""
LaTeX Coach — analiza un proyecto LaTeX y devuelve sugerencias estructuradas.

Mejoras sobre v1:
  - Sigue \\input / \\include para resolver el documento completo
  - Parsea estructura real: tablas, figuras, \\cite, \\ref, \\label
  - Extrae secciones con número de línea absoluto
  - Manda contenido con líneas numeradas al LLM → sugerencias ancladas
  - Genera review.tex anotado con \\suggestion{} en rojo y lo compila
  - Persiste el zip en disco para generación de annotated on-demand
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Optional

import httpx
import openai

from ..models.latex_schemas import (
    CompilationResult,
    GlobalAssessment,
    LatexCoachSession,
    LatexFigure,
    LatexStructure,
    LatexTable,
    SectionAnalysis,
    SuggestedFigure,
    SuggestedTable,
    TextSuggestion,
)
from ..storage.latex_store import latex_store

logger = logging.getLogger(__name__)

LATEX_SERVICE_URL = os.getenv("LATEX_SERVICE_URL", "http://localhost:8001")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.4-nano")

# Macros LaTeX para anotaciones en rojo
# Use \providecommand so we don't conflict if the document already defines these.
# Avoid todonotes — many documents already load it, causing \todo redefinition errors.
ANNOTATION_PREAMBLE = r"""
% ---- LaTeX Coach annotations ----
\usepackage{xcolor}
\providecommand{\suggestion}[1]{\textcolor{red}{#1}}
\providecommand{\coachissue}[1]{\marginpar{\tiny\textcolor{orange!70!black}{#1}}}
% ---------------------------------
"""


async def _create_llm_completion(
    client: openai.AsyncOpenAI,
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    max_completion_tokens: int = 1400,
) -> str:
    """Llama al modelo via Responses API (gpt-5.x requiere /v1/responses, no Chat Completions).
    Extrae system prompt como 'instructions' y el resto como 'input'.
    Devuelve el texto generado directamente.
    """
    instructions = next((m["content"] for m in messages if m["role"] == "system"), None)
    user_parts = [m for m in messages if m["role"] != "system"]
    user_input: str | list = user_parts[0]["content"] if len(user_parts) == 1 else user_parts

    logger.info("[LaTeXCoach] responses.create model=%s max_output_tokens=%d", LLM_MODEL, max_completion_tokens)
    try:
        resp = await client.responses.create(
            model=LLM_MODEL,
            instructions=instructions,
            input=user_input,
            max_output_tokens=max_completion_tokens,
        )
        logger.info("[LaTeXCoach] OK got %d chars", len(resp.output_text or ""))
        return resp.output_text or ""
    except Exception as exc:
        logger.error("[LaTeXCoach] responses.create failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Entry point principal
# ---------------------------------------------------------------------------

async def run_latex_coach(session_id: str, zip_bytes: bytes, filename: str, main_tex: str = "") -> None:
    """Corre el análisis completo en background."""
    try:
        await _run(session_id, zip_bytes, filename, main_tex)
    except Exception as exc:
        logger.exception("LaTeX coach failed for session %s: %s", session_id, exc)
        await latex_store.mark_error(session_id, str(exc))
        await latex_store.notify_complete(session_id)


async def _run(session_id: str, zip_bytes: bytes, filename: str, main_tex: str = "") -> None:
    session = latex_store.get_session(session_id)
    if session is None:
        return

    # Guardar zip en disco para uso posterior (annotated PDF on-demand)
    latex_store.save_zip(session_id, zip_bytes)

    # ------------------------------------------------------------------
    # 1. Compilar en Docker
    # ------------------------------------------------------------------
    await latex_store.add_log(session_id, "Compilando proyecto LaTeX…")
    compilation = await _compile_zip(zip_bytes, filename)

    # Si falló, intentar modo lenient (tolera imágenes faltantes, etc.)
    if not compilation.success and compilation.errors:
        missing_image = any(
            "File" in e and ("eps" in e or "pdf" in e or "png" in e or "jpg" in e or "imgs" in e.lower())
            for e in compilation.errors
        )
        if missing_image:
            await latex_store.add_log(
                session_id,
                "Imágenes faltantes detectadas. Reintentando compilación en modo tolerante…",
                level="warning",
            )
            lenient_result = await _compile_zip(zip_bytes, filename, lenient=True)
            if lenient_result.success or lenient_result.pdf_url:
                compilation = lenient_result

    session.compilation = compilation
    session.progress.percentage = 20
    await latex_store.update_session(session)

    if compilation.success:
        await latex_store.add_log(session_id, "Compilación exitosa.")
    else:
        await latex_store.add_log(
            session_id,
            f"Compilación con {len(compilation.errors)} errores. Continuando análisis del código fuente…",
            level="warning",
        )

    # ------------------------------------------------------------------
    # 2. Parsear estructura completa del proyecto
    # ------------------------------------------------------------------
    await latex_store.add_log(session_id, "Parseando estructura del proyecto…")
    tex_files = _extract_tex_files(zip_bytes)
    if not tex_files:
        await latex_store.mark_error(session_id, "No se encontraron archivos .tex en el zip.")
        await latex_store.notify_complete(session_id)
        return

    # Resolver \input/\include para tener vista completa
    resolved = _resolve_includes(tex_files)
    paper_title = _extract_title(resolved)
    session.paper_title = paper_title

    # Estructura real: tablas, figuras, citas, labels
    structure = _parse_structure(tex_files)
    session.structure = structure

    # Secciones con líneas absolutas (priorizando main_tex si se especificó)
    sections_raw = _parse_sections_with_lines(tex_files, preferred_main=main_tex)

    session.progress.percentage = 35
    await latex_store.update_session(session)

    # ------------------------------------------------------------------
    # 3. Analizar secciones con LLM (con líneas numeradas)
    # ------------------------------------------------------------------
    await latex_store.add_log(session_id, f"Analizando {len(sections_raw)} secciones con IA…")
    sections_analysis = await _analyze_sections(session_id, sections_raw)
    session.sections = sections_analysis
    session.progress.percentage = 75
    await latex_store.update_session(session)

    # ------------------------------------------------------------------
    # 4. Análisis global
    # ------------------------------------------------------------------
    await latex_store.add_log(session_id, "Generando evaluación global…")
    global_result = await _global_assessment(paper_title, sections_raw, compilation, structure)
    session.global_assessment = global_result["assessment"]
    session.suggested_tables = global_result["tables"]
    session.suggested_figures = global_result["figures"]
    session.weak_claims = global_result["weak_claims"]
    session.progress.percentage = 90
    await latex_store.update_session(session)

    # ------------------------------------------------------------------
    # 5. Generar PDF anotado en rojo
    # ------------------------------------------------------------------
    await latex_store.add_log(session_id, "Generando PDF anotado con sugerencias en rojo…")
    try:
        annotated_zip = _build_annotated_zip(zip_bytes, tex_files, sections_analysis, main_tex)
        annotated_result = await _compile_zip(annotated_zip, "review_annotated.zip")
        if annotated_result.success and annotated_result.pdf_url:
            session.annotated_pdf_url = annotated_result.pdf_url
            await latex_store.add_log(session_id, "PDF anotado generado correctamente.")
        else:
            await latex_store.add_log(
                session_id,
                "PDF anotado falló la compilación (puede haber conflictos de macros).",
                level="warning",
            )
    except Exception as exc:
        logger.warning("Annotated PDF generation failed: %s", exc)
        await latex_store.add_log(session_id, f"PDF anotado no disponible: {exc}", level="warning")

    # ------------------------------------------------------------------
    # 6. Finalizar
    # ------------------------------------------------------------------
    await latex_store.mark_complete(session_id)
    await latex_store.notify_complete(session_id)
    await latex_store.add_log(session_id, "Análisis completado.")


# ---------------------------------------------------------------------------
# Entry point on-demand: (re)generar PDF anotado desde disco
# ---------------------------------------------------------------------------

async def generate_annotated_pdf(session_id: str) -> Optional[str]:
    """
    Genera (o regenera) el PDF anotado para una sesión ya completada.
    Devuelve la URL del PDF anotado, o None si falla.
    """
    session = await latex_store.get_or_load_session(session_id)
    if session is None or session.status != "completed":
        return None

    zip_bytes = latex_store.get_zip_bytes(session_id)
    if zip_bytes is None:
        return None

    tex_files = _extract_tex_files(zip_bytes)
    annotated_zip = _build_annotated_zip(zip_bytes, tex_files, session.sections)
    result = await _compile_zip(annotated_zip, "review_annotated.zip", lenient=True)

    logger.info("[AnnotatedPDF] compile success=%s pdf_url=%s errors=%s",
                result.success, result.pdf_url, result.errors[:3] if result.errors else [])

    # Accept partial PDF even when compilation has errors (lenient mode)
    if result.pdf_url:
        session.annotated_pdf_url = result.pdf_url
        await latex_store.update_session(session)
        return result.pdf_url

    logger.error("[AnnotatedPDF] No PDF produced. errors=%s log_tail=%s",
                 result.errors, result.log[-500:] if result.log else "")
    return None


# ---------------------------------------------------------------------------
# Compilación vía micro-servicio Docker
# ---------------------------------------------------------------------------

async def _compile_zip(zip_bytes: bytes, filename: str, lenient: bool = False) -> CompilationResult:
    """
    lenient=True → intenta compilación sin -halt-on-error para obtener PDF parcial
    aunque haya errores de imágenes faltantes u otros no fatales.
    """
    try:
        params = {"lenient": "1"} if lenient else {}
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{LATEX_SERVICE_URL}/compile",
                files={"file": (filename, io.BytesIO(zip_bytes), "application/zip")},
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            return CompilationResult(
                success=data.get("success", False),
                log=data.get("log", ""),
                pdf_url=_abs_pdf_url(data.get("pdf_url")),
                errors=data.get("errors", []),
                warnings=data.get("warnings", []),
            )
    except httpx.ConnectError:
        return CompilationResult(
            success=False,
            log="No se pudo conectar al servicio de compilación LaTeX. ¿Está corriendo Docker?",
            errors=["Servicio de compilación no disponible"],
        )
    except Exception as exc:
        return CompilationResult(
            success=False,
            log=str(exc),
            errors=[f"Error de compilación: {exc}"],
        )


def _abs_pdf_url(relative_url: Optional[str]) -> Optional[str]:
    if not relative_url:
        return None
    return f"{LATEX_SERVICE_URL}{relative_url}"


# ---------------------------------------------------------------------------
# Extracción y resolución de archivos .tex
# ---------------------------------------------------------------------------

def _extract_tex_files(zip_bytes: bytes) -> dict[str, str]:
    """Devuelve {nombre_archivo: contenido} para todos los .tex del zip."""
    result: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                if name.endswith(".tex"):
                    try:
                        content = z.read(name).decode("utf-8", errors="ignore")
                        result[name] = content
                    except Exception:
                        pass
    except Exception:
        pass
    return result


def _resolve_includes(tex_files: dict[str, str]) -> dict[str, str]:
    """
    Resuelve \\input{} y \\include{} recursivamente.
    Devuelve una copia con cada archivo expandido.
    """
    def _expand(content: str, depth: int = 0) -> str:
        if depth > 5:
            return content  # evitar recursión infinita

        def replace(m: re.Match) -> str:
            fname = m.group(1).strip()
            if not fname.endswith(".tex"):
                fname += ".tex"
            # Buscar en tex_files (puede estar en subdirectorio)
            for key, fcontent in tex_files.items():
                if key == fname or key.endswith("/" + fname) or key.endswith("\\" + fname):
                    return _expand(fcontent, depth + 1)
            return m.group(0)  # no encontrado → dejar como está

        return re.sub(r"\\(?:input|include)\{([^}]+)\}", replace, content)

    return {fname: _expand(content) for fname, content in tex_files.items()}


def _extract_title(tex_files: dict[str, str]) -> str:
    """Extrae el título del paper con soporte para \\title{...\\\\} multilínea."""
    for content in tex_files.values():
        # Intentar con llaves balanceadas (soporta \title{...{\em ...}...})
        m = re.search(r"\\title\{", content)
        if m:
            start = m.end()
            depth = 1
            i = start
            while i < len(content) and depth > 0:
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                i += 1
            raw = content[start : i - 1]
            # Limpiar comandos LaTeX
            clean = re.sub(r"\\[a-zA-Z]+(\{[^}]*\})?", "", raw)
            clean = re.sub(r"[{}\\]", "", clean).strip()
            if clean:
                return clean[:120]
    return "Untitled Paper"


# ---------------------------------------------------------------------------
# Parseo de estructura real
# ---------------------------------------------------------------------------

def _parse_structure(tex_files: dict[str, str]) -> LatexStructure:
    """Extrae tablas, figuras, citas y labels de todos los archivos."""
    tables: list[LatexTable] = []
    figures: list[LatexFigure] = []
    citation_keys: set[str] = set()
    label_keys: set[str] = set()
    ref_keys: set[str] = set()

    for fname, content in tex_files.items():
        # Tablas
        for m in re.finditer(
            r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", content, re.DOTALL
        ):
            body = m.group(1)
            caption = re.search(r"\\caption\{([^}]+)\}", body)
            label = re.search(r"\\label\{([^}]+)\}", body)
            tables.append(LatexTable(
                file=fname,
                caption=caption.group(1) if caption else "",
                label=label.group(1) if label else "",
            ))

        # Figuras
        for m in re.finditer(
            r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", content, re.DOTALL
        ):
            body = m.group(1)
            caption = re.search(r"\\caption\{([^}]+)\}", body)
            label = re.search(r"\\label\{([^}]+)\}", body)
            figures.append(LatexFigure(
                file=fname,
                caption=caption.group(1) if caption else "",
                label=label.group(1) if label else "",
            ))

        # Citas
        for m in re.finditer(r"\\cite[a-z]*\*?\{([^}]+)\}", content):
            for key in m.group(1).split(","):
                citation_keys.add(key.strip())

        # Labels y refs
        for m in re.finditer(r"\\label\{([^}]+)\}", content):
            label_keys.add(m.group(1).strip())
        for m in re.finditer(r"\\ref\{([^}]+)\}", content):
            ref_keys.add(m.group(1).strip())

    # Referencias sin label correspondiente
    undefined_refs = sorted(ref_keys - label_keys)

    return LatexStructure(
        tables=tables,
        figures=figures,
        citations=sorted(citation_keys),
        labels=sorted(label_keys),
        undefined_refs=undefined_refs,
    )


# ---------------------------------------------------------------------------
# Parseo de secciones con líneas absolutas
# ---------------------------------------------------------------------------

def _parse_sections_with_lines(tex_files: dict[str, str], preferred_main: str = "") -> list[dict]:
    """
    Extrae secciones con su posición exacta en el archivo.
    Devuelve lista de:
    {
      "title": str,
      "file": str,
      "start_line": int,     # 1-indexed, absoluto en el archivo
      "end_line": int,
      "content": str,        # texto limpio (sin comentarios)
      "numbered": str,       # contenido con "NNN | línea" para el LLM
    }
    """
    sections: list[dict] = []

    # Priorizar: 1) preferred_main explícito, 2) main.tex, 3) resto alfabético
    def _sort_key(kv: tuple[str, str]) -> tuple[int, str]:
        fname = kv[0]
        if preferred_main and (fname == preferred_main or fname.endswith("/" + preferred_main)):
            return (0, fname)
        if "main" in Path(fname).name.lower():
            return (1, fname)
        return (2, fname)

    ordered = sorted(tex_files.items(), key=_sort_key)

    for fname, content in ordered:
        lines = content.split("\n")

        # Detectar inicio de cada sección/subsección
        section_starts: list[tuple[int, str, str]] = []  # (line_idx, level, title)
        for idx, line in enumerate(lines):
            # Ignorar líneas de comentario
            stripped = line.lstrip()
            if stripped.startswith("%"):
                continue
            m = re.match(r"\\(section|subsection)\*?\{([^}]+)\}", stripped)
            if m:
                section_starts.append((idx, m.group(1), m.group(2).strip()))

        # Extraer cuerpo de cada sección
        for i, (start_idx, level, title) in enumerate(section_starts):
            end_idx = section_starts[i + 1][0] if i + 1 < len(section_starts) else len(lines)
            body_lines = lines[start_idx:end_idx]

            # Limpiar comentarios para el análisis
            clean_lines = [re.sub(r"(?<!\\)%.*", "", ln) for ln in body_lines]
            clean_body = "\n".join(clean_lines).strip()

            if len(clean_body) < 40:
                continue

            # Contenido con números de línea absolutos para el LLM
            max_lines = 120  # límite razonable por sección
            numbered = "\n".join(
                f"{start_idx + j + 1:5d} | {ln}"
                for j, ln in enumerate(body_lines[:max_lines])
            )

            sections.append({
                "title": title,
                "file": fname,
                "start_line": start_idx + 1,
                "end_line": end_idx,
                "content": clean_body[:5000],
                "numbered": numbered,
            })

    # Si no encontramos secciones, usar cada archivo completo
    if not sections:
        for fname, content in ordered[:3]:
            lines = content.split("\n")
            clean = "\n".join(re.sub(r"(?<!\\)%.*", "", ln) for ln in lines).strip()
            if len(clean) < 100:
                continue
            numbered = "\n".join(f"{j+1:5d} | {ln}" for j, ln in enumerate(lines[:100]))
            sections.append({
                "title": Path(fname).stem,
                "file": fname,
                "start_line": 1,
                "end_line": len(lines),
                "content": clean[:5000],
                "numbered": numbered,
            })

    return sections[:18]


# ---------------------------------------------------------------------------
# Análisis LLM por sección (con líneas ancladas)
# ---------------------------------------------------------------------------

SECTION_SYSTEM = """You are a senior academic paper coach reviewing a LaTeX paper.
The section content is shown with ABSOLUTE line numbers from the source file (format: "  LINE | content").
Analyze it and return JSON:
{
  "score_clarity": <0-10>,
  "score_rigor": <0-10>,
  "score_completeness": <0-10>,
  "issues": ["specific issue 1", ...],
  "suggestions": [
    {
      "type": "rewrite|add|remove|expand",
      "start_line": <absolute line number where the change starts>,
      "end_line": <absolute line number where the change ends>,
      "target_text": "exact text from those lines (verbatim, ≤120 chars)",
      "replacement": "full replacement text (LaTeX-valid)",
      "reason": "concise reason"
    }
  ]
}

Rules:
- start_line/end_line MUST be valid line numbers shown in the content.
- target_text must be verbatim from the source (used for matching).
- replacement must be valid LaTeX.
- Limit to 3 suggestions per section. Focus on the highest impact.
Return ONLY valid JSON, no markdown fences."""


async def _analyze_sections(session_id: str, sections_raw: list[dict]) -> list[SectionAnalysis]:
    client = openai.AsyncOpenAI()
    results: list[SectionAnalysis] = []
    llm_errors: list[str] = []

    for i, sec in enumerate(sections_raw):
        pct = 35 + int((i / max(len(sections_raw), 1)) * 38)
        session = latex_store.get_session(session_id)
        if session:
            session.progress.percentage = pct
            await latex_store.update_session(session)

        try:
            # Limitar contenido para no exceder contexto
            numbered_trimmed = "\n".join(sec["numbered"].split("\n")[:100])

            raw = await _create_llm_completion(
                client,
                messages=[
                    {"role": "system", "content": SECTION_SYSTEM},
                    {"role": "user", "content": (
                        f"Section: {sec['title']} "
                        f"(file: {Path(sec['file']).name}, lines {sec['start_line']}–{sec['end_line']})\n\n"
                        f"{numbered_trimmed}"
                    )},
                ],
                temperature=0.0,
                max_completion_tokens=1400,
            )

            raw = raw or "{}"
            data = _safe_json(raw)

            # Si el JSON no se parseó correctamente, tratar como fallo parcial
            if not data:
                llm_errors.append(f"'{sec['title']}': respuesta LLM no parseable")
                results.append(SectionAnalysis(
                    title=sec["title"], file=sec["file"], start_line=sec["start_line"],
                    issues=["LLM response could not be parsed. Check server logs."],
                ))
                continue

            suggestions = []
            for s in data.get("suggestions", []):
                try:
                    suggestions.append(TextSuggestion(
                        type=s.get("type", "rewrite"),
                        file=sec["file"],
                        start_line=int(s.get("start_line", sec["start_line"])),
                        end_line=int(s.get("end_line", sec["start_line"])),
                        target_text=s.get("target_text", ""),
                        replacement=s.get("replacement", ""),
                        reason=s.get("reason", ""),
                    ))
                except Exception:
                    pass

            results.append(SectionAnalysis(
                title=sec["title"],
                file=sec["file"],
                start_line=sec["start_line"],
                score_clarity=_clamp(data.get("score_clarity", 5)),
                score_rigor=_clamp(data.get("score_rigor", 5)),
                score_completeness=_clamp(data.get("score_completeness", 5)),
                issues=data.get("issues", []),
                suggestions=suggestions,
            ))

        except Exception as exc:
            err_msg = str(exc)
            logger.warning("Section analysis failed for '%s': %s", sec["title"], err_msg)
            llm_errors.append(f"'{sec['title']}': {err_msg[:120]}")
            results.append(SectionAnalysis(
                title=sec["title"],
                file=sec["file"],
                start_line=sec["start_line"],
                issues=[f"Analysis failed: {err_msg}"],
            ))

    # Surfacear errores LLM en los logs de sesión para que el usuario los vea
    if llm_errors:
        await latex_store.add_log(
            session_id,
            f"⚠ LLM analysis failed for {len(llm_errors)} section(s): {'; '.join(llm_errors[:3])}",
            level="warning",
        )

    return results


# ---------------------------------------------------------------------------
# Análisis global LLM
# ---------------------------------------------------------------------------

GLOBAL_SYSTEM = """You are a senior academic paper coach.
Given the paper's structure and section summaries, return JSON:
{
  "assessment": {
    "novelty": <0-10>,
    "clarity": <0-10>,
    "experimental_rigor": <0-10>,
    "submission_readiness": <0-10>,
    "overall": <0-10>,
    "top_priorities": ["priority 1", ..., "priority 5"],
    "submission_checklist": ["checklist item 1", ...],
    "verdict": "Not ready | Workshop | Conference | Top venue"
  },
  "suggested_tables": [
    {"title": "...", "rationale": "...", "latex": "\\begin{table}...\\end{table}"}
  ],
  "suggested_figures": [
    {"title": "...", "description": "...", "placement": "section name"}
  ],
  "weak_claims": ["claim quote — section name — why it needs support"]
}
Suggest 1–3 tables and 1–2 figures. Be specific and actionable.
Return ONLY valid JSON, no markdown fences."""


async def _global_assessment(
    title: str,
    sections_raw: list[dict],
    compilation: CompilationResult,
    structure: LatexStructure,
) -> dict:
    client = openai.AsyncOpenAI()

    sections_summary = "\n\n".join(
        f"=== {s['title']} (lines {s['start_line']}–{s['end_line']}) ===\n{s['content'][:600]}"
        for s in sections_raw[:12]
    )

    structure_note = (
        f"\nDocument structure:\n"
        f"  Tables found: {len(structure.tables)} ({', '.join(t.caption[:40] for t in structure.tables[:3])})\n"
        f"  Figures found: {len(structure.figures)} ({', '.join(f.caption[:40] for f in structure.figures[:3])})\n"
        f"  Citation keys: {len(structure.citations)}\n"
        f"  Undefined \\ref: {structure.undefined_refs[:5]}\n"
    )

    compilation_note = ""
    if not compilation.success and compilation.errors:
        compilation_note = f"\nCompilation errors: {'; '.join(compilation.errors[:3])}"

    try:
        raw = await _create_llm_completion(
            client,
            messages=[
                {"role": "system", "content": GLOBAL_SYSTEM},
                {"role": "user", "content": (
                    f"Paper: {title}{compilation_note}{structure_note}\n\n{sections_summary}"
                )},
            ],
            temperature=0.0,
            max_completion_tokens=2000,
        )

        raw = raw or "{}"
        data = _safe_json(raw)
        assess = data.get("assessment", {})

        return {
            "assessment": GlobalAssessment(
                novelty=_clamp(assess.get("novelty", 5)),
                clarity=_clamp(assess.get("clarity", 5)),
                experimental_rigor=_clamp(assess.get("experimental_rigor", 5)),
                submission_readiness=_clamp(assess.get("submission_readiness", 5)),
                overall=_clamp(assess.get("overall", 5)),
                top_priorities=assess.get("top_priorities", []),
                submission_checklist=assess.get("submission_checklist", []),
                verdict=assess.get("verdict", ""),
            ),
            "tables": [
                SuggestedTable(
                    title=t.get("title", ""),
                    rationale=t.get("rationale", ""),
                    latex=t.get("latex", ""),
                )
                for t in data.get("suggested_tables", [])
            ],
            "figures": [
                SuggestedFigure(
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    placement=f.get("placement", ""),
                )
                for f in data.get("suggested_figures", [])
            ],
            "weak_claims": data.get("weak_claims", []),
        }

    except Exception as exc:
        logger.exception("Global assessment failed: %s", exc)
        return {
            "assessment": GlobalAssessment(),
            "tables": [], "figures": [], "weak_claims": [],
        }


# ---------------------------------------------------------------------------
# Generación de zip anotado con sugerencias en rojo
# ---------------------------------------------------------------------------

def _build_annotated_zip(
    original_zip: bytes,
    tex_files: dict[str, str],
    sections: list[SectionAnalysis],
    preferred_main: str = "",
) -> bytes:
    """
    Genera un nuevo zip donde main.tex incluye un apendice "LaTeX Coach Report"
    con todas las sugerencias listadas y escapadas correctamente.
    Evitamos inyectar macros inline porque el texto generado por LLM contiene
    caracteres especiales LaTeX (_^{}$) que rompen la compilacion.
    """
    # Mapa: nombre_archivo → contenido modificado
    modified: dict[str, str] = {k: v for k, v in tex_files.items()}

    # 1. Inyectar macros al preámbulo del main.tex
    main_key = _find_main_key(modified, preferred_main)
    if main_key:
        modified[main_key] = _inject_preamble(modified[main_key])
        # 2. Añadir apendice de sugerencias antes de \end{document}
        modified[main_key] = _append_coach_report(modified[main_key], sections)

    # 3. Reconstruir zip con archivos modificados + todos los demás originales
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_zip)) as z_in:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.infolist():
                if item.filename in modified:
                    z_out.writestr(item, modified[item.filename].encode("utf-8"))
                else:
                    z_out.writestr(item, z_in.read(item.filename))

    return buf.getvalue()


def _latex_escape(text: str) -> str:
    """Escape special LaTeX characters for use in text mode. Always returns a single line."""
    # Collapse newlines/tabs to a space first — LaTeX commands cannot span paragraphs
    text = " ".join(text.replace("\r", "").split("\n")).strip()
    # Order matters: backslash first, then others
    text = text.replace("\\", r"\textbackslash{}")
    text = text.replace("&", r"\&")
    text = text.replace("%", r"\%")
    text = text.replace("$", r"\$")
    text = text.replace("#", r"\#")
    text = text.replace("_", r"\_")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")
    text = text.replace("~", r"\textasciitilde{}")
    text = text.replace("^", r"\textasciicircum{}")
    return text


def _append_coach_report(content: str, sections: list) -> str:
    """
    Append a LaTeX Coach report section before \\end{document}.
    All suggestion text is escaped to a single line — never breaks compilation.
    """
    lines = [
        r"",
        r"\clearpage",
        r"\section*{\textcolor{red}{LaTeX Coach --- Suggested Changes}}",
        r"\small",
    ]
    for sec in sections:
        if not sec.suggestions:
            continue
        lines.append(r"\subsection*{" + _latex_escape(sec.title) + r"}")
        lines.append(r"\begin{itemize}")
        for sug in sec.suggestions:
            reason = _latex_escape(sug.reason or "")
            stype = _latex_escape(sug.type or "")
            lines.append(f"  \\item \\textbf{{[{stype}]}}: {reason}")
            if sug.target_text:
                orig = _latex_escape(sug.target_text[:120])
                lines.append(f"  \\begin{{quote}}\\textit{{Original:}} {orig}\\end{{quote}}")
            if sug.replacement:
                repl = _latex_escape(sug.replacement[:200])
                lines.append(f"  \\begin{{quote}}\\textcolor{{red}}{{\\textit{{Suggestion:}} {repl}}}\\end{{quote}}")
        lines.append(r"\end{itemize}")

    report = "\n".join(lines)
    if r"\end{document}" in content:
        return content.replace(r"\end{document}", report + "\n" + r"\end{document}", 1)
    return content + "\n" + report


def _find_main_key(tex_files: dict[str, str], preferred: str = "") -> Optional[str]:
    """
    Encuentra la clave de main.tex en el dict de archivos.
    Prioridad: preferred > main.tex > primer documentclass.
    """
    if preferred:
        for key in tex_files:
            if key == preferred or key.endswith("/" + preferred) or Path(key).name == preferred:
                return key
    for key in tex_files:
        if Path(key).name.lower() == "main.tex":
            return key
    for key, content in tex_files.items():
        if r"\documentclass" in content:
            return key
    return None


def _inject_preamble(content: str) -> str:
    """Inserta macros de anotación justo después de \\documentclass{...}."""
    # Buscar fin de \documentclass{...}
    m = re.search(r"\\documentclass(\[.*?\])?\{[^}]+\}", content)
    if m:
        insert_at = m.end()
        return content[:insert_at] + "\n" + ANNOTATION_PREAMBLE + content[insert_at:]
    # Fallback: insertar al inicio
    return ANNOTATION_PREAMBLE + "\n" + content


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _safe_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {}


def _clamp(val, lo: float = 0.0, hi: float = 10.0) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return 5.0
