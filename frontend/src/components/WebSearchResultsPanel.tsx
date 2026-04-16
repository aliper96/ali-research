'use client'

import { useState } from 'react'
import {
  Globe,
  ExternalLink,
  Search,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import type { WebSearchResult, WebSource } from '@/lib/types'

// ---------------------------------------------------------------------------
// QueriesBar
// ---------------------------------------------------------------------------

export function QueriesBar({ queries, userQuestion }: { queries: string[]; userQuestion: string }) {
  const [open, setOpen] = useState(false)
  if (!queries.length) return null

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/55">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-800/40"
      >
        <Globe
          className="h-4 w-4 flex-shrink-0 animate-pulse text-cyan-500"
          style={{ animationDuration: '2s' }}
        />
        <span className="flex-1 truncate text-sm text-slate-300">
          Searching for <span className="italic text-slate-400">"{userQuestion}"</span>
        </span>
        <span className="text-xs text-slate-600">{queries.length} queries</span>
        {open ? (
          <ChevronUp className="h-4 w-4 text-slate-600" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-600" />
        )}
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-800 px-4 py-3">
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
// SourceCard
// ---------------------------------------------------------------------------

export function SourceCard({ source, index }: { source: WebSource; index: number }) {
  const domain =
    source.domain ||
    (() => {
      try {
        return new URL(source.url).hostname.replace('www.', '')
      } catch {
        return ''
      }
    })()

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col gap-1.5 rounded-xl border border-slate-700 bg-slate-800/45 p-3 transition-all duration-200 hover:border-cyan-700/60 hover:bg-cyan-900/10"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-slate-700 text-[10px] font-bold text-slate-300 transition-colors group-hover:bg-cyan-800 group-hover:text-cyan-200">
            {index}
          </span>
          <span className="truncate text-xs text-slate-500">{domain}</span>
        </div>
        <ExternalLink className="h-3 w-3 flex-shrink-0 text-slate-600 transition-colors group-hover:text-cyan-400" />
      </div>
      <p className="line-clamp-2 text-sm font-medium text-slate-200 transition-colors group-hover:text-white">
        {source.title}
      </p>
      {source.snippet && <p className="line-clamp-2 text-xs text-slate-500">{source.snippet}</p>}
      {source.published_date && <p className="text-[10px] text-slate-600">{source.published_date}</p>}
    </a>
  )
}

// ---------------------------------------------------------------------------
// AnswerText
// ---------------------------------------------------------------------------

export function AnswerText({ text }: { text: string }) {
  return (
    <div
      className="prose prose-invert prose-sm max-w-none
      prose-headings:mb-2 prose-headings:mt-4 prose-headings:font-semibold prose-headings:text-slate-100
      prose-h2:text-base prose-h3:text-sm
      prose-p:my-2 prose-p:leading-relaxed prose-p:text-slate-200
      prose-li:my-0.5 prose-li:text-slate-200
      prose-ul:my-2 prose-ol:my-2
      prose-strong:text-white
      prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline
      prose-code:rounded prose-code:bg-slate-800 prose-code:px-1 prose-code:text-xs prose-code:text-cyan-300
      prose-hr:my-4 prose-hr:border-slate-700"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p({ children }) {
            const renderChildren = (node: React.ReactNode): React.ReactNode => {
              if (typeof node === 'string') {
                const parts = node.split(/(\[\d+\])/g)
                return parts.map((part, i) => {
                  const m = part.match(/^\[(\d+)\]$/)
                  return m ? (
                    <sup key={i} className="mx-0.5 text-[11px] font-bold text-cyan-400 not-prose">
                      [{m[1]}]
                    </sup>
                  ) : (
                    part
                  )
                })
              }
              return node
            }
            return <p>{Array.isArray(children) ? children.map(renderChildren) : renderChildren(children)}</p>
          },
          li({ children }) {
            const renderChildren = (node: React.ReactNode): React.ReactNode => {
              if (typeof node === 'string') {
                const parts = node.split(/(\[\d+\])/g)
                return parts.map((part, i) => {
                  const m = part.match(/^\[(\d+)\]$/)
                  return m ? (
                    <sup key={i} className="mx-0.5 text-[11px] font-bold text-cyan-400 not-prose">
                      [{m[1]}]
                    </sup>
                  ) : (
                    part
                  )
                })
              }
              return node
            }
            return <li>{Array.isArray(children) ? children.map(renderChildren) : renderChildren(children)}</li>
          },
          a({ href, children }) {
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            )
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CopyButton
// ---------------------------------------------------------------------------

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
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
      className="flex items-center gap-1.5 rounded-md border border-transparent px-2.5 py-1.5 text-xs text-slate-400 transition-all duration-150 hover:border-slate-600 hover:bg-slate-700/60 hover:text-slate-100"
      title="Copy as markdown"
    >
      {copied ? (
        <>
          <Check className="h-3.5 w-3.5 text-emerald-400" />
          <span className="text-emerald-400">Copied!</span>
        </>
      ) : (
        <>
          <Copy className="h-3.5 w-3.5" />
          <span>Copy</span>
        </>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// WebSearchResultsPanel — main export
// ---------------------------------------------------------------------------

export default function WebSearchResultsPanel({
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
      <QueriesBar queries={result.queries_used} userQuestion={userQuestion} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.8fr)]">
        <Card className="border-slate-700/80 bg-slate-900/65">
          <CardHeader className="border-b border-slate-800/80 px-6 py-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-cyan-900/60 bg-cyan-950/40 text-cyan-400">
                  <Globe className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-400/80">
                    Synthesized answer
                  </p>
                  <h2 className="text-lg font-semibold text-slate-100">Answer</h2>
                </div>
              </div>
              <CopyButton text={result.answer} />
            </div>
          </CardHeader>
          <CardContent className="px-6 py-6">
            <AnswerText text={result.answer} />
          </CardContent>
        </Card>

        <div className="space-y-6">
          {result.sources.length > 0 && (
            <Card className="border-slate-800 bg-slate-900/55">
              <CardHeader className="px-5 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                      Sources
                    </p>
                    <h3 className="mt-1 text-base font-semibold text-slate-100">
                      {result.sources.length} references
                    </h3>
                  </div>
                  <div className="rounded-full border border-slate-700 bg-slate-800/70 px-2.5 py-1 text-[11px] text-slate-400">
                    Ranked
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 px-5 pb-5">
                {result.sources.map((source, i) => (
                  <SourceCard key={source.url} source={source} index={i + 1} />
                ))}
              </CardContent>
            </Card>
          )}

          {result.follow_up_questions.length > 0 && (
            <Card className="border-slate-800 bg-slate-900/55">
              <CardHeader className="px-5 py-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Next steps
                  </p>
                  <h3 className="mt-1 text-base font-semibold text-slate-100">
                    Related questions
                  </h3>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 px-5 pb-5">
                {result.follow_up_questions.map((q, i) => (
                  <button
                    key={i}
                    className="w-full rounded-xl border border-slate-700 bg-slate-800/35 px-4 py-3 text-left text-sm text-slate-300 transition-all duration-200 hover:border-cyan-700/60 hover:bg-cyan-900/10 hover:text-white"
                    onClick={() => onFollowUp(q)}
                  >
                    <Search className="mr-2 inline h-3.5 w-3.5 text-cyan-500" />
                    {q}
                  </button>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
