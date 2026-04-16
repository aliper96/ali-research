'use client'

import { useState } from 'react'
import {
  Globe,
  Loader2,
  Search,
  RefreshCw,
} from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import ResearchProgress from '@/components/ResearchProgress'
import WebSearchResultsPanel from '@/components/WebSearchResultsPanel'
import { startWebSearch, streamWebSearchSession, getWebSearchSession } from '@/lib/api'
import type {
  WebSearchSession,
  LogEntry,
  SSEProgressEvent,
  SSEErrorEvent,
  WebSearchRecency,
} from '@/lib/types'

const RECENCY_OPTIONS: { value: WebSearchRecency; label: string }[] = [
  { value: 'any', label: 'Any time' },
  { value: 'day', label: 'Past 24h' },
  { value: 'week', label: 'Past week' },
  { value: 'month', label: 'Past month' },
]

export default function WebSearchPage() {
  const [input, setInput] = useState('')
  const [recency, setRecency] = useState<WebSearchRecency>('any')
  const [loading, setLoading] = useState(false)
  const [session, setSession] = useState<WebSearchSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [progress, setProgress] = useState(0)
  const [lastQuery, setLastQuery] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || loading) return

    const q = input.trim()
    setLoading(true)
    setError(null)
    setSession(null)
    setLogs([])
    setProgress(0)
    setLastQuery(q)

    try {
      const { session_id } = await startWebSearch(q, recency)
      const cleanup = streamWebSearchSession(session_id, async (event) => {
        if (event.type === 'log') {
          const ev = event as SSEProgressEvent
          setLogs((prev) => [...prev, ev.log])
          setProgress(ev.percentage)
        } else if (event.type === 'complete') {
          cleanup()
          const full = await getWebSearchSession(session_id)
          setSession(full)
          setLoading(false)
        } else if (event.type === 'error') {
          setError((event as SSEErrorEvent).message ?? 'Unknown error')
          setLoading(false)
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start web search')
      setLoading(false)
    }
  }

  function handleFollowUp(question: string) {
    setInput(question)
    setTimeout(() => {
      const form = document.getElementById('ws-form') as HTMLFormElement | null
      form?.requestSubmit()
    }, 50)
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/2 h-80 w-80 -translate-x-1/2 rounded-full bg-cyan-900/10 blur-[100px]" />
        <div className="absolute top-1/3 -right-24 h-72 w-72 rounded-full bg-indigo-900/10 blur-[96px]" />
      </div>

      <div className="relative mx-auto max-w-5xl space-y-8 px-4 py-12">
        <section className="rounded-[28px] border border-slate-800/80 bg-slate-950/35 px-6 py-7 shadow-2xl shadow-black/20 backdrop-blur-sm sm:px-8">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-900/60 bg-cyan-950/35 px-3 py-1.5 text-xs font-medium text-cyan-300">
                <Globe className="h-3.5 w-3.5" />
                Live web answers
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-slate-100 sm:text-4xl">
                  Search the web with citations
                </h1>
                <p className="max-w-xl text-sm leading-7 text-slate-400 sm:text-base">
                  Ask in any language, pull fresh sources, and get a synthesized answer with references you can open immediately.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 text-sm text-slate-500">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-600">Mode</div>
                <div className="mt-1 font-medium text-slate-300">SearXNG + synthesis</div>
              </div>
              <Link
                href="/"
                className="rounded-2xl border border-slate-800 bg-slate-900/50 px-4 py-3 text-slate-400 transition-colors hover:border-slate-700 hover:text-slate-200"
              >
                Back home
              </Link>
            </div>
          </div>
        </section>

        <Card className="border-slate-800/80 bg-slate-900/55">
          <CardContent className="px-6 py-6">
            <form id="ws-form" onSubmit={handleSubmit} className="space-y-5">
              <div className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <Input
                  id="ws-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask anything about a topic, company, person, product, or event..."
                  disabled={loading}
                  className="h-14 rounded-2xl pl-11 pr-4 text-base"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && input.trim() && !loading) {
                      e.preventDefault()
                      handleSubmit(e as unknown as React.FormEvent)
                    }
                  }}
                />
              </div>

              <div className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-950/30 px-4 py-4 sm:flex-row sm:items-end sm:justify-between">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                    Recency
                  </label>
                  <select
                    value={recency}
                    onChange={(e) => setRecency(e.target.value as WebSearchRecency)}
                    disabled={loading}
                    className="min-w-[180px] rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    {RECENCY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  {session && !loading && (
                    <button
                      type="button"
                      onClick={() => {
                        setSession(null)
                        setLogs([])
                        setProgress(0)
                        setInput('')
                      }}
                      className="flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-slate-300"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      New search
                    </button>
                  )}
                  <Button
                    type="submit"
                    disabled={!input.trim() || loading}
                    className="h-11 rounded-xl bg-cyan-700 px-5 hover:bg-cyan-600"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Searching...
                      </>
                    ) : (
                      <>
                        <Globe className="mr-2 h-4 w-4" />
                        Search the web
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>

        {!session && !loading && !error && (
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              'Compare two products with recent reviews',
              "Summarize today's news about a company",
              'Find sources backing a technical claim',
            ].map((example) => (
              <button
                key={example}
                onClick={() => setInput(example)}
                className="rounded-2xl border border-slate-800 bg-slate-900/35 px-4 py-4 text-left text-sm text-slate-400 transition-all duration-200 hover:border-cyan-800/50 hover:bg-cyan-950/10 hover:text-slate-200"
              >
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-600">
                  Example
                </div>
                {example}
              </button>
            ))}
          </div>
        )}

        {loading && (
          <Card className="border-slate-800/80 bg-slate-900/50">
            <CardContent className="px-6 py-6">
              <ResearchProgress logs={logs} percentage={progress} />
            </CardContent>
          </Card>
        )}

        {error && (
          <div className="rounded-2xl border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {session?.result && (
          <WebSearchResultsPanel
            result={session.result}
            userQuestion={lastQuery}
            onFollowUp={handleFollowUp}
          />
        )}
      </div>
    </main>
  )
}
