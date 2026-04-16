'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Search, Zap, BarChart2, Layers, ArrowRight,
  BookOpen, Globe, Loader2, RefreshCw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { startSmartSearch, streamWebSearchSession, getWebSearchSession } from '@/lib/api'
import ResearchProgress from '@/components/ResearchProgress'
import WebSearchResultsPanel from '@/components/WebSearchResultsPanel'
import type { Depth, WebSearchResult, LogEntry, SSEProgressEvent, SSEErrorEvent } from '@/lib/types'

const DEPTH_OPTIONS: {
  value: Depth
  label: string
  icon: React.ReactNode
  time: string
}[] = [
  { value: 'quick',    label: 'Quick',    icon: <Zap className="h-3.5 w-3.5" />,      time: '~30s' },
  { value: 'standard', label: 'Standard', icon: <BarChart2 className="h-3.5 w-3.5" />, time: '~2min' },
  { value: 'deep',     label: 'Deep',     icon: <Layers className="h-3.5 w-3.5" />,    time: '~5min' },
]

const EXAMPLES = [
  'Attention mechanisms in transformers',
  'Diffusion models for image generation',
  '2312.00752',
  'What is the best laptop for ML in 2024?',
  'Graph neural networks survey',
  'Latest news about GPT-5',
]

export default function UnifiedSearch() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [depth, setDepth] = useState<Depth>('standard')
  const [detectedMode, setDetectedMode] = useState<'papers' | 'web' | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Web-search inline state
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [progress, setProgress] = useState(0)
  const [webResult, setWebResult] = useState<WebSearchResult | null>(null)
  const [lastQuery, setLastQuery] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || loading) return

    const q = query.trim()
    setLoading(true)
    setError(null)
    setDetectedMode(null)
    setWebResult(null)
    setLogs([])
    setProgress(0)
    setLastQuery(q)

    try {
      const { mode, session_id } = await startSmartSearch(q, depth)
      setDetectedMode(mode)

      if (mode === 'papers') {
        // Navigate to the papers research page (existing flow)
        router.push(`/research/${session_id}`)
        return
      }

      // Web search: stream results inline
      const cleanup = streamWebSearchSession(session_id, async (event) => {
        if (event.type === 'log') {
          const ev = event as SSEProgressEvent
          setLogs((prev) => [...prev, ev.log])
          setProgress(ev.percentage)
        } else if (event.type === 'complete') {
          cleanup()
          const full = await getWebSearchSession(session_id)
          setWebResult(full.result ?? null)
          setLoading(false)
        } else if (event.type === 'error') {
          setError((event as SSEErrorEvent).message ?? 'Unknown error')
          setLoading(false)
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start search')
      setLoading(false)
    }
  }

  function handleFollowUp(question: string) {
    setQuery(question)
    setTimeout(() => {
      const form = document.getElementById('unified-form') as HTMLFormElement | null
      form?.requestSubmit()
    }, 50)
  }

  function handleReset() {
    setWebResult(null)
    setLogs([])
    setProgress(0)
    setQuery('')
    setDetectedMode(null)
    setError(null)
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <form id="unified-form" onSubmit={handleSubmit} className="space-y-4">

        {/* Search box */}
        <div className="relative group">
          <div className={cn(
            'absolute -inset-px rounded-2xl bg-gradient-to-r from-indigo-500/40 to-purple-500/20 opacity-0 blur-sm transition-opacity duration-300',
            'group-focus-within:opacity-100'
          )} />
          <div className="relative rounded-2xl border border-[#1d2d47] bg-[#0d1526]/80 transition-colors duration-200 group-focus-within:border-indigo-500/50 backdrop-blur-sm">
            <div className="flex items-start gap-3 p-5">
              <Search className="mt-1 h-5 w-5 flex-shrink-0 text-indigo-400" />
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search papers, ask a question, paste an arXiv ID or URL..."
                rows={3}
                disabled={loading}
                className="w-full resize-none bg-transparent text-slate-100 placeholder:text-slate-500 text-[15px] leading-relaxed focus:outline-none disabled:opacity-60"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault()
                    void handleSubmit(e as unknown as React.FormEvent)
                  }
                }}
              />
            </div>

            <div className="px-5 pb-3 flex items-center justify-between">
              {/* Depth selector — used for paper searches */}
              <div className="flex items-center gap-1.5">
                {DEPTH_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    disabled={loading}
                    onClick={() => setDepth(option.value)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150',
                      depth === option.value
                        ? 'bg-indigo-600/20 border border-indigo-500/40 text-indigo-300'
                        : 'border border-transparent text-slate-500 hover:text-slate-300 hover:bg-[#121d32]'
                    )}
                  >
                    <span className={depth === option.value ? 'text-indigo-400' : 'text-slate-600'}>
                      {option.icon}
                    </span>
                    {option.label}
                    <span className={cn(
                      'font-mono text-[10px]',
                      depth === option.value ? 'text-indigo-400/70' : 'text-slate-600'
                    )}>
                      {option.time}
                    </span>
                  </button>
                ))}
              </div>
              <span className="text-[11px] text-slate-600 select-none">Ctrl+Enter</span>
            </div>
          </div>
        </div>

        {/* Mode badge — shows after detection */}
        {detectedMode && (
          <div className="flex items-center gap-2">
            {detectedMode === 'papers' ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-900/60 bg-indigo-950/30 px-3 py-1 text-xs text-indigo-400">
                <BookOpen className="h-3 w-3" />
                Searching academic papers…
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-900/60 bg-cyan-950/30 px-3 py-1 text-xs text-cyan-400">
                <Globe className="h-3 w-3 animate-pulse" style={{ animationDuration: '2s' }} />
                Searching the web…
              </span>
            )}
            {!loading && webResult && (
              <button
                type="button"
                onClick={handleReset}
                className="flex items-center gap-1 text-xs text-slate-500 transition-colors hover:text-slate-300"
              >
                <RefreshCw className="h-3 w-3" />
                New search
              </button>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-red-900/50 bg-red-900/15 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Submit */}
        {!webResult && (
          <Button
            type="submit"
            size="lg"
            className="w-full text-[15px] font-semibold font-[family-name:var(--font-display)]"
            disabled={!query.trim() || loading}
          >
            {loading ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Searching…</>
            ) : (
              <>Search <ArrowRight className="ml-2 h-4 w-4" /></>
            )}
          </Button>
        )}
      </form>

      {/* Web search progress */}
      {loading && detectedMode === 'web' && (
        <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/50 px-6 py-6">
          <ResearchProgress logs={logs} percentage={progress} />
        </div>
      )}

      {/* Inline web results */}
      {webResult && (
        <div className="mt-6">
          <WebSearchResultsPanel
            result={webResult}
            userQuestion={lastQuery}
            onFollowUp={handleFollowUp}
          />
        </div>
      )}

      {/* Example topics — only when idle */}
      {!loading && !webResult && !detectedMode && (
        <div className="mt-8">
          <p className="text-[11px] font-medium text-slate-600 mb-3 text-center uppercase tracking-widest">
            Try an example
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {EXAMPLES.map((topic) => (
              <button
                key={topic}
                type="button"
                onClick={() => setQuery(topic)}
                className={cn(
                  'rounded-full border border-[#1d2d47] bg-[#0d1526]/60 px-3 py-1.5 text-xs text-slate-500',
                  'transition-all duration-150 hover:border-indigo-600/40 hover:bg-indigo-900/15 hover:text-indigo-300',
                  'font-mono'
                )}
              >
                {topic}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
