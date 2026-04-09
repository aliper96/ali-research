"""
LaTeX compilation micro-service.

POST /compile   — recibe un .zip con el proyecto LaTeX, devuelve JSON con resultado
GET  /download  — descarga el último PDF compilado
GET  /health    — healthcheck
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse

app = FastAPI(title="latex-compiler", version="1.0.0")

TIMEOUT_SECONDS = 90
MAX_ZIP_MB = 50
OUTPUT_DIR = Path("/home/latexuser/outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/compile")
async def compile_latex(file: UploadFile, lenient: str = "0") -> dict:
    """
    Recibe un .zip con el proyecto LaTeX.
    Devuelve:
      {
        "job_id": "...",
        "success": bool,
        "log": "...",
        "pdf_url": "/download/<job_id>" | null,
        "errors": [...],
        "warnings": [...]
      }
    """
    if not (file.filename or "").endswith(".zip"):
        raise HTTPException(400, "Se requiere un archivo .zip")

    data = await file.read()
    if len(data) > MAX_ZIP_MB * 1024 * 1024:
        raise HTTPException(413, f"El zip supera el límite de {MAX_ZIP_MB} MB")

    job_id = str(uuid.uuid4())

    with tempfile.TemporaryDirectory(prefix="latex_") as tmpdir:
        zip_path = os.path.join(tmpdir, "project.zip")
        with open(zip_path, "wb") as f:
            f.write(data)

        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(tmpdir)
        except zipfile.BadZipFile:
            raise HTTPException(400, "Archivo zip corrupto o inválido")

        main_tex = _find_main_tex(tmpdir)
        if not main_tex:
            raise HTTPException(400, "No se encontró main.tex en el zip")

        work_dir = str(Path(main_tex).parent)
        tex_filename = Path(main_tex).name

        # lenient=1 → sin -halt-on-error para tolerar imágenes faltantes, etc.
        flags = ["latexmk", "-pdf", "-interaction=nonstopmode", "-file-line-error"]
        if lenient != "1":
            flags.append("-halt-on-error")
        flags.append(tex_filename)

        try:
            result = subprocess.run(
                flags,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "job_id": job_id,
                "success": False,
                "log": "Compilación cancelada: superó el timeout de 90 segundos.",
                "pdf_url": None,
                "errors": ["Timeout de compilación"],
                "warnings": [],
            }

        log = result.stdout + "\n" + result.stderr
        errors = _extract_errors(log)
        warnings = _extract_warnings(log)

        pdf_src = Path(main_tex).with_suffix(".pdf")
        if result.returncode == 0 and pdf_src.exists():
            # Guardar PDF fuera del tmpdir (que se borrará al salir del with)
            out_path = OUTPUT_DIR / f"{job_id}.pdf"
            shutil.copy(str(pdf_src), str(out_path))
            return {
                "job_id": job_id,
                "success": True,
                "log": log,
                "pdf_url": f"/download/{job_id}",
                "errors": errors,
                "warnings": warnings,
            }
        else:
            return {
                "job_id": job_id,
                "success": False,
                "log": log,
                "pdf_url": None,
                "errors": errors,
                "warnings": warnings,
            }


@app.get("/download/{job_id}")
def download_pdf(job_id: str) -> FileResponse:
    # Validar que job_id sea un UUID seguro
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "job_id inválido")

    pdf_path = OUTPUT_DIR / f"{job_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF no encontrado. Puede haber expirado.")
    return FileResponse(str(pdf_path), media_type="application/pdf", filename="compiled.pdf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_main_tex(directory: str) -> Optional[str]:
    """Busca main.tex primero; si no existe, usa el primer .tex con \\documentclass."""
    base = Path(directory)

    # 1. Buscar main.tex exacto
    for path in base.rglob("main.tex"):
        return str(path)

    # 2. Buscar cualquier .tex que contenga \documentclass
    for path in sorted(base.rglob("*.tex")):
        try:
            content = path.read_text(errors="ignore")
            if r"\documentclass" in content:
                return str(path)
        except OSError:
            continue

    return None


def _extract_errors(log: str) -> list[str]:
    errors = []
    for line in log.splitlines():
        if re.match(r"^!|.*:\d+: ", line):
            errors.append(line.strip())
    return errors[:20]  # máximo 20


def _extract_warnings(log: str) -> list[str]:
    warnings = []
    for line in log.splitlines():
        low = line.lower()
        if "warning" in low and len(line.strip()) > 5:
            warnings.append(line.strip())
    return warnings[:30]  # máximo 30
