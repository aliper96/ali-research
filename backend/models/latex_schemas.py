from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

from .schemas import LogEntry, Progress


# ---------------------------------------------------------------------------
# Compilation result (del micro-servicio Docker)
# ---------------------------------------------------------------------------

class CompilationResult(BaseModel):
    success: bool = False
    log: str = ""
    pdf_url: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sugerencias por sección — con anclaje real al source
# ---------------------------------------------------------------------------

class TextSuggestion(BaseModel):
    type: Literal["rewrite", "add", "remove", "expand"] = "rewrite"
    # Anclaje al source
    file: str = ""          # archivo .tex donde aplica
    start_line: int = 0     # línea absoluta en ese archivo (1-indexed)
    end_line: int = 0       # línea final inclusive
    # Contenido
    target_text: str = ""   # fragmento original exacto (para matching)
    replacement: str = ""   # texto sugerido
    reason: str = ""


class SectionAnalysis(BaseModel):
    title: str = ""
    file: str = ""
    start_line: int = 0     # dónde empieza la sección en su archivo
    score_clarity: float = Field(default=0.0, ge=0.0, le=10.0)
    score_rigor: float = Field(default=0.0, ge=0.0, le=10.0)
    score_completeness: float = Field(default=0.0, ge=0.0, le=10.0)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[TextSuggestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Estructura LaTeX real (tablas, figuras, citas, labels)
# ---------------------------------------------------------------------------

class LatexTable(BaseModel):
    file: str = ""
    caption: str = ""
    label: str = ""

class LatexFigure(BaseModel):
    file: str = ""
    caption: str = ""
    label: str = ""

class LatexStructure(BaseModel):
    tables: list[LatexTable] = Field(default_factory=list)
    figures: list[LatexFigure] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)    # cite keys encontradas
    labels: list[str] = Field(default_factory=list)       # label keys
    undefined_refs: list[str] = Field(default_factory=list)  # \ref sin \label correspondiente


# ---------------------------------------------------------------------------
# Tablas y figuras sugeridas (salida del LLM)
# ---------------------------------------------------------------------------

class SuggestedTable(BaseModel):
    title: str = ""
    rationale: str = ""
    latex: str = ""

class SuggestedFigure(BaseModel):
    title: str = ""
    description: str = ""
    placement: str = ""


# ---------------------------------------------------------------------------
# Puntuación global
# ---------------------------------------------------------------------------

class GlobalAssessment(BaseModel):
    novelty: float = Field(default=0.0, ge=0.0, le=10.0)
    clarity: float = Field(default=0.0, ge=0.0, le=10.0)
    experimental_rigor: float = Field(default=0.0, ge=0.0, le=10.0)
    submission_readiness: float = Field(default=0.0, ge=0.0, le=10.0)
    overall: float = Field(default=0.0, ge=0.0, le=10.0)
    top_priorities: list[str] = Field(default_factory=list)
    submission_checklist: list[str] = Field(default_factory=list)
    verdict: str = ""


# ---------------------------------------------------------------------------
# Sesión principal
# ---------------------------------------------------------------------------

class LatexCoachSession(BaseModel):
    session_id: str
    status: Literal["running", "completed", "error"] = "running"
    filename: str = ""
    paper_title: str = ""

    # Compilación original
    compilation: Optional[CompilationResult] = None

    # Estructura real del documento
    structure: Optional[LatexStructure] = None

    # Análisis por secciones
    sections: list[SectionAnalysis] = Field(default_factory=list)

    # Sugerencias globales del LLM
    suggested_tables: list[SuggestedTable] = Field(default_factory=list)
    suggested_figures: list[SuggestedFigure] = Field(default_factory=list)
    weak_claims: list[str] = Field(default_factory=list)

    # Puntuación global
    global_assessment: Optional[GlobalAssessment] = None

    # PDF anotado (versión en rojo generada por el coach)
    annotated_pdf_url: Optional[str] = None

    # PDF compilado después de aplicar parches seleccionados
    patched_pdf_url: Optional[str] = None

    # Progreso y logs
    created_at: str = ""
    progress: Progress = Field(default_factory=Progress)
    error: Optional[str] = None
