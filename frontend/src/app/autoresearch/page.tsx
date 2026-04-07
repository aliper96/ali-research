'use client'

import { useState } from 'react'
import { RefreshCw, Loader2 } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import ResearchProgress from '@/components/ResearchProgress'
import ResearchReport from '@/components/ResearchReport'
import { startAutoResearch, streamAutoSession, getAutoSession } from '@/lib/api'
import type { AutoResearchSession, LogEntry, SSEProgressEvent, SSEErrorEvent, Depth } from '@/lib/types'

const DEPTH_OPTIONS: { value: Depth; label: string }[] = [
  { value: 'standard', label: 'Standard' },
  { value: 'deep', label: 'Deep' },
]

export default function AutoResearchPage() {
  const [input, setInput]             = useState('')
  const [depth, setDepth]             = useState<Depth>('standard')
  const [maxIterations, setMaxIter]   = useState(3)
  const [loading, setLoading]         = useState(false)
  const [session, setSession]         = useState<AutoResearchSession | null>(null)
  const [error, setError]             = useState<string | null>(null)
  const [logs, setLogs]               = useState<LogEntry[]>([])
  const [progress, setProgress]       = useState(0)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || loading) return
    setLoading(true); setError(null); setSession(null); setLogs([]); setProgress(0)

    try {
      const { session_id } = await startAutoResearch(input.trim(), depth, maxIterations)
      const cleanup = streamAutoSession(session_id, async (event) => {
        if (event.type === 'log') {
          const ev = event as SSEProgressEvent
          setLogs(prev => [...prev, ev.log])
          setProgress(ev.percentage)
        } else if (event.type === 'complete') {
          cleanup()
          const full = await getAutoSession(session_id)
          setSession(full)
          setLoading(false)
        } else if (event.type === 'error') {
          setError((event as SSEErrorEvent).message)
          setLoading(false)
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start auto research')
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-4xl px-4 py-12 space-y-8">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-emerald-400">
              <RefreshCw className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Auto Research</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Iterative Auto Research</h1>
          <p className="text-slate-400">
            The agent autonomously decides follow-up questions and keeps researching until
            it reaches confidence or runs out of iterations.
          </p>
        </div>

        <Card className="border-slate-800 bg-slate-900/50">
          <CardContent className="pt-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="e.g. Why does reward hacking occur in RLHF-trained models?"
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
                  <label className="text-xs text-slate-400">
                    Max Iterations: {maxIterations}
                  </label>
                  <input
                    type="range" min={1} max={6} value={maxIterations}
                    onChange={e => setMaxIter(Number(e.target.value))}
                    disabled={loading}
                    className="w-full accent-emerald-500"
                  />
                </div>
                <Button type="submit" disabled={!input.trim() || loading}
                  className="bg-emerald-700 hover:bg-emerald-600">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Start'}
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

        {session?.result && (
          <ResearchReport result={session.result} sessionId={session.session_id} />
        )}
      </div>
    </main>
  )
}
