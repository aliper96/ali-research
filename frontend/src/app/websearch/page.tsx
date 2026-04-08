'use client'

import { useState } from 'react'
import { Globe, Loader2, ExternalLink, Search, RefreshCw, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react'
import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import ResearchProgress from '@/components/ResearchProgress'
import { startWebSearch, streamWebSearchSession, getWebSearchSession } from '@/lib/api'
import type {
  WebSearchSession, WebSearchResult, WebSource,
  LogEntry, SSEProgressEvent, SSEErrorEvent, WebSearchRecency,
} from '@/lib/types'

const RECENCY_OPTIONS: { value: WebSearchRecency; label: string }[] = [
  { value: 'any',   label: 'Any time' },
  { value: 'day',   label: 'Past 24h' },
  { value: 'week',  label: 'Past week' },
  { value: 'month', label: 'Past month' },
]

// ---------------------------------------------------------------------------
// Queries "thinking" bar — like Perplexity's "Reuniendo..." dropdown
// ---------------------------------------------------------------------------
function QueriesBar({ queries, userQuestion }: { queries: string[]; userQuestion: string }) {
  const [open, setOpen] = useState(false)
  if (!queries.length) return null
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-800/40 transition-colors"
      >
        <Globe className="h-4 w-4 flex-shrink-0 text-cyan-500 animate-pulse" style={{ animationDuration: '2s' }} />
        <span className="flex-1 text-sm text-slate-300 truncate">
          Searching for <span className="text-slate-400 italic">"{userQuestion}"</span>
        </span>
        <span className="text-xs text-slate-600">{queries.length} queries</span>
        {open
          ? <ChevronUp className="h-4 w-4 text-slate-600" />
          : <ChevronDown className="h-4 w-4 text-slate-600" />
        }
      </button>
      {open && (
        <div className="border-t border-slate-800 px-4 py-3 space-y-2">
          {queries.map((q, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-slate-400">
              <Search className="h-3.5 w-3.5 flex-shrink-0 text-slate-600" />
              {q}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Source card
// ---------------------------------------------------------------------------
function SourceCard({ source, index }: { source: WebSource; index: number }) {
  const domain = source.domain || (() => {
    try { return new URL(source.url).hostname.replace('www.', '') } catch { return '' }
  })()

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col gap-1.5 rounded-lg border border-slate-700 bg-slate-800/50 p-3
                 hover:border-cyan-700/60 hover:bg-cyan-900/10 transition-all duration-200"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex-shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full
                           bg-slate-700 text-[10px] font-bold text-slate-300
                           group-hover:bg-cyan-800 group-hover:text-cyan-200 transition-colors">
            {index}
          </span>
          <span className="text-xs text-slate-500 truncate">{domain}</span>
        </div>
        <ExternalLink className="h-3 w-3 flex-shrink-0 text-slate-600 group-hover:text-cyan-400 transition-colors" />
      </div>
      <p className="text-sm font-medium text-slate-200 line-clamp-2 group-hover:text-white transition-colors">
        {source.title}
      </p>
      {source.snippet && (
        <p className="text-xs text-slate-500 line-clamp-2">{source.snippet}</p>
      )}
      {source.published_date && (
        <p className="text-[10px] text-slate-600">{source.published_date}</p>
      )}
    </a>
  )
}

// ---------------------------------------------------------------------------
// Answer — renders markdown + [N] citation superscripts
// ---------------------------------------------------------------------------
function AnswerText({ text }: { text: string }) {
  // Pre-process: protect [N] citations so markdown doesn't eat them
  return (
    <div className="prose prose-invert prose-sm max-w-none
      prose-headings:text-slate-100 prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
      prose-h2:text-base prose-h3:text-sm
      prose-p:text-slate-200 prose-p:leading-relaxed prose-p:my-2
      prose-li:text-slate-200 prose-li:my-0.5
      prose-ul:my-2 prose-ol:my-2
      prose-strong:text-white
      prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline
      prose-code:text-cyan-300 prose-code:bg-slate-800 prose-code:px-1 prose-code:rounded prose-code:text-xs
      prose-hr:border-slate-700 prose-hr:my-4">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p({ children }) {
            // Render inline [N] as cyan superscripts
            const renderChildren = (node: React.ReactNode): React.ReactNode => {
              if (typeof node === 'string') {
                const parts = node.split(/(\[\d+\])/g)
                return parts.map((part, i) => {
                  const m = part.match(/^\[(\d+)\]$/)
                  return m
                    ? <sup key={i} className="text-cyan-400 font-bold text-[11px] mx-0.5 not-prose">[{m[1]}]</sup>
                    : part
                })
              }
              return node
            }
            return (
              <p>{Array.isArray(children) ? children.map(renderChildren) : renderChildren(children)}</p>
            )
          },
          li({ children }) {
            const renderChildren = (node: React.ReactNode): React.ReactNode => {
              if (typeof node === 'string') {
                const parts = node.split(/(\[\d+\])/g)
                return parts.map((part, i) => {
                  const m = part.match(/^\[(\d+)\]$/)
                  return m
                    ? <sup key={i} className="text-cyan-400 font-bold text-[11px] mx-0.5 not-prose">[{m[1]}]</sup>
                    : part
                })
              }
              return node
            }
            return (
              <li>{Array.isArray(children) ? children.map(renderChildren) : renderChildren(children)}</li>
            )
          },
          a({ href, children }) {
            return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Copy button — copies raw markdown to clipboard
// ---------------------------------------------------------------------------
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback for older browsers
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs
                 text-slate-400 hover:text-slate-100 hover:bg-slate-700/60
                 border border-transparent hover:border-slate-600
                 transition-all duration-150"
      title="Copy as markdown"
    >
      {copied
        ? <><Check className="h-3.5 w-3.5 text-emerald-400" /><span className="text-emerald-400">Copied!</span></>
        : <><Copy className="h-3.5 w-3.5" /><span>Copy</span></>
      }
    </button>
  )
}

// ---------------------------------------------------------------------------
// Full results view
// ---------------------------------------------------------------------------
function WebSearchResults({
  result,
  userQuestion,
  onFollowUp,
}: {
  result: WebSearchResult
  userQuestion: string
  onFollowUp: (q: string) => void
}) {
  return (
    <div className="space-y-6">

      {/* Queries used — Perplexity-style expandable bar */}
      <QueriesBar queries={result.queries_used} userQuestion={userQuestion} />

      {/* Sources grid */}
      {result.sources.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
            Sources ({result.sources.length})
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {result.sources.map((source, i) => (
              <SourceCard key={source.url} source={source} index={i + 1} />
            ))}
          </div>
        </div>
      )}

      {/* Answer */}
      <Card className="border-slate-700 bg-slate-900/60">
        <CardHeader className="pb-2 pt-4 px-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-cyan-400">
              <Globe className="h-4 w-4" />
              <span className="text-sm font-semibold">Answer</span>
            </div>
            <CopyButton text={result.answer} />
          </div>
        </CardHeader>
        <CardContent className="px-5 pb-5">
          <AnswerText text={result.answer} />
        </CardContent>
      </Card>

      {/* Follow-up questions */}
      {result.follow_up_questions.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
            Related questions
          </h3>
          <div className="space-y-2">
            {result.follow_up_questions.map((q, i) => (
              <button
                key={i}
                className="w-full text-left rounded-lg border border-slate-700 bg-slate-800/30 px-4 py-2.5
                           text-sm text-slate-300 hover:border-cyan-700/60 hover:bg-cyan-900/10 hover:text-white
                           transition-all duration-200"
                onClick={() => onFollowUp(q)}
              >
                <Search className="inline h-3.5 w-3.5 mr-2 text-cyan-500" />
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function WebSearchPage() {
  const [input, setInput]       = useState('')
  const [recency, setRecency]   = useState<WebSearchRecency>('any')
  const [loading, setLoading]   = useState(false)
  const [session, setSession]   = useState<WebSearchSession | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [logs, setLogs]         = useState<LogEntry[]>([])
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
          setLogs(prev => [...prev, ev.log])
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
    // Auto-submit
    setTimeout(() => {
      const form = document.getElementById('ws-form') as HTMLFormElement
      form?.requestSubmit()
    }, 50)
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-4xl px-4 py-12 space-y-8">

        {/* Header */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-cyan-400">
              <Globe className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Web Search</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Web Search</h1>
          <p className="text-slate-400">
            Ask in any language — searches the web and synthesizes a cited answer.
          </p>
        </div>

        {/* Search form */}
        <Card className="border-slate-800 bg-slate-900/50">
          <CardContent className="pt-6">
            <form id="ws-form" onSubmit={handleSubmit} className="space-y-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
                <Input
                  id="ws-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="Ask anything…"
                  disabled={loading}
                  className="pl-10 pr-4 py-3 text-base"
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey && input.trim() && !loading) {
                      e.preventDefault()
                      handleSubmit(e as any)
                    }
                  }}
                />
              </div>
              <div className="flex gap-3 items-center">
                <div className="space-y-1">
                  <label className="text-xs text-slate-400">Recency</label>
                  <select
                    value={recency}
                    onChange={e => setRecency(e.target.value as WebSearchRecency)}
                    disabled={loading}
                    className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200
                               focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    {RECENCY_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <Button
                  type="submit"
                  disabled={!input.trim() || loading}
                  className="mt-5 bg-cyan-700 hover:bg-cyan-600 gap-2"
                >
                  {loading
                    ? <><Loader2 className="h-4 w-4 animate-spin" /> Searching…</>
                    : <><Globe className="h-4 w-4" /> Search</>
                  }
                </Button>
                {session && !loading && (
                  <button
                    type="button"
                    onClick={() => { setSession(null); setLogs([]); setProgress(0); setInput('') }}
                    className="mt-5 text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1 transition-colors"
                  >
                    <RefreshCw className="h-3 w-3" /> New search
                  </button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Progress */}
        {loading && <ResearchProgress logs={logs} percentage={progress} status="running" />}

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Results */}
        {session?.result && (
          <WebSearchResults
            result={session.result}
            userQuestion={lastQuery}
            onFollowUp={handleFollowUp}
          />
        )}
      </div>
    </main>
  )
}
