'use client'

import React, { useState, useEffect, useRef } from 'react'
import {
  BookOpen,
  Table2,
  Network,
  AlertTriangle,
  Map,
  CheckCircle2,
  Share2,
  Link2,
  FileDown,
  Printer,
  ClipboardList,
  Check,
  X,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import PapersTable from '@/components/PapersTable'
import CitationNetwork from '@/components/CitationNetwork'
import MarkdownContent from '@/components/MarkdownContent'
import { API_BASE_URL } from '@/lib/api'
import type { ResearchResult, Difficulty } from '@/lib/types'

interface ResearchReportProps {
  result: ResearchResult
  sessionId: string
  topic?: string   // the original search input — used in share export
}

type TabId = 'overview' | 'papers' | 'network' | 'gaps' | 'roadmap'

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <BookOpen className="h-4 w-4" /> },
  { id: 'papers', label: 'Papers', icon: <Table2 className="h-4 w-4" /> },
  { id: 'network', label: 'Network', icon: <Network className="h-4 w-4" /> },
  { id: 'gaps', label: 'Gaps', icon: <AlertTriangle className="h-4 w-4" /> },
  { id: 'roadmap', label: 'Roadmap', icon: <Map className="h-4 w-4" /> },
]

const DIFFICULTY_VARIANT: Record<Difficulty, 'easy' | 'medium' | 'hard'> = {
  easy: 'easy',
  medium: 'medium',
  hard: 'hard',
}

const DIFFICULTY_COLORS: Record<Difficulty, string> = {
  easy: 'border-l-green-500',
  medium: 'border-l-yellow-500',
  hard: 'border-l-red-500',
}

// ── Export helpers ────────────────────────────────────────────────────────────

function buildMarkdown(result: ResearchResult, sessionId: string, topic: string): string {
  const date = new Date().toISOString().slice(0, 10)
  const lines: string[] = []

  lines.push(`# Research: ${topic}`)
  lines.push(`*Session: \`${sessionId}\` · Generated: ${date} · ali_researcher*`)
  lines.push('')

  // Summary
  if (result.summary) {
    lines.push('## Summary')
    lines.push('')
    lines.push(result.summary)
    lines.push('')
  }

  // Stats
  lines.push(`---`)
  lines.push(`**${result.papers.length} papers** · **${result.gap_analysis.length} research gaps** · **${result.implementation_roadmap.length} roadmap steps**`)
  lines.push(`---`)
  lines.push('')

  // Key concepts
  if (result.key_concepts.length > 0) {
    lines.push('## Key Concepts')
    lines.push('')
    lines.push(result.key_concepts.map(c => `\`${c}\``).join(' · '))
    lines.push('')
  }

  // Papers
  lines.push(`## Papers (${result.papers.length})`)
  lines.push('')
  result.papers.forEach((p, idx) => {
    const authors = p.authors.length > 0 ? p.authors.slice(0, 5).join(', ') + (p.authors.length > 5 ? ' et al.' : '') : 'Unknown'
    const year = p.year ? ` (${p.year})` : ''
    lines.push(`### ${idx + 1}. ${p.title}${year}`)
    lines.push('')
    lines.push(`- **Authors**: ${authors}`)
    if (p.venue) lines.push(`- **Venue**: ${p.venue}`)
    if (p.citation_count) lines.push(`- **Citations**: ${p.citation_count.toLocaleString()}`)
    if (p.source) lines.push(`- **Source**: ${p.source}`)
    if (p.arxiv_id) lines.push(`- **arXiv**: [${p.arxiv_id}](https://arxiv.org/abs/${p.arxiv_id})`)
    if (p.url) lines.push(`- **URL**: ${p.url}`)
    if (p.relevance_reason) lines.push(`- **Relevance**: ${p.relevance_reason}`)
    if (p.abstract) {
      lines.push('')
      lines.push(`> ${p.abstract.slice(0, 300).replace(/\n/g, ' ')}${p.abstract.length > 300 ? '…' : ''}`)
    }
    lines.push('')
    if (idx < result.papers.length - 1) lines.push('---')
    lines.push('')
  })

  // Research gaps
  if (result.gap_analysis.length > 0) {
    lines.push('## Research Gaps')
    lines.push('')
    result.gap_analysis.forEach((gap, idx) => {
      lines.push(`${idx + 1}. ${gap}`)
    })
    lines.push('')
  }

  // Roadmap
  if (result.implementation_roadmap.length > 0) {
    lines.push('## Implementation Roadmap')
    lines.push('')
    result.implementation_roadmap.forEach((step, idx) => {
      lines.push(`### ${idx + 1}. ${step.step} *(${step.difficulty})*`)
      lines.push('')
      lines.push(step.description)
      lines.push('')
    })
  }

  return lines.join('\n')
}

function buildPaperList(result: ResearchResult): string {
  return result.papers.map((p, idx) => {
    const authors = p.authors.length > 0
      ? p.authors.slice(0, 3).join(', ') + (p.authors.length > 3 ? ' et al.' : '')
      : 'Unknown authors'
    const year = p.year ? ` (${p.year})` : ''
    const venue = p.venue ? ` — ${p.venue}` : ''
    const url = p.url ? `\n   ${p.url}` : ''
    return `${idx + 1}. ${p.title}${year}\n   ${authors}${venue}${url}`
  }).join('\n\n')
}

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ── Share modal ───────────────────────────────────────────────────────────────

interface ShareModalProps {
  result: ResearchResult
  sessionId: string
  topic: string
  onClose: () => void
}

type CopiedState = 'link' | 'list' | null

function ShareModal({ result, sessionId, topic, onClose }: ShareModalProps) {
  const [copied, setCopied] = useState<CopiedState>(null)
  const backdropRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const markCopied = (key: CopiedState) => {
    setCopied(key)
    setTimeout(() => setCopied(null), 2000)
  }

  const copyLink = async () => {
    await navigator.clipboard.writeText(window.location.href)
    markCopied('link')
  }

  const copyPaperList = async () => {
    await navigator.clipboard.writeText(buildPaperList(result))
    markCopied('list')
  }

  const downloadMarkdown = () => {
    const slug = topic.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)
    const md = buildMarkdown(result, sessionId, topic)
    downloadFile(md, `research-${slug}.md`, 'text/markdown')
    onClose()
  }

  const [pdfLoading, setPdfLoading] = useState(false)

  const downloadPDF = async () => {
    setPdfLoading(true)
    try {
      const resp = await fetch(`${API_BASE_URL}/api/research/${sessionId}/export/pdf`)
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`)
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const slug = topic.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)
      a.download = `research-${slug}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      onClose()
    } catch (err) {
      console.error('PDF download failed:', err)
    } finally {
      setPdfLoading(false)
    }
  }

  const OPTIONS = [
    {
      key: 'link' as const,
      icon: copied === 'link' ? <Check className="h-4 w-4 text-green-400" /> : <Link2 className="h-4 w-4" />,
      label: copied === 'link' ? 'Link copied!' : 'Copy shareable link',
      description: 'Anyone with this URL can view the results',
      action: copyLink,
      accent: 'hover:border-indigo-700/60 hover:bg-indigo-950/20',
    },
    {
      key: 'list' as const,
      icon: copied === 'list' ? <Check className="h-4 w-4 text-green-400" /> : <ClipboardList className="h-4 w-4" />,
      label: copied === 'list' ? 'Copied!' : 'Copy paper list',
      description: `${result.papers.length} papers with authors, venue & URL`,
      action: copyPaperList,
      accent: 'hover:border-cyan-700/60 hover:bg-cyan-950/20',
    },
    {
      key: 'md' as const,
      icon: <FileDown className="h-4 w-4" />,
      label: 'Download as Markdown',
      description: 'Full report: summary, papers, gaps, roadmap (.md)',
      action: downloadMarkdown,
      accent: 'hover:border-emerald-700/60 hover:bg-emerald-950/20',
    },
    {
      key: 'pdf' as const,
      icon: pdfLoading
        ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-amber-400 inline-block" />
        : <Printer className="h-4 w-4" />,
      label: pdfLoading ? 'Generating PDF…' : 'Download as PDF',
      description: 'Full report: summary, all papers, gaps & roadmap (.pdf)',
      action: downloadPDF,
      accent: 'hover:border-amber-700/60 hover:bg-amber-950/20',
    },
  ]

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === backdropRef.current) onClose() }}
    >
      <div className="w-full max-w-md rounded-2xl border border-[#1d2d47] bg-[#0d1526] shadow-2xl animate-fade-up">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1d2d47] px-5 py-4">
          <div className="flex items-center gap-2.5">
            <Share2 className="h-4 w-4 text-indigo-400" />
            <div>
              <p className="text-sm font-semibold text-slate-100">Share research</p>
              <p className="text-[11px] text-slate-500 truncate max-w-[240px]">{topic}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-[#121d32] hover:text-slate-300 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Options */}
        <div className="p-3 space-y-2">
          {OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={opt.action}
              className={cn(
                'w-full flex items-center gap-4 rounded-xl border border-[#1d2d47] p-4 text-left transition-all duration-150',
                opt.accent
              )}
            >
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl border border-[#1d2d47] bg-[#121d32] text-slate-400">
                {opt.icon}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-200">{opt.label}</p>
                <p className="text-[11px] text-slate-500 leading-relaxed">{opt.description}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Footer note */}
        <div className="border-t border-[#1d2d47] px-5 py-3">
          <p className="text-[11px] text-slate-600 text-center">
            {result.papers.length} papers · session <code className="font-mono">{sessionId.slice(0, 8)}</code>
          </p>
        </div>
      </div>
    </div>
  )
}


// ── Tab content components ────────────────────────────────────────────────────

function OverviewTab({ result }: { result: ResearchResult }) {
  return (
    <div className="space-y-8 animate-fade-in">
      {/* Summary */}
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-4">
          Research Summary
        </h3>
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-5">
          <MarkdownContent>{result.summary}</MarkdownContent>
        </div>
      </div>

      {/* Key Concepts */}
      {result.key_concepts.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-4">
            Key Concepts
          </h3>
          <div className="flex flex-wrap gap-2">
            {result.key_concepts.map((concept, idx) => (
              <Badge key={idx} variant="default" className="text-xs py-1 px-3">
                {concept}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Papers', value: result.papers.length },
          { label: 'Gaps Identified', value: result.gap_analysis.length },
          { label: 'Roadmap Steps', value: result.implementation_roadmap.length },
          { label: 'Key Concepts', value: result.key_concepts.length },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 text-center"
          >
            <div className="text-2xl font-bold text-indigo-400">{stat.value}</div>
            <div className="text-xs text-slate-500 mt-1">{stat.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function GapsTab({ gaps }: { gaps: string[] }) {
  if (gaps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <CheckCircle2 className="h-12 w-12 mb-3 opacity-30 text-green-500" />
        <p className="text-sm">No gaps identified</p>
      </div>
    )
  }

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
            Research Gaps
          </h3>
          <p className="mt-1 text-xs text-slate-600">
            Open problems and unexplored directions identified in the literature
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-amber-800/40 bg-amber-950/30 px-3 py-1.5">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
          <span className="text-xs font-semibold text-amber-300">{gaps.length} gap{gaps.length !== 1 ? 's' : ''}</span>
        </div>
      </div>

      <div className="space-y-3">
        {gaps.map((gap, idx) => (
          <div
            key={idx}
            className="group relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition-all duration-200 hover:border-amber-800/40 hover:bg-slate-900/90"
          >
            <div className="absolute inset-y-0 left-0 w-0.5 bg-gradient-to-b from-amber-500/60 via-amber-400/30 to-transparent" />
            <div className="flex items-start gap-4">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-amber-800/40 bg-amber-950/40 text-xs font-bold tabular-nums text-amber-400">
                {String(idx + 1).padStart(2, '0')}
              </div>
              <p className="flex-1 text-sm leading-relaxed text-slate-300 group-hover:text-slate-200 transition-colors">
                {gap}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RoadmapTab({ steps }: { steps: ResearchResult['implementation_roadmap'] }) {
  if (steps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <Map className="h-12 w-12 mb-3 opacity-30" />
        <p className="text-sm">No roadmap available</p>
      </div>
    )
  }

  return (
    <div className="space-y-0 animate-fade-in">
      <p className="text-sm text-slate-400 mb-6">
        Implementation roadmap with suggested steps and difficulty levels:
      </p>
      <div className="relative">
        <div className="absolute left-[19px] top-0 bottom-0 w-0.5 bg-slate-800" />
        <div className="space-y-4">
          {steps.map((step, idx) => (
            <div key={idx} className="relative flex gap-4">
              <div className="relative z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border-2 border-slate-700 bg-slate-900 font-bold text-sm text-indigo-400">
                {idx + 1}
              </div>
              <div
                className={cn(
                  'flex-1 rounded-lg border border-l-2 border-slate-800 bg-slate-900/50 p-4 mb-1 hover:bg-slate-900/80 transition-colors',
                  DIFFICULTY_COLORS[step.difficulty]
                )}
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <h4 className="text-sm font-semibold text-slate-200 leading-snug">
                    {step.step}
                  </h4>
                  <Badge variant={DIFFICULTY_VARIANT[step.difficulty]} className="flex-shrink-0">
                    {step.difficulty}
                  </Badge>
                </div>
                <p className="text-sm text-slate-400 leading-relaxed">
                  {step.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}


// ── Main component ────────────────────────────────────────────────────────────

export default function ResearchReport({ result, sessionId, topic: topicProp }: ResearchReportProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [shareOpen, setShareOpen] = useState(false)

  // Use prop if available, fall back to document.title
  const [topic, setTopic] = useState(topicProp ?? 'Research results')
  useEffect(() => {
    if (topicProp) { setTopic(topicProp); return }
    const t = document.title.replace('ali_researcher', '').replace(/[—|-]/g, '').trim()
    if (t) setTopic(t)
  }, [topicProp])

  const tabBadge: Partial<Record<TabId, number>> = {
    papers: result.papers.length,
    gaps: result.gap_analysis.length,
    roadmap: result.implementation_roadmap.length,
  }

  return (
    <>
      {shareOpen && (
        <ShareModal
          result={result}
          sessionId={sessionId}
          topic={topic}
          onClose={() => setShareOpen(false)}
        />
      )}

      <div className="space-y-6 animate-slide-up">
        {/* Tab bar + share button */}
        <div className="flex items-center gap-2">
          <div className="flex flex-1 items-center gap-1 overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/80 p-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200 whitespace-nowrap',
                  activeTab === tab.id
                    ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                )}
              >
                <span className={activeTab === tab.id ? 'text-white' : 'text-slate-500'}>
                  {tab.icon}
                </span>
                {tab.label}
                {tabBadge[tab.id] !== undefined && (
                  <span
                    className={cn(
                      'ml-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums',
                      activeTab === tab.id
                        ? 'bg-indigo-500 text-white'
                        : 'bg-slate-700 text-slate-400'
                    )}
                  >
                    {tabBadge[tab.id]}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Share button */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShareOpen(true)}
            className="flex-shrink-0 gap-1.5"
          >
            <Share2 className="h-3.5 w-3.5" />
            Share
          </Button>
        </div>

        {/* Tab content */}
        <div className="min-h-96">
          {activeTab === 'overview' && <OverviewTab result={result} />}
          {activeTab === 'papers' && <PapersTable papers={result.papers} />}
          {activeTab === 'network' && (
            <CitationNetwork
              sessionId={sessionId}
              fallbackNodes={result.papers}
              fallbackLinks={result.citation_links}
            />
          )}
          {activeTab === 'gaps' && <GapsTab gaps={result.gap_analysis} />}
          {activeTab === 'roadmap' && (
            <RoadmapTab steps={result.implementation_roadmap} />
          )}
        </div>
      </div>
    </>
  )
}
