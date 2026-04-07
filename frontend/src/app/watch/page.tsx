'use client'

import { useState, useEffect, useCallback } from 'react'
import { Bell, Plus, Trash2, Play, Clock, CheckCircle2, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select } from '@/components/ui/select'
import { createWatch, listWatches, deleteWatch, runWatchNow } from '@/lib/api'
import type { Watch } from '@/lib/api'

const SCHEDULE_OPTIONS = [
  { label: 'Every day',    value: 24  },
  { label: 'Every 3 days', value: 72  },
  { label: 'Weekly',       value: 168 },
  { label: 'Bi-weekly',    value: 336 },
]

function WatchCard({ watch, onDelete, onRunNow }: {
  watch: Watch
  onDelete: (id: string) => void
  onRunNow:  (id: string) => void
}) {
  const scheduleLabel = SCHEDULE_OPTIONS.find(o => o.value === watch.schedule_hours)?.label
    ?? `Every ${watch.schedule_hours}h`

  return (
    <Card className="border-slate-800 bg-slate-900/50">
      <CardContent className="pt-4 pb-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-200 truncate">{watch.query}</p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
              <span className="text-[11px] text-slate-500">{scheduleLabel}</span>
              <span className="text-[11px] text-slate-500">depth: {watch.depth}</span>
              {watch.last_run_at && (
                <span className="text-[11px] text-slate-500">
                  last run: {new Date(watch.last_run_at).toLocaleDateString()}
                </span>
              )}
              {watch.next_run_at && (
                <span className="text-[11px] text-indigo-400">
                  next: {new Date(watch.next_run_at).toLocaleDateString()}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Button variant="outline" size="sm" onClick={() => onRunNow(watch.watch_id)}
                    className="h-7 text-xs px-2">
              <Play className="h-3 w-3 mr-1" /> Run now
            </Button>
            <Button variant="outline" size="sm" onClick={() => onDelete(watch.watch_id)}
                    className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:border-red-700">
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </div>

        {watch.last_result && (
          <div className="rounded-md border border-slate-800 bg-slate-950/50 p-3 space-y-1.5">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span>{watch.last_result.paper_count} papers found</span>
            </div>
            {watch.last_result.top_papers.length > 0 && (
              <ul className="space-y-0.5 pl-5">
                {watch.last_result.top_papers.map((title, i) => (
                  <li key={i} className="text-[11px] text-slate-400 truncate">• {title}</li>
                ))}
              </ul>
            )}
            {watch.last_result.summary && (
              <p className="text-[11px] text-slate-500 leading-relaxed line-clamp-2">
                {watch.last_result.summary}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function WatchPage() {
  const [watches, setWatches]         = useState<Watch[]>([])
  const [query, setQuery]             = useState('')
  const [depth, setDepth]             = useState('quick')
  const [scheduleHours, setSchedule]  = useState(168)
  const [creating, setCreating]       = useState(false)
  const [runningIds, setRunningIds]   = useState<Set<string>>(new Set())
  const [error, setError]             = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      setWatches(await listWatches())
    } catch {}
  }, [])

  useEffect(() => { reload() }, [reload])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim() || creating) return
    setCreating(true)
    setError(null)
    try {
      const w = await createWatch(query.trim(), depth, scheduleHours)
      setWatches(prev => [w, ...prev])
      setQuery('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create watch')
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteWatch(id)
      setWatches(prev => prev.filter(w => w.watch_id !== id))
    } catch {}
  }

  async function handleRunNow(id: string) {
    setRunningIds(prev => new Set(prev).add(id))
    try {
      await runWatchNow(id)
      setTimeout(() => {
        setRunningIds(prev => { const s = new Set(prev); s.delete(id); return s })
        reload()
      }, 3000)
    } catch {
      setRunningIds(prev => { const s = new Set(prev); s.delete(id); return s })
    }
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-3xl px-4 py-12 space-y-8">
        {/* Header */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-indigo-400">
            <Bell className="h-5 w-5" />
            <span className="text-sm font-semibold uppercase tracking-wider">Research Watches</span>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Topic Monitor</h1>
          <p className="text-slate-400">
            Set up recurring research runs on topics or queries. The system will automatically
            re-run them on schedule and surface new papers.
          </p>
        </div>

        {/* Create form */}
        <Card className="border-slate-800 bg-slate-900/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold text-slate-300">New Watch</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-3">
              <Input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="e.g. diffusion models for protein design"
                disabled={creating}
              />
              <div className="flex gap-3">
                <Select
                  value={depth}
                  onChange={e => setDepth(e.target.value)}
                  className="w-36"
                >
                  <option value="quick">Quick</option>
                  <option value="standard">Standard</option>
                  <option value="deep">Deep</option>
                </Select>
                <Select
                  value={String(scheduleHours)}
                  onChange={e => setSchedule(Number(e.target.value))}
                  className="flex-1"
                >
                  {SCHEDULE_OPTIONS.map(o => (
                    <option key={o.value} value={String(o.value)}>{o.label}</option>
                  ))}
                </Select>
                <Button type="submit" disabled={!query.trim() || creating} className="flex-shrink-0">
                  <Plus className="h-4 w-4 mr-1" />
                  {creating ? 'Creating…' : 'Create'}
                </Button>
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
            </form>
          </CardContent>
        </Card>

        {/* Watch list */}
        {watches.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-600 space-y-2">
            <Clock className="h-10 w-10 opacity-30" />
            <p className="text-sm">No watches yet — create one above.</p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">{watches.length} active watch{watches.length !== 1 ? 'es' : ''}</p>
            {watches.map(w => (
              <WatchCard
                key={w.watch_id}
                watch={w}
                onDelete={handleDelete}
                onRunNow={handleRunNow}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  )
}
