'use client'

import { useState } from 'react'
import { Search, Loader2, FlaskConical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import ResearchProgress from '@/components/ResearchProgress'
import AuditReport from '@/components/AuditReport'
import { startAudit, streamAudit, getAuditSession } from '@/lib/api'
import type { AuditSession, LogEntry, SSEErrorEvent, SSEProgressEvent } from '@/lib/types'

export default function AuditPage() {
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [session, setSession]   = useState<AuditSession | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [logs, setLogs]         = useState<LogEntry[]>([])
  const [progress, setProgress] = useState(0)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || loading) return
    setLoading(true)
    setError(null)
    setSession(null)
    setLogs([])
    setProgress(0)

    try {
      const { session_id } = await startAudit(input.trim())

      const cleanup = streamAudit(session_id, async (event) => {
        if (event.type === 'log') {
          const ev = event as SSEProgressEvent
          setLogs(prev => [...prev, ev.log])
          setProgress(ev.percentage)
        } else if (event.type === 'complete') {
          cleanup()
          const full = await getAuditSession(session_id)
          setSession(full)
          setLoading(false)
        } else if (event.type === 'error') {
          const ev = event as SSEErrorEvent
          setError(ev.message)
          setLoading(false)
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start audit')
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-3xl px-4 py-12 space-y-8">
        {/* Header */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-indigo-400">
            <FlaskConical className="h-5 w-5" />
            <span className="text-sm font-semibold uppercase tracking-wider">Paper Audit</span>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Claims vs. Code</h1>
          <p className="text-slate-400">
            Paste an arXiv ID, DOI, URL, or paper title. The agent will extract key claims from the
            paper and verify them against the public repository.
          </p>
        </div>

        {/* Form */}
        <Card className="border-slate-800 bg-slate-900/50">
          <CardContent className="pt-6">
            <form onSubmit={handleSubmit} className="flex gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                <Input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="2301.07041  ·  10.1145/3531146  ·  Attention is All You Need"
                  className="pl-9"
                  disabled={loading}
                />
              </div>
              <Button type="submit" disabled={!input.trim() || loading}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Audit'}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Progress */}
        {loading && (
          <ResearchProgress
            logs={logs}
            percentage={progress}
            status="running"
          />
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Result */}
        {session?.result && <AuditReport result={session.result} />}
      </div>
    </main>
  )
}
