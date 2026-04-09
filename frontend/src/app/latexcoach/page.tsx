'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Upload, FileArchive, ArrowLeft, AlertCircle, Zap, Table2,
  FileCode2, Loader2, Check, ChevronRight,
} from 'lucide-react'
import Link from 'next/link'
import { startLatexCoach, scanLatexZip, type LatexCandidate } from '@/lib/api'
import { cn } from '@/lib/utils'

export default function LatexCoachPage() {
  const router = useRouter()
  const inputRef = useRef<HTMLInputElement>(null)

  const [zipFile, setZipFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [candidates, setCandidates] = useState<LatexCandidate[] | null>(null)
  const [selectedMain, setSelectedMain] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Auto-scan cuando cambia el zip
  useEffect(() => {
    if (!zipFile) { setCandidates(null); setSelectedMain(''); return }

    setScanning(true)
    setCandidates(null)
    setSelectedMain('')

    scanLatexZip(zipFile)
      .then(result => {
        if (result.candidates.length > 1) {
          setCandidates(result.candidates)
          // Pre-seleccionar el que tiene más secciones
          setSelectedMain(result.candidates[0].filename)
        } else if (result.candidates.length === 1) {
          // Solo uno → seleccionar automáticamente sin mostrar picker
          setSelectedMain(result.candidates[0].filename)
          setCandidates(null)
        } else {
          // Ningún \documentclass encontrado → error
          setError('No se encontró ningún archivo .tex con \\documentclass en el zip.')
        }
      })
      .catch(() => {
        // Si el scan falla, continuar sin picker (el backend lo resolverá)
      })
      .finally(() => setScanning(false))
  }, [zipFile])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    setError(null)
    const f = Array.from(e.dataTransfer.files).find(f => f.name.endsWith('.zip'))
    if (f) setZipFile(f)
    else setError('Suelta un archivo .zip con tu proyecto LaTeX.')
  }, [])

  const handleFileChange = (f: File | null) => {
    setError(null)
    setZipFile(f)
  }

  const handleSubmit = async () => {
    if (!zipFile) return
    setLoading(true)
    setError(null)
    try {
      const { session_id } = await startLatexCoach(zipFile, selectedMain || undefined)
      router.push(`/latexcoach/${session_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
      setLoading(false)
    }
  }

  const canSubmit = !!zipFile && !scanning && !loading

  return (
    <div className="flex min-h-screen flex-col bg-[#030712] text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-1/4 -left-32 h-72 w-72 rounded-full bg-emerald-900/10 blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 h-72 w-72 rounded-full bg-teal-900/10 blur-3xl" />
      </div>

      <header className="relative border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-6 py-4">
          <Link href="/" className="flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors text-sm">
            <ArrowLeft className="h-4 w-4" /> Back
          </Link>
          <div className="h-5 w-px bg-slate-800" />
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-900/50 border border-emerald-700/50">
              <FileCode2 className="h-4 w-4 text-emerald-400" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">LaTeX Coach</h1>
              <p className="text-[11px] text-slate-500">AI feedback on your paper — section by section</p>
            </div>
          </div>
        </div>
      </header>

      <main className="relative mx-auto w-full max-w-3xl flex-1 px-6 py-12 space-y-6">

        {/* Hero */}
        <div className="text-center space-y-3">
          <h2 className="text-2xl font-bold text-slate-100">Submit your LaTeX project</h2>
          <p className="text-slate-400 text-sm max-w-lg mx-auto">
            Sube un <span className="text-emerald-400 font-mono">.zip</span> con tu proyecto LaTeX.
            El coach lo compilará, analizará cada sección y te dirá exactamente qué arreglar, añadir o reescribir.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={cn(
            'relative cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center transition-all duration-200',
            dragging
              ? 'border-emerald-500/70 bg-emerald-900/10'
              : zipFile
                ? 'border-emerald-700/50 bg-emerald-900/10'
                : 'border-slate-700 bg-slate-900/40 hover:border-slate-600 hover:bg-slate-900/60',
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={e => handleFileChange(e.target.files?.[0] ?? null)}
          />
          {zipFile ? (
            <div className="flex flex-col items-center gap-3">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-emerald-900/30 border border-emerald-700/40">
                {scanning
                  ? <Loader2 className="h-6 w-6 text-emerald-400 animate-spin" />
                  : <FileArchive className="h-7 w-7 text-emerald-400" />}
              </div>
              <p className="text-sm font-medium text-emerald-300">{zipFile.name}</p>
              <p className="text-xs text-slate-500">
                {scanning ? 'Detectando archivos .tex…' : `${(zipFile.size / 1024).toFixed(0)} KB — click para cambiar`}
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-slate-800 border border-slate-700">
                <Upload className="h-7 w-7 text-slate-400" />
              </div>
              <p className="text-sm text-slate-300">
                Suelta tu <span className="font-mono text-emerald-400">.zip</span> aquí, o haz click para seleccionar
              </p>
              <p className="text-xs text-slate-600">Proyecto LaTeX completo — máx 50 MB</p>
            </div>
          )}
        </div>

        {/* Picker de main.tex — solo si hay múltiples candidatos */}
        {candidates && candidates.length > 1 && (
          <div className="rounded-xl border border-amber-900/40 bg-amber-950/15 p-5 space-y-4">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-amber-400 flex-shrink-0" />
              <p className="text-sm font-semibold text-amber-300">
                Se encontraron {candidates.length} archivos con <span className="font-mono">\\documentclass</span>. ¿Cuál es el principal?
              </p>
            </div>
            <div className="space-y-2">
              {candidates.map(c => (
                <label
                  key={c.filename}
                  className={cn(
                    'flex items-center gap-3 rounded-lg border px-4 py-3 cursor-pointer transition-all',
                    selectedMain === c.filename
                      ? 'border-emerald-700/60 bg-emerald-900/20'
                      : 'border-slate-800 hover:border-slate-700 hover:bg-slate-900/40',
                  )}
                >
                  <input
                    type="radio"
                    name="main_tex"
                    value={c.filename}
                    checked={selectedMain === c.filename}
                    onChange={() => setSelectedMain(c.filename)}
                    className="accent-emerald-500"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-mono text-slate-200 truncate">{c.filename}</p>
                    <p className="text-xs text-slate-600 mt-0.5">
                      {c.section_count} sección{c.section_count !== 1 ? 'es' : ''} · {c.size_kb} KB
                    </p>
                  </div>
                  {selectedMain === c.filename && (
                    <Check className="h-4 w-4 text-emerald-400 flex-shrink-0" />
                  )}
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Confirmación si solo hay uno detectado */}
        {zipFile && !scanning && !candidates && selectedMain && (
          <div className="flex items-center gap-2 text-xs text-slate-500 px-1">
            <Check className="h-3.5 w-3.5 text-emerald-500" />
            Archivo principal detectado: <span className="font-mono text-emerald-400">{selectedMain}</span>
          </div>
        )}

        {/* How to zip */}
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/30 px-5 py-4 space-y-2">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cómo crear el zip</p>
          <code className="block text-xs text-emerald-400 font-mono bg-slate-950/60 rounded px-3 py-2">
            zip -r my_paper.zip . -x &quot;*.pdf&quot; -x &quot;.git/*&quot;
          </code>
          <p className="text-xs text-slate-600">
            Ejecuta esto dentro de la carpeta de tu proyecto LaTeX. Las imágenes pueden estar o no —
            si faltan, el análisis del código fuente continuará igualmente.
          </p>
        </div>

        {/* What it does */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            { icon: Zap, label: 'Compilar y verificar', desc: 'Ejecuta latexmk en Docker, muestra errores y warnings', color: 'text-yellow-400' },
            { icon: FileCode2, label: 'Análisis por sección', desc: 'Puntúa claridad, rigor y completitud — por sección', color: 'text-emerald-400' },
            { icon: Table2, label: 'Tablas y figuras', desc: 'Identifica qué experimentos y visualizaciones faltan', color: 'text-teal-400' },
          ].map(f => (
            <div key={f.label} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
              <f.icon className={`h-4 w-4 mb-2 ${f.color}`} />
              <p className="text-xs font-semibold text-slate-200 mb-1">{f.label}</p>
              <p className="text-xs text-slate-500">{f.desc}</p>
            </div>
          ))}
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        )}

        <button
          disabled={!canSubmit}
          onClick={handleSubmit}
          className="w-full rounded-xl bg-emerald-700 py-3.5 text-sm font-semibold text-white transition-all hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Subiendo…</>
          ) : scanning ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Detectando archivos…</>
          ) : (
            <>Analizar paper <ChevronRight className="h-4 w-4" /></>
          )}
        </button>
      </main>
    </div>
  )
}
