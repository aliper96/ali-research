'use client'

import { useState, useEffect, useCallback } from 'react'
import { Brain, Search, Loader2 } from 'lucide-react'
import Link from 'next/link'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { searchKnowledge, getKnowledgeStats } from '@/lib/api'
import type { KnowledgePaper, KnowledgeStats } from '@/lib/types'

export default function KnowledgePage() {
  const [query, setQuery]       = useState('')
  const [papers, setPapers]     = useState<KnowledgePaper[]>([])
  const [stats, setStats]       = useState<KnowledgeStats | null>(null)
  const [loading, setLoading]   = useState(false)
  const [statsLoading, setStatsLoading] = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [searched, setSearched] = useState(false)

  useEffect(() => {
    getKnowledgeStats()
      .then(setStats)
      .catch(() => {})
      .finally(() => setStatsLoading(false))
  }, [])

  const handleSearch = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!query.trim() || loading) return
    setLoading(true); setError(null); setSearched(true)
    try {
      const results = await searchKnowledge(query.trim())
      setPapers(results)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setLoading(false)
    }
  }, [query, loading])

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-4xl px-4 py-12 space-y-8">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-teal-400">
              <Brain className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Knowledge Base</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Cross-Session Knowledge</h1>
          <p className="text-slate-400">
            Full-text search across all papers discovered in past research sessions.
          </p>
        </div>

        {/* Stats row */}
        {!statsLoading && stats && (
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Total Papers" value={stats.total_papers.toLocaleString()} />
            <StatCard label="Sessions" value={stats.total_sessions.toLocaleString()} />
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
              <p className="text-xs text-slate-500 mb-2">Top tags</p>
              <div className="flex flex-wrap gap-1">
                {stats.top_tags.slice(0, 6).map(t => (
                  <button
                    key={t.tag}
                    onClick={() => { setQuery(t.tag); }}
                    className="text-xs rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-slate-400 hover:border-teal-700 hover:text-teal-300 transition-all"
                  >
                    {t.tag} <span className="text-slate-600">×{t.count}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Search */}
        <Card className="border-slate-800 bg-slate-900/50">
          <CardContent className="pt-6">
            <form onSubmit={handleSearch} className="flex gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                <Input
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="Search papers by title, abstract, or concept…"
                  className="pl-9"
                  disabled={loading}
                />
              </div>
              <Button type="submit" disabled={!query.trim() || loading}
                className="bg-teal-700 hover:bg-teal-600">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
              </Button>
            </form>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {searched && !loading && papers.length === 0 && !error && (
          <p className="text-sm text-slate-500">No papers found for &quot;{query}&quot;</p>
        )}

        {/* Results */}
        {papers.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">{papers.length} papers found</p>
            {papers.map((p, i) => (
              <KnowledgePaperCard key={i} paper={p} />
            ))}
          </div>
        )}

        {/* Recent papers when no search */}
        {!searched && stats?.recent_papers && stats.recent_papers.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Recently Added</h2>
            {stats.recent_papers.slice(0, 5).map((p, i) => (
              <KnowledgePaperCard key={i} paper={p} />
            ))}
          </div>
        )}
      </div>
    </main>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-2xl font-bold text-teal-300 mt-1">{value}</p>
    </div>
  )
}

function KnowledgePaperCard({ paper }: { paper: KnowledgePaper }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <Card className="border-slate-800 bg-slate-900/50">
      <CardContent className="pt-4 space-y-2">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            {paper.url ? (
              <a href={paper.url} target="_blank" rel="noopener noreferrer"
                className="text-sm font-medium text-slate-200 hover:text-teal-300 transition-colors line-clamp-2">
                {paper.title}
              </a>
            ) : (
              <p className="text-sm font-medium text-slate-200 line-clamp-2">{paper.title}</p>
            )}
            <p className="text-xs text-slate-500 mt-0.5">
              {paper.authors.slice(0, 3).join(', ')}{paper.authors.length > 3 ? ' et al.' : ''}
              {paper.year ? ` · ${paper.year}` : ''}
              {paper.citation_count > 0 ? ` · ${paper.citation_count} citations` : ''}
            </p>
          </div>
          {paper.arxiv_id && (
            <span className="shrink-0 text-xs text-violet-400 font-mono">arXiv:{paper.arxiv_id}</span>
          )}
        </div>

        {paper.abstract && (
          <>
            <p className={`text-xs text-slate-400 leading-relaxed ${expanded ? '' : 'line-clamp-2'}`}>
              {paper.abstract}
            </p>
            {paper.abstract.length > 200 && (
              <button onClick={() => setExpanded(e => !e)}
                className="text-xs text-teal-500 hover:text-teal-300">
                {expanded ? 'Show less' : 'Show more'}
              </button>
            )}
          </>
        )}

        {paper.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {paper.tags.map(tag => (
              <span key={tag} className="text-xs rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-slate-500">
                {tag}
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
