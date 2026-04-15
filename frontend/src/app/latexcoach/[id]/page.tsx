'use client'

import React, { useEffect, useState, lazy, Suspense } from 'react'
const LaTeXEditor = lazy(() => import('./LaTeXEditor'))
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft, CheckCircle2, XCircle, AlertTriangle, Loader2,
  ChevronDown, ChevronUp, Copy, Check, FileCode2, Table2,
  BarChart3, Lightbulb, ClipboardList, Terminal, ImageIcon,
  Zap, ShieldAlert, BookOpen, Hash, RefreshCw, Columns2, X,
} from 'lucide-react'
import {
  getLatexCoachSession, streamLatexCoach, requestAnnotatedPdf, reanalyzeLatexCoach, patchLatexCoach,
  type LatexCoachSession, type SectionAnalysis, type LatexStructure,
} from '@/lib/api'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Score ring
// ---------------------------------------------------------------------------
function ScoreRing({ value, label, color }: { value: number; label: string; color: string }) {
  const r = 28
  const circ = 2 * Math.PI * r
  const dash = (Math.min(value, 10) / 10) * circ
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-[72px] h-[72px]">
        <svg width="72" height="72" className="-rotate-90 absolute inset-0">
          <circle cx="36" cy="36" r={r} fill="none" stroke="#1e293b" strokeWidth="6" />
          <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.6s ease' }} />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-slate-200">
          {value.toFixed(1)}
        </span>
      </div>
      <span className="text-[10px] text-slate-500 text-center leading-tight">{label}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Copy button
// ---------------------------------------------------------------------------
function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }}
      className={cn('text-slate-600 hover:text-slate-300 transition-colors', className)}
      title="Copy"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Line badge
// ---------------------------------------------------------------------------
function LineBadge({ file, startLine, endLine }: { file: string; startLine: number; endLine: number }) {
  if (!startLine) return null
  const fname = file.split('/').pop() ?? file
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-mono bg-slate-900 border border-slate-700/60 text-slate-500 rounded px-1.5 py-0.5">
      <Hash className="h-2.5 w-2.5" />
      {fname}:{startLine}{endLine > startLine ? `–${endLine}` : ''}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Section card
// ---------------------------------------------------------------------------
function SectionCard({ sec, secIdx, applied, onToggle }: {
  sec: SectionAnalysis
  secIdx: number
  applied: Set<string>
  onToggle: (key: string) => void
}) {
  const [open, setOpen] = useState(false)
  const avg = (sec.score_clarity + sec.score_rigor + sec.score_completeness) / 3
  const scoreColor = avg >= 7 ? 'text-emerald-400' : avg >= 5 ? 'text-yellow-400' : 'text-red-400'
  const borderColor = avg >= 7 ? 'border-emerald-900/40' : avg >= 5 ? 'border-yellow-900/40' : 'border-red-900/40'

  return (
    <div className={cn('rounded-xl border bg-slate-900/40', borderColor)}>
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center gap-3 px-5 py-4 text-left">
        <span className={cn('text-sm font-bold w-10 flex-shrink-0 tabular-nums', scoreColor)}>
          {avg.toFixed(1)}
        </span>
        <span className="flex-1 text-sm font-medium text-slate-200 truncate">{sec.title}</span>
        {sec.start_line > 0 && (
          <span className="text-[10px] font-mono text-slate-700 mr-1">:{sec.start_line}</span>
        )}
        <span className="text-[10px] font-mono text-slate-600 mr-2 truncate max-w-[120px] hidden sm:block">
          {sec.file.split('/').pop()}
        </span>
        {sec.suggestions.length > 0 && (
          <span className="text-[10px] bg-orange-900/40 text-orange-400 border border-orange-800/40 rounded px-1.5 py-0.5 flex-shrink-0">
            {sec.suggestions.length} fix{sec.suggestions.length > 1 ? 'es' : ''}
          </span>
        )}
        {open ? <ChevronUp className="h-4 w-4 text-slate-600 flex-shrink-0" /> : <ChevronDown className="h-4 w-4 text-slate-600 flex-shrink-0" />}
      </button>

      {open && (
        <div className="border-t border-slate-800/60 px-5 pb-5 pt-4 space-y-5">
          {/* Mini scores */}
          <div className="flex gap-3">
            {[
              { label: 'Clarity', val: sec.score_clarity },
              { label: 'Rigor', val: sec.score_rigor },
              { label: 'Completeness', val: sec.score_completeness },
            ].map(s => (
              <div key={s.label} className="flex-1 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-center">
                <div className={cn('font-bold text-base tabular-nums',
                  s.val >= 7 ? 'text-emerald-400' : s.val >= 5 ? 'text-yellow-400' : 'text-red-400')}>
                  {s.val.toFixed(1)}
                </div>
                <div className="text-[11px] text-slate-600 mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Issues */}
          {sec.issues.length > 0 && (
            <div className="space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Issues</p>
              {sec.issues.map((issue, i) => (
                <div key={i} className="flex gap-2 text-xs text-slate-400">
                  <AlertTriangle className="h-3.5 w-3.5 text-yellow-500/70 flex-shrink-0 mt-0.5" />
                  {issue}
                </div>
              ))}
            </div>
          )}

          {/* Suggestions */}
          {sec.suggestions.length > 0 && (
            <div className="space-y-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Suggested changes</p>
              {sec.suggestions.map((s, i) => {
                const key = `${secIdx}_${i}`
                const isApplied = applied.has(key)
                return (
                  <div key={i} className={cn(
                    'rounded-lg border p-3 space-y-2.5 transition-colors',
                    isApplied ? 'border-emerald-700/40 bg-emerald-950/10' : 'border-slate-800 bg-slate-950/50'
                  )}>
                    {/* Header */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <input
                        type="checkbox"
                        checked={isApplied}
                        onChange={() => onToggle(key)}
                        className="accent-emerald-500 flex-shrink-0 w-4 h-4 cursor-pointer"
                        title={isApplied ? 'Quitar sugerencia' : 'Marcar como aplicada'}
                      />
                      {isApplied && (
                        <span className="text-[10px] bg-emerald-900/40 text-emerald-400 border border-emerald-800/40 rounded px-1.5 py-0.5 flex-shrink-0">
                          aplicada
                        </span>
                      )}
                      <span className={cn(
                        'text-[10px] font-mono px-1.5 py-0.5 rounded border flex-shrink-0',
                        s.type === 'rewrite' ? 'border-orange-800/50 text-orange-400 bg-orange-950/30' :
                        s.type === 'add'     ? 'border-emerald-800/50 text-emerald-400 bg-emerald-950/30' :
                        s.type === 'expand'  ? 'border-blue-800/50 text-blue-400 bg-blue-950/30' :
                                               'border-red-800/50 text-red-400 bg-red-950/30',
                      )}>{s.type}</span>
                      <LineBadge file={s.file || sec.file} startLine={s.start_line} endLine={s.end_line} />
                      {s.reason && <span className="text-xs text-slate-500 flex-1 min-w-0">{s.reason}</span>}
                    </div>
                    {/* Original → Red */}
                    {s.target_text && (
                      <div className="flex items-start gap-2">
                        <div className="flex-1 text-xs rounded bg-red-950/20 border border-red-900/30 px-2.5 py-1.5 text-red-300/80 line-through opacity-70 font-mono break-all">
                          {s.target_text.slice(0, 240)}
                        </div>
                      </div>
                    )}
                    {/* Replacement → Green */}
                    {s.replacement && (
                      <div className="flex items-start gap-2">
                        <div className="flex-1 text-xs rounded bg-emerald-950/20 border border-emerald-900/30 px-2.5 py-1.5 text-emerald-300 font-mono break-all">
                          {s.replacement}
                        </div>
                        <CopyButton text={s.replacement} className="mt-1 flex-shrink-0" />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Structure panel
// ---------------------------------------------------------------------------
function StructurePanel({ s }: { s: LatexStructure }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center gap-3 px-5 py-4 text-left">
        <BookOpen className="h-4 w-4 text-teal-400" />
        <span className="text-sm font-semibold text-slate-200 flex-1">Document Structure</span>
        <div className="flex gap-3 text-xs text-slate-600 mr-2">
          <span>{s.tables.length} tables</span>
          <span>{s.figures.length} figs</span>
          <span>{s.citations.length} cites</span>
          {s.undefined_refs.length > 0 && (
            <span className="text-red-500">{s.undefined_refs.length} broken refs</span>
          )}
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-slate-600" /> : <ChevronDown className="h-4 w-4 text-slate-600" />}
      </button>

      {open && (
        <div className="border-t border-slate-800/60 px-5 pb-5 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">Tables ({s.tables.length})</p>
            {s.tables.length === 0
              ? <p className="text-xs text-slate-700">None found</p>
              : s.tables.map((t, i) => (
                  <div key={i} className="text-xs text-slate-400 py-1 border-b border-slate-800/40 last:border-0">
                    {t.caption || '(no caption)'}{t.label && <span className="ml-2 font-mono text-slate-600">{t.label}</span>}
                  </div>
                ))
            }
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">Figures ({s.figures.length})</p>
            {s.figures.length === 0
              ? <p className="text-xs text-slate-700">None found</p>
              : s.figures.map((f, i) => (
                  <div key={i} className="text-xs text-slate-400 py-1 border-b border-slate-800/40 last:border-0">
                    {f.caption || '(no caption)'}{f.label && <span className="ml-2 font-mono text-slate-600">{f.label}</span>}
                  </div>
                ))
            }
          </div>
          {s.undefined_refs.length > 0 && (
            <div className="sm:col-span-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-red-500 mb-2">
                Broken \ref without matching \label ({s.undefined_refs.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {s.undefined_refs.map((r, i) => (
                  <span key={i} className="text-[10px] font-mono bg-red-950/30 border border-red-900/30 text-red-400 rounded px-1.5 py-0.5">{r}</span>
                ))}
              </div>
            </div>
          )}
          <div className="sm:col-span-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Citation keys ({s.citations.length})
            </p>
            <p className="text-xs text-slate-600 font-mono truncate">{s.citations.slice(0, 12).join(', ')}{s.citations.length > 12 ? ` +${s.citations.length - 12} more` : ''}</p>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PDF preview panel
// ---------------------------------------------------------------------------
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function proxyPdf(url: string | null | undefined): string | null {
  if (!url) return null
  return `${API_BASE}/api/pdf-proxy?src=${encodeURIComponent(url)}`
}

type PdfTab = 'original' | 'annotated' | 'patched' | 'raw'

function PdfPanel({
  pdfUrl,
  annotatedUrl,
  patchedUrl,
  patchErrors,
  compiling,
  rawFiles,
  rawFileList,
  rawMain,
  onClose,
  onFetchRaw,
  onCompileEdit,
}: {
  pdfUrl: string | null | undefined
  annotatedUrl: string | null | undefined
  patchedUrl: string | null | undefined
  patchErrors: string[]
  compiling: boolean
  rawFiles: Record<string, string>
  rawFileList: string[]
  rawMain: string
  onClose: () => void
  onFetchRaw: (file?: string) => void
  onCompileEdit: (file: string, content: string) => Promise<void>
}) {
  const [active, setActive] = useState<PdfTab>('original')
  const [rawFile, setRawFile] = useState<string>('')

  // Auto-switch to patched tab when it becomes available
  useEffect(() => { if (patchedUrl) setActive('patched') }, [patchedUrl])

  // Load raw on tab switch
  useEffect(() => {
    if (active !== 'raw') return
    const target = rawFile || rawMain
    if (!target) {
      // rawMain not yet populated — fetch default (no file arg → backend picks main)
      onFetchRaw()
    } else if (!rawFiles[target]) {
      onFetchRaw(target)
    }
  }, [active, rawFile, rawMain])

  const rawKey = rawFile || rawMain
  const rawContent = rawFiles[rawKey] ?? ''

  // Local edit state — initialise from fetched content
  const [editContent, setEditContent] = useState('')
  const [editingFile, setEditingFile] = useState('')
  const [editCompiling, setEditCompiling] = useState(false)
  const [editErrors, setEditErrors] = useState<string[]>([])

  useEffect(() => {
    if (rawContent && rawKey !== editingFile) {
      setEditContent(rawContent)
      setEditingFile(rawKey)
      setEditErrors([])
    }
  }, [rawContent, rawKey])

  const handleCompileEdit = async () => {
    if (!editingFile) return
    setEditCompiling(true)
    setEditErrors([])
    try {
      await onCompileEdit(editingFile, editContent)
    } catch (e: any) {
      setEditErrors([String(e)])
    } finally {
      setEditCompiling(false)
    }
  }

  const tabs: { id: PdfTab; label: string; available: boolean; color?: string }[] = [
    { id: 'original',  label: 'Original',  available: !!pdfUrl },
    { id: 'annotated', label: 'Anotado',   available: !!annotatedUrl, color: 'red' },
    { id: 'patched',   label: 'Parcheado', available: !!patchedUrl || compiling, color: 'emerald' },
    { id: 'raw',       label: 'Raw .tex',  available: true },
  ]

  const pdfSrc: Record<PdfTab, string | null> = {
    original:  proxyPdf(pdfUrl),
    annotated: proxyPdf(annotatedUrl),
    patched:   proxyPdf(patchedUrl),
    raw:       null,
  }

  return (
    <div className="flex flex-col h-full bg-slate-950 border-l border-slate-800/60">
      {/* Panel header */}
      <div className="flex items-center gap-1 px-2 py-2 border-b border-slate-800/60 bg-slate-950/90 flex-shrink-0 flex-wrap">
        <div className="flex rounded-lg border border-slate-700/60 overflow-hidden text-[11px] flex-shrink-0">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => tab.available && setActive(tab.id)}
              disabled={!tab.available && tab.id !== 'raw'}
              className={cn(
                'px-2.5 py-1 transition-colors border-r border-slate-700/60 last:border-0',
                active === tab.id
                  ? tab.color === 'red' ? 'bg-red-900/60 text-red-200'
                    : tab.color === 'emerald' ? 'bg-emerald-900/50 text-emerald-200'
                    : 'bg-slate-700 text-slate-100'
                  : tab.available
                    ? 'text-slate-400 hover:text-slate-200'
                    : 'text-slate-700 cursor-not-allowed',
              )}
            >
              {tab.id === 'patched' && compiling && active !== 'patched'
                ? <span className="flex items-center gap-1"><Loader2 className="h-2.5 w-2.5 animate-spin" /> compilando…</span>
                : tab.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-1 flex-shrink-0">
          {active !== 'raw' && pdfSrc[active] && (
            <a href={pdfSrc[active]!} target="_blank" rel="noopener noreferrer"
              className="text-[11px] text-slate-500 hover:text-slate-300 transition-colors px-1.5" title="Abrir en nueva pestaña">
              ↗
            </a>
          )}
          <button onClick={onClose} className="text-slate-600 hover:text-slate-300 transition-colors p-0.5" title="Cerrar">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 flex flex-col">
        {active === 'raw' ? (
          <div className="flex flex-col h-full">
            {/* Toolbar: file selector + compile button */}
            <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-800/60 bg-slate-900/80 flex-shrink-0">
              {rawFileList.length > 1 ? (
                <select
                  value={rawKey}
                  onChange={e => {
                    setRawFile(e.target.value)
                    if (!rawFiles[e.target.value]) onFetchRaw(e.target.value)
                  }}
                  className="text-[11px] bg-slate-800 border border-slate-700/60 text-slate-300 rounded px-2 py-0.5 flex-1 min-w-0"
                >
                  {rawFileList.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              ) : (
                <span className="text-[11px] text-slate-500 font-mono flex-1 truncate">{rawKey}</span>
              )}
              <CopyButton text={editContent} />
              <button
                onClick={handleCompileEdit}
                disabled={editCompiling || !editContent}
                className="flex items-center gap-1 text-[11px] bg-emerald-900/50 hover:bg-emerald-900/70 border border-emerald-700/50 text-emerald-300 rounded px-2.5 py-1 transition-colors disabled:opacity-50 flex-shrink-0"
              >
                {editCompiling ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                {editCompiling ? 'Compilando…' : '▶ Compilar'}
              </button>
            </div>

            {/* Error bar */}
            {editErrors.length > 0 && (
              <div className="bg-red-950/40 border-b border-red-900/40 px-3 py-1.5 flex-shrink-0">
                {editErrors.slice(0, 2).map((e, i) => (
                  <p key={i} className="text-[11px] text-red-400 font-mono truncate">{e}</p>
                ))}
              </div>
            )}

            {/* Editor */}
            <div className="flex-1 min-h-0 relative">
              {editContent || rawContent ? (
                <Suspense fallback={
                  <div className="flex items-center justify-center h-full text-slate-400 text-xs gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" /> Cargando editor…
                  </div>
                }>
                  <LaTeXEditor
                    value={editContent || rawContent}
                    onChange={setEditContent}
                  />
                </Suspense>
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-600">
                  <Loader2 className="h-6 w-6 animate-spin" />
                  <p className="text-xs">Cargando…</p>
                </div>
              )}
            </div>
          </div>
        ) : active === 'patched' && compiling ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
            <p className="text-xs text-slate-500">Compilando versión parcheada…</p>
          </div>
        ) : active === 'patched' && patchErrors.length > 0 && !patchedUrl ? (
          <div className="flex flex-col gap-3 p-5 overflow-y-auto h-full">
            <div className="flex items-center gap-2 text-red-400 font-semibold text-sm">
              <XCircle className="h-4 w-4" /> Compilación fallida
            </div>
            <p className="text-xs text-slate-500">Los cambios aplicados introducen errores LaTeX. Revisa los parches o edita el Raw .tex.</p>
            <div className="space-y-1 mt-2">
              {patchErrors.map((e, i) => (
                <div key={i} className="text-[11px] font-mono text-red-300 bg-red-950/30 rounded px-2.5 py-1.5 break-all">
                  {e}
                </div>
              ))}
            </div>
          </div>
        ) : pdfSrc[active] ? (
          <iframe key={pdfSrc[active]!} src={pdfSrc[active]!} className="w-full h-full" title="PDF preview" />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-600">
            <FileCode2 className="h-10 w-10 opacity-30" />
            <p className="text-xs text-center px-4">No disponible</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function LatexCoachResultPage() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<LatexCoachSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [annotating, setAnnotating] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)
  const [applied, setApplied] = useState<Set<string>>(new Set())
  const [showPdf, setShowPdf] = useState(false)
  const [patchedPdfUrl, setPatchedPdfUrl] = useState<string | null>(null)
  const [patchErrors, setPatchErrors] = useState<string[]>([])
  const [compiling, setCompiling] = useState(false)
  const [rawFiles, setRawFiles] = useState<Record<string, string>>({})
  const [rawFileList, setRawFileList] = useState<string[]>([])
  const [rawMain, setRawMain] = useState<string>('')

  useEffect(() => {
    if (!id) return
    getLatexCoachSession(id).then(s => { setSession(s); setLoading(false) }).catch(() => setLoading(false))

    const cleanup = streamLatexCoach(id, (event) => {
      if (event.type === 'complete' || event.type === 'progress') {
        getLatexCoachSession(id).then(s => setSession(s))
      }
    })
    return cleanup
  }, [id])

  const handleReanalyze = async () => {
    if (!id) return
    setReanalyzing(true)
    try {
      await reanalyzeLatexCoach(id)
      getLatexCoachSession(id).then(s => setSession(s))
    } catch (e) {
      console.error(e)
    } finally {
      setReanalyzing(false)
    }
  }

  const handleRequestAnnotated = async () => {
    if (!id) return
    setAnnotating(true)
    try {
      const { annotated_pdf_url } = await requestAnnotatedPdf(id)
      setSession(s => s ? { ...s, annotated_pdf_url } : s)
    } catch (e) {
      console.error(e)
    } finally {
      setAnnotating(false)
    }
  }

  const toggleSuggestion = (key: string) => {
    setApplied(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const applyAll = () => {
    if (!session) return
    const keys = new Set<string>()
    session.sections.forEach((sec, si) => {
      sec.suggestions.forEach((_, gi) => keys.add(`${si}_${gi}`))
    })
    setApplied(keys)
  }

  const clearAll = () => setApplied(new Set())

  const getSuggestionList = () =>
    Array.from(applied).map(key => {
      const [si, gi] = key.split('_').map(Number)
      return { section_idx: si, suggestion_idx: gi }
    })

  const handleDownloadPatched = async () => {
    if (!id || applied.size === 0) return
    try { await patchLatexCoach(id, getSuggestionList()) } catch (e) { console.error(e) }
  }

  const handleCompilePatched = async () => {
    if (!id || applied.size === 0) return
    setCompiling(true)
    setShowPdf(true)
    setPatchErrors([])
    try {
      const res = await fetch(`${API_BASE}/api/latexcoach/${id}/patch-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suggestions: getSuggestionList() }),
      })
      const data = await res.json()
      if (data.patched_pdf_url) {
        setPatchedPdfUrl(data.patched_pdf_url)
      } else {
        setPatchErrors(data.errors ?? ['Compilation produced no PDF'])
      }
    } catch (e) { console.error(e) } finally { setCompiling(false) }
  }

  const handleCompileEdit = async (file: string, content: string) => {
    setCompiling(true)
    setShowPdf(true)
    try {
      const res = await fetch(`${API_BASE}/api/latexcoach/${id}/compile-edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file, content }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setPatchedPdfUrl(data.pdf_url)
    } finally {
      setCompiling(false)
    }
  }

  const fetchRaw = async (file?: string) => {
    if (!id) return
    const url = `${API_BASE}/api/latexcoach/${id}/raw${file ? `?file=${encodeURIComponent(file)}` : ''}`
    try {
      const res = await fetch(url)
      if (!res.ok) return
      const data = await res.json()
      setRawFiles(prev => ({ ...prev, [data.file]: data.content }))
      setRawFileList(data.files ?? [])
      setRawMain(data.main ?? data.file)
    } catch (e) { console.error(e) }
  }

  const ga = session?.global_assessment
  const hasPdf = !!(session?.compilation?.pdf_url)

  return (
    <div className="flex flex-col min-h-screen bg-[#030712] text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-1/4 -left-32 h-72 w-72 rounded-full bg-emerald-900/8 blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 h-72 w-72 rounded-full bg-teal-900/8 blur-3xl" />
      </div>

      {/* Header */}
      <header className="relative border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10 flex-shrink-0">
        <div className="flex items-center gap-3 px-4 py-3">
          <Link href="/latexcoach" className="flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors text-sm flex-shrink-0">
            <ArrowLeft className="h-4 w-4" /> New
          </Link>
          <div className="h-5 w-px bg-slate-800" />
          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-900/50 border border-emerald-700/50 flex-shrink-0">
              <FileCode2 className="h-4 w-4 text-emerald-400" />
            </div>
            <div className="min-w-0">
              <h1 className="text-sm font-semibold text-slate-100 truncate">
                {session?.paper_title || session?.filename || 'LaTeX Coach'}
              </h1>
              <p className="text-[11px] text-slate-500">
                {session?.status === 'running'
                  ? `${session.progress.logs.at(-1)?.message ?? 'Analysing…'}`
                  : session?.status === 'completed' ? 'Analysis complete' : 'Error'}
              </p>
            </div>
          </div>

          {/* Split-view toggle */}
          {hasPdf && (
            <button
              onClick={() => setShowPdf(v => !v)}
              className={cn(
                'flex-shrink-0 flex items-center gap-1.5 text-xs rounded-lg px-3 py-1.5 border transition-colors',
                showPdf
                  ? 'bg-emerald-900/40 border-emerald-700/50 text-emerald-300'
                  : 'bg-slate-800 border-slate-700/50 text-slate-400 hover:bg-slate-700'
              )}
              title="Dividir pantalla con PDF"
            >
              <Columns2 className="h-3.5 w-3.5" />
              {showPdf ? 'Ocultar PDF' : 'Ver PDF'}
            </button>
          )}

          {/* Re-analyze */}
          {session && session.status !== 'running' && (
            <button
              onClick={handleReanalyze}
              disabled={reanalyzing}
              className="flex-shrink-0 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700/50 text-slate-400 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {reanalyzing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              Re-analizar
            </button>
          )}

          {/* Annotated PDF */}
          {session?.status === 'completed' && (
            session.annotated_pdf_url ? (
              <a
                href={session.annotated_pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-shrink-0 text-xs bg-red-900/40 hover:bg-red-900/60 border border-red-800/50 text-red-300 rounded-lg px-3 py-1.5 transition-colors"
              >
                ↓ PDF anotado
              </a>
            ) : (
              <button
                onClick={handleRequestAnnotated}
                disabled={annotating}
                className="flex-shrink-0 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700/50 text-slate-400 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {annotating ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                Generar PDF anotado
              </button>
            )
          )}

          {session?.status === 'running' && (
            <div className="flex items-center gap-2 text-xs text-emerald-400 flex-shrink-0">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {session.progress.percentage}%
            </div>
          )}
        </div>
      </header>

      {/* Body — split layout when PDF shown */}
      <div className={cn('flex flex-1 min-h-0 overflow-hidden', showPdf ? 'flex-row' : 'flex-col')}>

        {/* Left / main content */}
        <main className={cn(
          'overflow-y-auto',
          showPdf ? 'w-1/2 flex-shrink-0 px-5 py-8 space-y-8' : 'w-full px-6 py-10 space-y-8 max-w-4xl mx-auto'
        )}>

          {loading && (
            <div className="flex flex-col items-center justify-center py-32 gap-4">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              <p className="text-slate-500 text-sm">Loading…</p>
            </div>
          )}

          {!loading && !session && (
            <div className="text-center py-32 text-slate-500">Session not found.</div>
          )}

          {session && (
            <>
              {/* Progress bar */}
              {session.status === 'running' && (
                <div className="space-y-2">
                  <div className="h-1.5 w-full rounded-full bg-slate-800">
                    <div className="h-1.5 rounded-full bg-emerald-500 transition-all duration-700"
                      style={{ width: `${session.progress.percentage}%` }} />
                  </div>
                  <p className="text-xs text-slate-500">
                    {session.progress.logs.at(-1)?.message ?? 'Working…'}
                  </p>
                </div>
              )}

              {/* Compilation */}
              {session.compilation && (
                <div className={cn('rounded-xl border p-5 space-y-3',
                  session.compilation.success ? 'border-emerald-900/40 bg-emerald-950/20' : 'border-red-900/40 bg-red-950/15')}>
                  <div className="flex items-center gap-3">
                    {session.compilation.success
                      ? <CheckCircle2 className="h-5 w-5 text-emerald-400 flex-shrink-0" />
                      : <XCircle className="h-5 w-5 text-red-400 flex-shrink-0" />}
                    <span className="font-semibold text-sm flex-1">
                      {session.compilation.success ? 'Compiled successfully' : 'Compilation failed'}
                    </span>
                    {session.compilation.pdf_url && (
                      <a href={session.compilation.pdf_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-800/50 rounded px-2.5 py-1 flex-shrink-0">
                        ↓ PDF original
                      </a>
                    )}
                  </div>
                  {session.compilation.errors.length > 0 && (
                    <div className="space-y-1">
                      {session.compilation.errors.slice(0, 5).map((e, i) => (
                        <div key={i} className="flex gap-2 items-start text-xs font-mono text-red-300 bg-red-950/30 rounded px-2.5 py-1.5">
                          <Terminal className="h-3 w-3 flex-shrink-0 mt-0.5 text-red-500" />{e}
                        </div>
                      ))}
                    </div>
                  )}
                  {session.compilation.warnings.length > 0 && (
                    <details className="text-xs text-slate-500 cursor-pointer">
                      <summary className="hover:text-slate-400">{session.compilation.warnings.length} warnings</summary>
                      <div className="mt-2 space-y-1 max-h-40 overflow-y-auto pr-2">
                        {session.compilation.warnings.map((w, i) => (
                          <div key={i} className="font-mono text-yellow-600/80 break-all">{w}</div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              )}

              {/* Global scorecard */}
              {ga && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <BarChart3 className="h-4 w-4 text-emerald-400" />
                      <h2 className="font-semibold text-sm text-slate-200">Global Assessment</h2>
                    </div>
                    <div className={cn('text-xs font-mono px-2.5 py-1 rounded border',
                      ga.verdict.includes('Top') ? 'border-emerald-700/50 text-emerald-400 bg-emerald-950/30' :
                      ga.verdict.includes('Conference') ? 'border-blue-700/50 text-blue-400 bg-blue-950/30' :
                      ga.verdict.includes('Workshop') ? 'border-yellow-700/50 text-yellow-400 bg-yellow-950/30' :
                      'border-red-700/50 text-red-400 bg-red-950/30')}>
                      {ga.verdict || 'Pending'}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-around gap-4">
                    <ScoreRing value={ga.novelty} label="Novelty" color="#34d399" />
                    <ScoreRing value={ga.clarity} label="Clarity" color="#60a5fa" />
                    <ScoreRing value={ga.experimental_rigor} label="Rigor" color="#a78bfa" />
                    <ScoreRing value={ga.submission_readiness} label="Readiness" color="#fb923c" />
                    <ScoreRing value={ga.overall} label="Overall" color="#f9fafb" />
                  </div>
                  {ga.top_priorities.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                        <Zap className="h-3 w-3 text-yellow-400" /> Top priorities
                      </p>
                      {ga.top_priorities.map((p, i) => (
                        <div key={i} className="flex gap-3 text-sm text-slate-300">
                          <span className="text-yellow-500 font-bold w-5 flex-shrink-0 tabular-nums">{i + 1}.</span>
                          {p}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Document structure */}
              {session.structure && <StructurePanel s={session.structure} />}

              {/* Sections */}
              {session.sections.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                      <FileCode2 className="h-4 w-4 text-emerald-400" />
                      Section Analysis
                      <span className="text-slate-600 font-normal">({session.sections.length} sections)</span>
                    </h2>
                    <div className="flex items-center gap-2 ml-auto flex-wrap">
                      {applied.size > 0 && (
                        <span className="text-xs text-emerald-400 font-mono">{applied.size} aplicadas</span>
                      )}
                      <button onClick={applyAll} className="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700/50 text-slate-400 rounded px-2.5 py-1 transition-colors">
                        Aplicar todas
                      </button>
                      <button onClick={clearAll} disabled={applied.size === 0} className="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700/50 text-slate-400 rounded px-2.5 py-1 transition-colors disabled:opacity-40">
                        Quitar todas
                      </button>
                      {applied.size > 0 && (
                        <>
                          <button
                            onClick={handleCompilePatched}
                            disabled={compiling}
                            className="text-xs bg-emerald-900/50 hover:bg-emerald-900/70 border border-emerald-700/50 text-emerald-300 rounded px-2.5 py-1 transition-colors flex items-center gap-1 disabled:opacity-50"
                          >
                            {compiling ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                            Ver PDF parcheado
                          </button>
                          <button onClick={handleDownloadPatched} className="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700/50 text-slate-400 rounded px-2.5 py-1 transition-colors">
                            ↓ .zip parcheado
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  {session.sections.map((sec, i) => (
                    <SectionCard key={i} sec={sec} secIdx={i} applied={applied} onToggle={toggleSuggestion} />
                  ))}
                </div>
              )}

              {/* Weak claims */}
              {session.weak_claims.length > 0 && (
                <div className="rounded-xl border border-red-900/30 bg-red-950/10 p-5 space-y-3">
                  <h2 className="flex items-center gap-2 text-sm font-semibold text-red-300">
                    <ShieldAlert className="h-4 w-4" /> Weak or unsupported claims
                  </h2>
                  {session.weak_claims.map((c, i) => (
                    <div key={i} className="flex gap-2 text-xs text-slate-400">
                      <AlertTriangle className="h-3.5 w-3.5 text-red-500/70 flex-shrink-0 mt-0.5" />{c}
                    </div>
                  ))}
                </div>
              )}

              {/* Suggested tables */}
              {session.suggested_tables.length > 0 && (
                <div className="space-y-3">
                  <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                    <Table2 className="h-4 w-4 text-teal-400" /> Suggested Tables
                  </h2>
                  {session.suggested_tables.map((t, i) => (
                    <div key={i} className="rounded-xl border border-teal-900/30 bg-teal-950/10 p-5 space-y-3">
                      <div>
                        <p className="text-sm font-medium text-teal-300">{t.title}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{t.rationale}</p>
                      </div>
                      {t.latex && (
                        <div className="relative">
                          <pre className="text-xs font-mono text-slate-400 bg-slate-950/60 border border-slate-800 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
                            {t.latex}
                          </pre>
                          <div className="absolute top-2 right-2"><CopyButton text={t.latex} /></div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Suggested figures */}
              {session.suggested_figures.length > 0 && (
                <div className="space-y-3">
                  <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                    <ImageIcon className="h-4 w-4 text-blue-400" /> Suggested Figures
                  </h2>
                  {session.suggested_figures.map((f, i) => (
                    <div key={i} className="rounded-xl border border-blue-900/30 bg-blue-950/10 p-4 space-y-1">
                      <p className="text-sm font-medium text-blue-300">{f.title}</p>
                      <p className="text-xs text-slate-400">{f.description}</p>
                      {f.placement && (
                        <p className="text-xs text-slate-600">Place in: <span className="font-mono text-slate-500">{f.placement}</span></p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Submission checklist */}
              {ga && ga.submission_checklist.length > 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 space-y-3">
                  <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                    <ClipboardList className="h-4 w-4 text-violet-400" /> Submission Checklist
                  </h2>
                  {ga.submission_checklist.map((item, i) => (
                    <label key={i} className="flex items-start gap-3 cursor-pointer group">
                      <input type="checkbox" className="mt-0.5 accent-violet-500 flex-shrink-0" />
                      <span className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors">{item}</span>
                    </label>
                  ))}
                </div>
              )}

              {/* Error state */}
              {session.status === 'error' && (
                <div className="rounded-xl border border-red-800/50 bg-red-950/20 p-5 space-y-2">
                  <div className="flex items-center gap-2 text-red-300 font-semibold text-sm">
                    <XCircle className="h-4 w-4" /> Analysis failed
                  </div>
                  <p className="text-xs text-slate-500">{session.error}</p>
                </div>
              )}

              {/* Hint while compiling */}
              {session.status === 'running' && session.progress.percentage < 20 && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-5 flex items-start gap-3">
                  <Lightbulb className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-slate-500">
                    Compilando tu proyecto LaTeX en Docker. Si es la primera vez,
                    puede tardar unos minutos mientras descarga TeX Live.
                  </p>
                </div>
              )}
            </>
          )}
        </main>

        {/* Right — PDF panel */}
        {showPdf && (
          <div className="w-1/2 flex-shrink-0 sticky top-[57px] h-[calc(100vh-57px)]">
            <PdfPanel
              pdfUrl={session?.compilation?.pdf_url}
              annotatedUrl={session?.annotated_pdf_url}
              patchedUrl={patchedPdfUrl}
              patchErrors={patchErrors}
              compiling={compiling}
              rawFiles={rawFiles}
              rawFileList={rawFileList}
              rawMain={rawMain}
              onClose={() => setShowPdf(false)}
              onFetchRaw={fetchRaw}
              onCompileEdit={handleCompileEdit}
            />
          </div>
        )}
      </div>
    </div>
  )
}
