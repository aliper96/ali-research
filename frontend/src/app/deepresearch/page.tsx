'use client'

import { useState } from 'react'
import { Cpu, Loader2, Users } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import ResearchProgress from '@/components/ResearchProgress'
import ResearchReport from '@/components/ResearchReport'
import { startDeepResearch, streamDeepSession, getDeepSession } from '@/lib/api'
import type { DeepResearchSession, LogEntry, SSEProgressEvent, SSEErrorEvent, Depth } from '@/lib/types'

const DEPTH_OPTIONS: { value: Depth; label: string }[] = [
  { value: 'standard', label: 'Standard' },
  { value: 'deep', label: 'Deep' },
]

export default function DeepResearchPage() {
  const [input, setInput]             = useState('')
  const [depth, setDepth]             = useState<Depth>('standard')
  const [numResearchers, setNum]      = useState(3)
  const [loading, setLoading]         = useState(false)
  const [session, setSession]         = useState<DeepResearchSession | null>(null)
  const [error, setError]             = useState<string | null>(null)
  const [logs, setLogs]               = useState<LogEntry[]>([])
  const [progress, setProgress]       = useState(0)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || loading) return
    setLoading(true); setError(null); setSession(null); setLogs([]); setProgress(0)

    try {
      const { session_id } = await startDeepResearch(input.trim(), depth, numResearchers)
      const cleanup = streamDeepSession(session_id, async (event) => {
        if (event.type === 'log') {
          const ev = event as SSEProgressEvent
          setLogs(prev => [...prev, ev.log])
          setProgress(ev.percentage)
        } else if (event.type === 'complete') {
          cleanup()
          const full = await getDeepSession(session_id)
          setSession(full)
          setLoading(false)
        } else if (event.type === 'error') {
          setError((event as SSEErrorEvent).message)
          setLoading(false)
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start deep research')
      setLoading(false)
    }
  }

  const result = session?.result
  const synthesis = result?.synthesis  // the merged ResearchResult
  const researchers = result?.researchers ?? []
  const verification = result?.verification

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-4xl px-4 py-12 space-y-8">
        {/* Header */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-indigo-400">
              <Cpu className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Deep Research</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Multi-Agent Deep Research</h1>
          <p className="text-slate-400">
            Orchestrates multiple parallel AI researchers, each covering a subtopic,
            then synthesizes and verifies their findings.
          </p>
        </div>

        {/* Form */}
        <Card className="border-slate-800 bg-slate-900/50">
          <CardContent className="pt-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="e.g. Transformer architectures for time-series forecasting"
                disabled={loading}
              />
              <div className="flex gap-4 items-end">
                <div className="space-y-1 flex-1">
                  <label className="text-xs text-slate-400">Depth</label>
                  <select
                    value={depth}
                    onChange={e => setDepth(e.target.value as Depth)}
                    disabled={loading}
                    className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {DEPTH_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div className="space-y-1 flex-1">
                  <label className="text-xs text-slate-400 flex items-center gap-1">
                    <Users className="h-3 w-3" /> Researchers: {numResearchers}
                  </label>
                  <input
                    type="range" min={2} max={5} value={numResearchers}
                    onChange={e => setNum(Number(e.target.value))}
                    disabled={loading}
                    className="w-full accent-indigo-500"
                  />
                </div>
                <Button type="submit" disabled={!input.trim() || loading}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Research'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {loading && <ResearchProgress logs={logs} percentage={progress} status="running" />}

        {error && (
          <div className="rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Researcher subtopic badges */}
        {researchers.length > 0 && (
          <div className="space-y-2">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Subtopics Covered</h2>
            <div className="flex flex-wrap gap-2">
              {researchers.map((r, i) => (
                <span key={i} className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                  r.status === 'done'
                    ? 'border-indigo-800/50 bg-indigo-900/20 text-indigo-300'
                    : r.status === 'error'
                    ? 'border-red-800/50 bg-red-900/20 text-red-300'
                    : 'border-slate-700 bg-slate-800/50 text-slate-400'
                }`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${r.status === 'done' ? 'bg-indigo-400' : r.status === 'error' ? 'bg-red-400' : 'bg-slate-500'}`} />
                  {r.subtopic} ({r.papers?.length ?? 0} papers)
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Verification summary */}
        {verification && (
          <Card className="border-slate-800 bg-slate-900/50">
            <CardContent className="pt-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-300">Verification Report</span>
                <span className="text-xs text-slate-400">
                  Confidence: {Math.round((verification.overall_confidence ?? 0) * 100)}%
                </span>
              </div>
              {verification.unsupported_sentences.length > 0 && (
                <p className="text-xs text-amber-400">
                  {verification.unsupported_sentences.length} claim(s) not backed by evidence
                </p>
              )}
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {verification.verified_claims.slice(0, 8).map((c, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className={c.verdict === 'supported' ? 'text-emerald-400' : c.verdict === 'unsupported' ? 'text-red-400' : 'text-amber-400'}>
                      {c.verdict === 'supported' ? '✓' : c.verdict === 'unsupported' ? '✗' : '~'}
                    </span>
                    <span className="text-slate-300">{c.claim}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Synthesis result */}
        {synthesis && (
          <ResearchReport result={synthesis} sessionId={session?.session_id ?? ''} />
        )}
      </div>
    </main>
  )
}
