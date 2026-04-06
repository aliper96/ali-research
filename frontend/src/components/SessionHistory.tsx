'use client'

import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import { Clock, CheckCircle2, XCircle, Loader2, ChevronRight, History } from 'lucide-react'
import { listSessions, type SessionSummary } from '@/lib/api'
import { cn } from '@/lib/utils'

function StatusIcon({ status }: { status: SessionSummary['status'] }) {
  if (status === 'completed') return <CheckCircle2 className="h-3.5 w-3.5 text-green-400 flex-shrink-0" />
  if (status === 'error')     return <XCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
  return <Loader2 className="h-3.5 w-3.5 text-indigo-400 flex-shrink-0 animate-spin" />
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1)   return 'just now'
  if (m < 60)  return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24)  return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function SessionHistory() {
  const router = useRouter()

  const { data: sessions = [], isLoading } = useQuery<SessionSummary[]>({
    queryKey: ['sessions'],
    queryFn: () => listSessions(10),
    refetchInterval: 15_000,
    staleTime: 10_000,
  })

  if (isLoading || sessions.length === 0) return null

  return (
    <div className="w-full max-w-2xl mt-10 space-y-3">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <History className="h-3.5 w-3.5" />
        <span className="font-medium uppercase tracking-wider">Recent Sessions</span>
      </div>

      <div className="space-y-1.5">
        {sessions.map((s) => (
          <button
            key={s.session_id}
            onClick={() => s.has_result && router.push(`/research/${s.session_id}`)}
            disabled={!s.has_result}
            className={cn(
              'group w-full flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-left transition-all duration-150',
              s.has_result
                ? 'hover:border-slate-700 hover:bg-slate-900/80 cursor-pointer'
                : 'opacity-60 cursor-default'
            )}
          >
            <StatusIcon status={s.status} />

            <span className="flex-1 truncate text-sm text-slate-300 group-hover:text-slate-100 transition-colors">
              {s.input}
            </span>

            <span className="flex-shrink-0 text-[11px] text-slate-600 tabular-nums">
              {timeAgo(s.created_at)}
            </span>

            {s.has_result && (
              <ChevronRight className="h-3.5 w-3.5 text-slate-600 flex-shrink-0 group-hover:text-slate-400 transition-colors" />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
