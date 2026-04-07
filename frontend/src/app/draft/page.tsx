'use client'

import { useState } from 'react'
import { FileText, Loader2, Download } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { createDraft, listSessions, listDeepSessions, listLitSessions } from '@/lib/api'
import type { SessionSummary } from '@/lib/api'
import type { DraftFormat, DraftResult } from '@/lib/types'
import { useEffect } from 'react'

const FORMAT_OPTIONS: { value: DraftFormat; label: string; desc: string }[] = [
  { value: 'brief',  label: 'Executive Brief',  desc: '1-2 pages, key findings + actions' },
  { value: 'paper',  label: 'Academic Paper',   desc: 'Abstract → Introduction → Results → Conclusion' },
  { value: 'blog',   label: 'Blog Post',         desc: 'Accessible, engaging, concrete examples' },
]

const SESSION_TYPES = [
  { value: 'research',     label: 'Research' },
  { value: 'deepresearch', label: 'Deep Research' },
  { value: 'lit',          label: 'Literature Review' },
]

export default function DraftPage() {
  const [sessionId, setSessionId]   = useState('')
  const [sessionType, setType]      = useState('research')
  const [format, setFormat]         = useState<DraftFormat>('brief')
  const [title, setTitle]           = useState('')
  const [loading, setLoading]       = useState(false)
  const [result, setResult]         = useState<DraftResult | null>(null)
  const [error, setError]           = useState<string | null>(null)
  const [sessions, setSessions]     = useState<SessionSummary[]>([])

  // Load completed sessions for the selected type
  useEffect(() => {
    setSessions([])
    setSessionId('')
    const loaders: Record<string, () => Promise<SessionSummary[]>> = {
      research:     () => listSessions(),
      deepresearch: () => listDeepSessions(),
      lit:          () => listLitSessions(),
    }
    const loader = loaders[sessionType]
    if (loader) {
      loader().then(list => setSessions(list.filter(s => s.status === 'completed'))).catch(() => {})
    }
  }, [sessionType])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!sessionId.trim() || loading) return
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await createDraft(sessionId.trim(), sessionType, format, title.trim())
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Draft generation failed')
    } finally {
      setLoading(false)
    }
  }

  function downloadMarkdown() {
    if (!result) return
    const blob = new Blob([result.content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.title.replace(/\s+/g, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-4xl px-4 py-12 space-y-8">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-orange-400">
              <FileText className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Draft Generator</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Generate a Draft</h1>
          <p className="text-slate-400">
            Convert a completed research session into a structured document:
            executive brief, academic paper draft, or blog post.
          </p>
        </div>

        <Card className="border-slate-800 bg-slate-900/50">
          <CardContent className="pt-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Session type */}
              <div className="flex gap-3">
                {SESSION_TYPES.map(t => (
                  <button
                    key={t.value} type="button"
                    onClick={() => setType(t.value)}
                    className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-all ${
                      sessionType === t.value
                        ? 'border-orange-700 bg-orange-900/30 text-orange-300'
                        : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Session picker */}
              <div className="space-y-1">
                <label className="text-xs text-slate-400">Select session</label>
                {sessions.length > 0 ? (
                  <select
                    value={sessionId}
                    onChange={e => setSessionId(e.target.value)}
                    disabled={loading}
                    className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">— choose a session —</option>
                    {sessions.map(s => (
                      <option key={s.session_id} value={s.session_id}>
                        {s.input.slice(0, 80)} ({new Date(s.created_at).toLocaleDateString()})
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    value={sessionId}
                    onChange={e => setSessionId(e.target.value)}
                    placeholder="Paste session ID manually"
                    disabled={loading}
                  />
                )}
              </div>

              {/* Format */}
              <div className="space-y-1">
                <label className="text-xs text-slate-400">Output format</label>
                <div className="grid grid-cols-3 gap-3">
                  {FORMAT_OPTIONS.map(f => (
                    <button
                      key={f.value} type="button"
                      onClick={() => setFormat(f.value)}
                      className={`rounded-lg border p-3 text-left transition-all ${
                        format === f.value
                          ? 'border-orange-700 bg-orange-900/30'
                          : 'border-slate-700 bg-slate-800/50 hover:border-slate-600'
                      }`}
                    >
                      <div className="text-xs font-semibold text-slate-200">{f.label}</div>
                      <div className="text-xs text-slate-500 mt-0.5">{f.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Optional title */}
              <div className="space-y-1">
                <label className="text-xs text-slate-400">Document title (optional)</label>
                <Input
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="Leave empty to auto-generate"
                  disabled={loading}
                />
              </div>

              <Button type="submit" disabled={!sessionId.trim() || loading}
                className="bg-orange-700 hover:bg-orange-600">
                {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                {loading ? 'Generating…' : 'Generate Draft'}
              </Button>
            </form>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-slate-100">{result.title}</h2>
                <p className="text-xs text-slate-500">{result.word_count} words · {result.format}</p>
              </div>
              <Button variant="outline" size="sm" onClick={downloadMarkdown}
                className="border-slate-700 text-slate-300 hover:text-white gap-1.5">
                <Download className="h-3.5 w-3.5" /> Download .md
              </Button>
            </div>
            <Card className="border-slate-800 bg-slate-900/50">
              <CardContent className="pt-4">
                <pre className="whitespace-pre-wrap text-sm text-slate-300 font-mono leading-relaxed max-h-[60vh] overflow-y-auto">
                  {result.content}
                </pre>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </main>
  )
}
