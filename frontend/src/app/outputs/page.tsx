'use client'

import { useState, useEffect } from 'react'
import { FolderOpen, FileDown, Loader2 } from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { listAllOutputs, getArtifactDownloadUrl } from '@/lib/api'
import type { SessionArtifacts } from '@/lib/types'

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export default function OutputsPage() {
  const [sessions, setSessions] = useState<SessionArtifacts[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)

  useEffect(() => {
    listAllOutputs()
      .then(setSessions)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load outputs'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-4xl px-4 py-12 space-y-8">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-yellow-400">
              <FolderOpen className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Outputs</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Research Artifacts</h1>
          <p className="text-slate-400">
            Download generated files: summaries, paper lists, bibliographies, provenance, and full reports.
          </p>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {!loading && sessions.length === 0 && !error && (
          <p className="text-sm text-slate-500">No artifacts yet. Run a research session first.</p>
        )}

        <div className="space-y-4">
          {sessions.map(s => (
            <Card key={s.session_id} className="border-slate-800 bg-slate-900/50">
              <CardContent className="pt-4 space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-slate-200 line-clamp-2">
                      {s.topic ?? s.session_id}
                    </p>
                    <div className="flex gap-2 mt-1">
                      <span className="text-xs text-slate-500">
                        {s.agent_type}
                      </span>
                      {s.created_at && (
                        <span className="text-xs text-slate-600">
                          · {new Date(s.created_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-slate-500 shrink-0">{s.files.length} files</span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {s.files.map(f => (
                    <a
                      key={f.filename}
                      href={getArtifactDownloadUrl(s.session_id, f.filename)}
                      download
                      className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800/60 px-2.5 py-1.5 text-xs text-slate-300 hover:border-yellow-700/60 hover:text-yellow-300 transition-all"
                    >
                      <FileDown className="h-3 w-3" />
                      {f.filename}
                      <span className="text-slate-600">({formatBytes(f.size_bytes)})</span>
                    </a>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </main>
  )
}
