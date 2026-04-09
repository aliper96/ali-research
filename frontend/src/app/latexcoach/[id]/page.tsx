'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft, CheckCircle2, XCircle, AlertTriangle, Loader2,
  ChevronDown, ChevronUp, Copy, Check, FileCode2, Table2,
  BarChart3, Lightbulb, ClipboardList, Terminal, ImageIcon,
  Zap, ShieldAlert, BookOpen, Hash, RefreshCw,
} from 'lucide-react'
import {
  getLatexCoachSession, streamLatexCoach, requestAnnotatedPdf, reanalyzeLatexCoach,
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
function SectionCard({ sec }: { sec: SectionAnalysis }) {
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
              {sec.suggestions.map((s, i) => (
                <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 space-y-2.5">
                  {/* Header */}
                  <div className="flex items-center gap-2 flex-wrap">
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
              ))}
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
          {/* Tables */}
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
          {/* Figures */}
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
          {/* Broken refs */}
          {s.undefined_refs.length > 0 && (
            <div className="sm:col-span-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-red-500 mb-2">
                Broken \\ref without matching \\label ({s.undefined_refs.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {s.undefined_refs.map((r, i) => (
                  <span key={i} className="text-[10px] font-mono bg-red-950/30 border border-red-900/30 text-red-400 rounded px-1.5 py-0.5">{r}</span>
                ))}
              </div>
            </div>
          )}
          {/* Citation count */}
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
// Main page
// ---------------------------------------------------------------------------
export default function LatexCoachResultPage() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<LatexCoachSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [annotating, setAnnotating] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)

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
      // Stream will fire updates; also refresh immediately
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

  const ga = session?.global_assessment

  return (
    <div className="flex min-h-screen flex-col bg-[#030712] text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-1/4 -left-32 h-72 w-72 rounded-full bg-emerald-900/8 blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 h-72 w-72 rounded-full bg-teal-900/8 blur-3xl" />
      </div>

      {/* Header */}
      <header className="relative border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="mx-auto flex max-w-4xl items-center gap-4 px-6 py-4">
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

          {/* Re-analyze button — visible when completed or error */}
          {session && session.status !== 'running' && (
            <button
              onClick={handleReanalyze}
              disabled={reanalyzing}
              className="flex-shrink-0 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700/50 text-slate-400 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              title="Re-run analysis with latest code"
            >
              {reanalyzing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              Re-analizar
            </button>
          )}

          {/* Annotated PDF button */}
          {session?.status === 'completed' && (
            session.annotated_pdf_url ? (
              <a
                href={session.annotated_pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-shrink-0 text-xs bg-red-900/40 hover:bg-red-900/60 border border-red-800/50 text-red-300 rounded-lg px-3 py-1.5 transition-colors"
              >
                ↓ PDF anotado (rojo)
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

      <main className="relative mx-auto w-full max-w-4xl flex-1 px-6 py-10 space-y-8">

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
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
                  <FileCode2 className="h-4 w-4 text-emerald-400" />
                  Section Analysis
                  <span className="text-slate-600 font-normal">({session.sections.length} sections)</span>
                </h2>
                {session.sections.map((sec, i) => <SectionCard key={i} sec={sec} />)}
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
    </div>
  )
}
