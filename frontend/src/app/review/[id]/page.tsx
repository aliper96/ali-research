'use client'

import React, { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft, CheckCircle2, XCircle, Clock, AlertTriangle, FileText,
  ChevronDown, ChevronUp, Star, Zap, Users, BookOpen, Target,
  Share2, Copy, Check, Download, Loader2, X,
} from 'lucide-react'
import Link from 'next/link'
import { getReviewSession, streamReview, type ReviewSession, type ReviewerReport, type EditorReport, API_BASE_URL } from '@/lib/api'
import { cn } from '@/lib/utils'
import MarkdownContent from '@/components/MarkdownContent'

// ---------------------------------------------------------------------------
// Share helpers
// ---------------------------------------------------------------------------

const REC_LABEL_MAP: Record<string, string> = {
  accept: 'Accept',
  minor_revision: 'Minor Revision',
  major_revision: 'Major Revision',
  reject: 'Reject',
}

function buildReviewMarkdown(session: ReviewSession): string {
  const lines: string[] = []
  lines.push(`# Peer Review — ${session.paper_title || 'Untitled'}`)
  lines.push(``)
  if (session.editor_report) {
    const ed = session.editor_report
    lines.push(`## Editor's Decision`)
    lines.push(``)
    lines.push(`**Decision:** ${REC_LABEL_MAP[ed.final_recommendation] ?? ed.final_recommendation}`)
    if (ed.novelty_verdict)  lines.push(`**Novelty:** ${ed.novelty_verdict}`)
    if (ed.publishability)   lines.push(`**Publishability:** ${ed.publishability}`)
    lines.push(`**Reviewer agreement:** ${(ed.reviewer_agreement * 100).toFixed(0)}%`)
    lines.push(``)
    lines.push(`**Scores:** Novelty ${ed.novelty_score.toFixed(1)} | Technical ${ed.technical_score.toFixed(1)} | Clarity ${ed.clarity_score.toFixed(1)} | Contribution ${ed.contribution_score.toFixed(1)}`)
    lines.push(``)
    if (ed.consensus_summary) {
      lines.push(`### Consensus Summary`)
      lines.push(``)
      lines.push(ed.consensus_summary)
      lines.push(``)
    }
    if (ed.action_items.length > 0) {
      lines.push(`### Required Actions`)
      lines.push(``)
      ed.action_items.forEach((item, i) => lines.push(`${i + 1}. ${item}`))
      lines.push(``)
    }
    if (ed.major_issues.length > 0) {
      lines.push(`### Major Issues`)
      lines.push(``)
      ed.major_issues.forEach(s => lines.push(`- ${s}`))
      lines.push(``)
    }
    if (ed.minor_issues.length > 0) {
      lines.push(`### Minor Issues`)
      lines.push(``)
      ed.minor_issues.forEach(s => lines.push(`- ${s}`))
      lines.push(``)
    }
    if (ed.strengths.length > 0) {
      lines.push(`### Strengths`)
      lines.push(``)
      ed.strengths.forEach(s => lines.push(`- ${s}`))
      lines.push(``)
    }
  }

  const done = session.reviewer_reports.filter(r => r.status === 'done')
  if (done.length > 0) {
    lines.push(`---`)
    lines.push(``)
    lines.push(`## Individual Reviews`)
    lines.push(``)
    done.forEach(report => {
      lines.push(`### Reviewer ${report.reviewer_id}`)
      if (report.persona) lines.push(`*${report.persona}*`)
      lines.push(``)
      lines.push(`**Recommendation:** ${REC_LABEL_MAP[report.recommendation] ?? report.recommendation}  |  **Overall:** ${report.overall_score.toFixed(1)}/10`)
      lines.push(`**Scores:** Novelty ${report.novelty_score.toFixed(1)} | Technical ${report.technical_score.toFixed(1)} | Clarity ${report.clarity_score.toFixed(1)} | Contribution ${report.contribution_score.toFixed(1)}`)
      lines.push(``)
      if (report.summary) {
        lines.push(report.summary)
        lines.push(``)
      }
      if (report.major_issues.length > 0) {
        lines.push(`**Major issues:**`)
        report.major_issues.forEach(s => lines.push(`- ${s}`))
        lines.push(``)
      }
      if (report.minor_issues.length > 0) {
        lines.push(`**Minor issues:**`)
        report.minor_issues.forEach(s => lines.push(`- ${s}`))
        lines.push(``)
      }
      if (report.strengths.length > 0) {
        lines.push(`**Strengths:**`)
        report.strengths.forEach(s => lines.push(`- ${s}`))
        lines.push(``)
      }
      if (report.missing_citations.length > 0) {
        lines.push(`**Missing citations:**`)
        report.missing_citations.forEach(s => lines.push(`- ${s}`))
        lines.push(``)
      }
    })
  }

  if (session.paper_abstract) {
    lines.push(`---`)
    lines.push(``)
    lines.push(`## Paper Abstract`)
    lines.push(``)
    lines.push(session.paper_abstract)
    lines.push(``)
  }

  return lines.join('\n')
}

function downloadFile(content: string, filename: string, type = 'text/markdown') {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function ReviewShareModal({
  session,
  sessionId,
  onClose,
}: {
  session: ReviewSession
  sessionId: string
  onClose: () => void
}) {
  const [copiedLink, setCopiedLink] = useState(false)
  const [copiedText, setCopiedText] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)

  const pageUrl = typeof window !== 'undefined' ? window.location.href : ''

  const handleCopyLink = async () => {
    await navigator.clipboard.writeText(pageUrl)
    setCopiedLink(true)
    setTimeout(() => setCopiedLink(false), 2000)
  }

  const handleCopyText = async () => {
    const md = buildReviewMarkdown(session)
    await navigator.clipboard.writeText(md)
    setCopiedText(true)
    setTimeout(() => setCopiedText(false), 2000)
  }

  const handleDownloadMarkdown = () => {
    const md = buildReviewMarkdown(session)
    const slug = (session.paper_title || 'review')
      .replace(/[^a-z0-9]+/gi, '-')
      .toLowerCase()
      .slice(0, 40)
    downloadFile(md, `review-${slug}.md`)
  }

  const handleDownloadPdf = async () => {
    setPdfLoading(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/review/${sessionId}/export/pdf`)
      if (!res.ok) throw new Error('PDF export failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const slug = (session.paper_title || 'review')
        .replace(/[^a-z0-9]+/gi, '-')
        .toLowerCase()
        .slice(0, 40)
      a.download = `review-${slug}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setPdfLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-semibold text-slate-100">Share Review</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-2">
          {/* Copy link */}
          <button
            onClick={handleCopyLink}
            className="w-full flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 text-left text-sm hover:bg-slate-800 hover:border-violet-600/50 transition-all"
          >
            {copiedLink ? <Check className="h-4 w-4 text-green-400 flex-shrink-0" /> : <Copy className="h-4 w-4 text-violet-400 flex-shrink-0" />}
            <span className={copiedLink ? 'text-green-300' : 'text-slate-200'}>
              {copiedLink ? 'Link copied!' : 'Copy link'}
            </span>
          </button>

          {/* Copy review text */}
          <button
            onClick={handleCopyText}
            className="w-full flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 text-left text-sm hover:bg-slate-800 hover:border-violet-600/50 transition-all"
          >
            {copiedText ? <Check className="h-4 w-4 text-green-400 flex-shrink-0" /> : <Copy className="h-4 w-4 text-violet-400 flex-shrink-0" />}
            <span className={copiedText ? 'text-green-300' : 'text-slate-200'}>
              {copiedText ? 'Copied!' : 'Copy full review text'}
            </span>
          </button>

          {/* Download markdown */}
          <button
            onClick={handleDownloadMarkdown}
            className="w-full flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 text-left text-sm hover:bg-slate-800 hover:border-violet-600/50 transition-all"
          >
            <Download className="h-4 w-4 text-violet-400 flex-shrink-0" />
            <span className="text-slate-200">Download Markdown (.md)</span>
          </button>

          {/* Download PDF */}
          <button
            onClick={handleDownloadPdf}
            disabled={pdfLoading}
            className="w-full flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 text-left text-sm hover:bg-slate-800 hover:border-violet-600/50 transition-all disabled:opacity-60"
          >
            {pdfLoading
              ? <Loader2 className="h-4 w-4 text-violet-400 animate-spin flex-shrink-0" />
              : <Download className="h-4 w-4 text-violet-400 flex-shrink-0" />
            }
            <span className="text-slate-200">{pdfLoading ? 'Generating PDF…' : 'Download PDF'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const REC_LABEL: Record<string, string> = {
  accept: 'Accept',
  minor_revision: 'Minor Revision',
  major_revision: 'Major Revision',
  reject: 'Reject',
}
const REC_COLOR: Record<string, string> = {
  accept: 'text-green-300 border-green-700/50 bg-green-900/20',
  minor_revision: 'text-sky-300 border-sky-700/50 bg-sky-900/20',
  major_revision: 'text-yellow-300 border-yellow-700/50 bg-yellow-900/20',
  reject: 'text-red-300 border-red-700/50 bg-red-900/20',
}
const REC_BG_STRONG: Record<string, string> = {
  accept: 'bg-green-600',
  minor_revision: 'bg-sky-600',
  major_revision: 'bg-yellow-600',
  reject: 'bg-red-600',
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="font-mono font-semibold text-slate-200">{value.toFixed(1)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-violet-500 transition-all duration-700"
          style={{ width: `${(value / 10) * 100}%` }}
        />
      </div>
    </div>
  )
}

function ReviewerCard({ report, index }: { report: ReviewerReport; index: number }) {
  const [open, setOpen] = useState(false)
  const isPending = report.status === 'pending'
  const isRunning = report.status === 'running'
  const isDone    = report.status === 'done'
  const isError   = report.status === 'error'

  return (
    <div className={cn(
      'rounded-xl border transition-all duration-200',
      isDone    ? 'border-slate-700 bg-slate-900/60' :
      isRunning ? 'border-violet-700/50 bg-violet-900/10' :
      isError   ? 'border-red-800/40 bg-red-900/10' :
                  'border-slate-800 bg-slate-900/30 opacity-50',
    )}>
      {/* Header */}
      <button
        disabled={!isDone}
        onClick={() => isDone && setOpen(o => !o)}
        className="w-full flex items-center gap-4 px-5 py-4 text-left"
      >
        {/* Avatar */}
        <div className={cn(
          'flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border text-sm font-bold',
          isDone    ? 'border-violet-600/50 bg-violet-900/30 text-violet-300' :
          isRunning ? 'border-violet-600/50 bg-violet-900/20 text-violet-400' :
                      'border-slate-700 bg-slate-800 text-slate-600',
        )}>
          R{report.reviewer_id}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 truncate">
            Reviewer {report.reviewer_id}
          </p>
          <p className="text-xs text-slate-500 truncate">{report.persona || 'Pending…'}</p>
        </div>

        {/* Status / Recommendation */}
        {isDone && (
          <div className="flex items-center gap-3 flex-shrink-0">
            <span className={cn(
              'text-xs font-semibold border rounded-full px-2.5 py-0.5',
              REC_COLOR[report.recommendation] ?? 'text-slate-400 border-slate-700 bg-slate-800',
            )}>
              {REC_LABEL[report.recommendation] ?? report.recommendation}
            </span>
            <span className="text-xs text-slate-500 font-mono">{report.overall_score.toFixed(1)}/10</span>
            {open ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
          </div>
        )}
        {isRunning && (
          <div className="flex items-center gap-2 text-xs text-violet-400">
            <span className="flex gap-1">
              {[0,1,2].map(i => (
                <span key={i} className="h-1.5 w-1.5 rounded-full bg-violet-400 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
            </span>
            Reviewing…
          </div>
        )}
        {isPending && <span className="text-xs text-slate-600">Waiting…</span>}
        {isError && <span className="text-xs text-red-400">Error</span>}
      </button>

      {/* Expanded */}
      {open && isDone && (
        <div className="border-t border-slate-800 px-5 py-5 space-y-5">
          {/* Summary */}
          {report.summary && (
            <MarkdownContent>{report.summary}</MarkdownContent>
          )}

          {/* Scores */}
          <div className="grid grid-cols-2 gap-3">
            <ScoreBar label="Novelty" value={report.novelty_score} />
            <ScoreBar label="Technical" value={report.technical_score} />
            <ScoreBar label="Clarity" value={report.clarity_score} />
            <ScoreBar label="Contribution" value={report.contribution_score} />
          </div>

          {/* Issues */}
          {report.major_issues.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-red-400 mb-2">Major issues</p>
              <ul className="space-y-1.5">
                {report.major_issues.map((issue, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                    <XCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0 mt-0.5" />
                    {issue}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.minor_issues.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-yellow-400 mb-2">Minor issues</p>
              <ul className="space-y-1.5">
                {report.minor_issues.map((issue, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                    <AlertTriangle className="h-3.5 w-3.5 text-yellow-400 flex-shrink-0 mt-0.5" />
                    {issue}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.strengths.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-green-400 mb-2">Strengths</p>
              <ul className="space-y-1.5">
                {report.strengths.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-400 flex-shrink-0 mt-0.5" />
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.missing_citations.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-sky-400 mb-2">Missing citations</p>
              <ul className="space-y-1 text-xs text-slate-400">
                {report.missing_citations.map((c, i) => <li key={i}>• {c}</li>)}
              </ul>
            </div>
          )}
          {report.related_papers_found.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Related work found</p>
              <ul className="space-y-1 text-xs text-slate-500">
                {report.related_papers_found.map((p, i) => <li key={i}>• {p}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function EditorVerdict({ report }: { report: EditorReport }) {
  return (
    <div className="rounded-2xl border border-violet-700/40 bg-violet-950/30 p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-violet-900/50 border border-violet-700/50">
          <Users className="h-6 w-6 text-violet-300" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-base font-bold text-slate-100">Editor's Decision</h3>
            <span className={cn('text-sm font-bold rounded-full px-3 py-1 text-white', REC_BG_STRONG[report.final_recommendation])}>
              {REC_LABEL[report.final_recommendation]}
            </span>
          </div>
          <div className="mt-1.5 flex gap-4 text-xs text-slate-400 flex-wrap">
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3 text-amber-400" /> {report.novelty_verdict}
            </span>
            <span className="flex items-center gap-1">
              <Target className="h-3 w-3 text-sky-400" /> {report.publishability}
            </span>
            <span className="flex items-center gap-1">
              <Star className="h-3 w-3 text-violet-400" />
              Reviewer agreement: {(report.reviewer_agreement * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>

      {/* Summary */}
      {report.consensus_summary && (
        <div className="border-l-2 border-violet-700/50 pl-4">
          <MarkdownContent>{report.consensus_summary}</MarkdownContent>
        </div>
      )}

      {/* Score overview */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Novelty',      v: report.novelty_score },
          { label: 'Technical',    v: report.technical_score },
          { label: 'Clarity',      v: report.clarity_score },
          { label: 'Contribution', v: report.contribution_score },
        ].map(({ label, v }) => (
          <div key={label} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-center">
            <div className="text-xl font-bold text-violet-300">{v.toFixed(1)}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Action items */}
      {report.action_items.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Required actions for authors</p>
          <ol className="space-y-2">
            {report.action_items.map((item, i) => (
              <li key={i} className="flex items-start gap-3 text-sm text-slate-300">
                <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-violet-900/40 border border-violet-700/50 text-[10px] font-bold text-violet-400 tabular-nums">
                  {i + 1}
                </span>
                {item}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Consolidated Major/Minor */}
      <div className="grid sm:grid-cols-2 gap-4">
        {report.major_issues.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-red-400 mb-2">
              Major issues ({report.major_issues.length})
            </p>
            <ul className="space-y-1.5">
              {report.major_issues.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-slate-400">
                  <XCircle className="h-3 w-3 text-red-400 flex-shrink-0 mt-0.5" />{s}
                </li>
              ))}
            </ul>
          </div>
        )}
        {report.minor_issues.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-yellow-400 mb-2">
              Minor issues ({report.minor_issues.length})
            </p>
            <ul className="space-y-1.5">
              {report.minor_issues.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-slate-400">
                  <AlertTriangle className="h-3 w-3 text-yellow-400 flex-shrink-0 mt-0.5" />{s}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Strengths */}
      {report.strengths.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-green-400 mb-2">Strengths</p>
          <ul className="space-y-1.5">
            {report.strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-slate-400">
                <CheckCircle2 className="h-3 w-3 text-green-400 flex-shrink-0 mt-0.5" />{s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ReviewSessionPage() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<ReviewSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [shareOpen, setShareOpen] = useState(false)
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (!id) return

    getReviewSession(id).then(s => {
      setSession(s)
      setLoading(false)
      if (s.status === 'completed' || s.status === 'error') return

      // Subscribe to SSE
      cleanupRef.current = streamReview(id, (event: any) => {
        if (event.type === 'complete') {
          getReviewSession(id).then(fresh => setSession(fresh))
        } else if (event.type === 'reviewer_update') {
          setSession(prev => {
            if (!prev) return prev
            const updated = prev.reviewer_reports.map(r =>
              r.reviewer_id === event.reviewer_id
                ? { ...r, status: event.status, recommendation: event.recommendation ?? r.recommendation, overall_score: event.overall_score ?? r.overall_score }
                : r
            )
            return { ...prev, reviewer_reports: updated, progress: { ...prev.progress, percentage: event.percentage ?? prev.progress.percentage } }
          })
        } else if (event.type === 'log') {
          setSession(prev => prev ? { ...prev, progress: { ...prev.progress, percentage: event.percentage ?? prev.progress.percentage } } : prev)
        }
      })
    }).catch(() => setLoading(false))

    return () => { cleanupRef.current?.() }
  }, [id])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#030712]">
        <div className="flex gap-1.5">
          {[0,1,2].map(i => <span key={i} className="h-2.5 w-2.5 rounded-full bg-violet-500 animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />)}
        </div>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#030712] text-slate-400 gap-4">
        <p>Review session not found.</p>
        <Link href="/review" className="text-sm text-violet-400 hover:text-violet-300">← Start a new review</Link>
      </div>
    )
  }

  const isRunning = session.status === 'running'
  const doneCount = session.reviewer_reports.filter(r => r.status === 'done').length

  return (
    <div className="flex min-h-screen flex-col bg-[#030712] text-slate-100">
      {shareOpen && session.status === 'completed' && (
        <ReviewShareModal
          session={session}
          sessionId={id}
          onClose={() => setShareOpen(false)}
        />
      )}
      <header className="sticky top-0 z-10 border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-6 py-4">
          <Link href="/review" className="flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors text-sm">
            <ArrowLeft className="h-4 w-4" /> New review
          </Link>
          <div className="h-5 w-px bg-slate-800" />
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <FileText className="h-4 w-4 text-violet-400 flex-shrink-0" />
            <span className="text-sm font-medium text-slate-200 truncate">{session.paper_title}</span>
          </div>
          {isRunning && (
            <div className="flex items-center gap-2 text-xs text-violet-400 flex-shrink-0">
              <span className="flex gap-1">
                {[0,1,2].map(i => <span key={i} className="h-1.5 w-1.5 rounded-full bg-violet-400 animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />)}
              </span>
              {doneCount}/{session.num_reviewers} done
            </div>
          )}
          {session.status === 'completed' && (
            <button
              onClick={() => setShareOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-300 hover:border-violet-600/50 hover:text-violet-300 transition-all flex-shrink-0"
            >
              <Share2 className="h-3.5 w-3.5" />
              Share
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-8 space-y-8">

        {/* Progress bar (while running) */}
        {isRunning && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-slate-500">
              <span>Review in progress…</span>
              <span className="font-mono text-violet-400">{session.progress.percentage}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-slate-800">
              <div className="h-full rounded-full bg-violet-500 transition-all duration-500"
                style={{ width: `${session.progress.percentage}%` }} />
            </div>
          </div>
        )}

        {/* Editor verdict (shown when complete) */}
        {session.editor_report && <EditorVerdict report={session.editor_report} />}

        {/* Reviewer cards */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
            Individual Reviews ({doneCount}/{session.num_reviewers} complete)
          </h2>
          {session.reviewer_reports.map((report, i) => (
            <ReviewerCard key={report.reviewer_id} report={report} index={i} />
          ))}
        </div>

        {/* Abstract */}
        {session.paper_abstract && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-2">
              <BookOpen className="h-3.5 w-3.5" /> Paper abstract
            </p>
            <p className="text-sm text-slate-400 leading-relaxed">{session.paper_abstract}</p>
          </div>
        )}
      </main>
    </div>
  )
}
