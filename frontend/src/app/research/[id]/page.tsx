'use client'

import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import ResearchProgress from '@/components/ResearchProgress'
import ResearchReport from '@/components/ResearchReport'
import { getSession, streamSession } from '@/lib/api'
import { cn, formatTimestamp } from '@/lib/utils'
import type { LogEntry, SessionStatus, SSEEvent } from '@/lib/types'

interface ResearchPageProps {
  params: { id: string }
}

const STATUS_CONFIG: Record<
  SessionStatus,
  { label: string; icon: React.ReactNode; badgeClass: string }
> = {
  running: {
    label: 'Running',
    icon: <Clock className="h-3 w-3 animate-pulse" />,
    badgeClass: 'bg-blue-900/50 text-blue-300 border border-blue-800/50',
  },
  completed: {
    label: 'Completed',
    icon: <CheckCircle2 className="h-3 w-3" />,
    badgeClass: 'bg-green-900/50 text-green-300 border border-green-800/50',
  },
  error: {
    label: 'Error',
    icon: <XCircle className="h-3 w-3" />,
    badgeClass: 'bg-red-900/50 text-red-300 border border-red-800/50',
  },
}

export default function ResearchPage({ params }: ResearchPageProps) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const sessionId = params.id

  const [streamLogs, setStreamLogs] = useState<LogEntry[]>([])
  const [streamPercentage, setStreamPercentage] = useState(0)
  const [streamError, setStreamError] = useState<string | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  const { data: session, isLoading, isError, refetch } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => getSession(sessionId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      // Stop polling when done
      if (status === 'completed' || status === 'error') return false
      return 5000
    },
    retry: 3,
  })

  const handleSSEEvent = useCallback(
    (event: SSEEvent) => {
      if (event.type === 'log') {
        setStreamLogs((prev) => [...prev, event.log])
        setStreamPercentage(event.percentage)
      } else if (event.type === 'complete') {
        // Invalidate to get final result
        void queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
        cleanupRef.current?.()
        cleanupRef.current = null
      } else if (event.type === 'error') {
        setStreamError(event.message)
        void queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
        cleanupRef.current?.()
        cleanupRef.current = null
      }
    },
    [queryClient, sessionId]
  )

  // Subscribe to SSE stream when session is running
  useEffect(() => {
    if (session?.status === 'running' && !cleanupRef.current) {
      // Seed logs from existing session data
      if (session.progress.logs.length > 0 && streamLogs.length === 0) {
        setStreamLogs(session.progress.logs)
        setStreamPercentage(session.progress.percentage)
      }

      const cleanup = streamSession(sessionId, handleSSEEvent)
      cleanupRef.current = cleanup
    }

    return () => {
      if (session?.status !== 'running') {
        cleanupRef.current?.()
        cleanupRef.current = null
      }
    }
  }, [session?.status, sessionId, handleSSEEvent])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupRef.current?.()
    }
  }, [])

  const displayLogs =
    streamLogs.length > 0 ? streamLogs : session?.progress.logs ?? []
  const displayPercentage =
    streamPercentage > 0 ? streamPercentage : session?.progress.percentage ?? 0

  return (
    <div className="min-h-screen bg-[#0a0f1e]">
      {/* Background decorations */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 h-80 w-80 rounded-full bg-indigo-900/5 blur-3xl" />
        <div className="absolute bottom-0 -left-40 h-80 w-80 rounded-full bg-purple-900/5 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-4xl px-4 py-8">
        {/* Header */}
        <div className="mb-8 flex items-start gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.push('/')}
            className="mt-0.5 flex-shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="text-xs font-mono text-slate-600 uppercase tracking-wider">
                Session
              </span>
              <code className="text-xs font-mono text-slate-500 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">
                {sessionId}
              </code>

              {session && (
                <div
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
                    STATUS_CONFIG[session.status].badgeClass
                  )}
                >
                  {STATUS_CONFIG[session.status].icon}
                  {STATUS_CONFIG[session.status].label}
                </div>
              )}
            </div>

            {session && (
              <h1 className="text-xl font-semibold text-slate-100 leading-snug">
                {session.input}
              </h1>
            )}

            {session && (
              <p className="text-xs text-slate-600 mt-1 font-mono">
                Started {formatTimestamp(session.created_at)}
              </p>
            )}
          </div>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-32">
            <div className="flex flex-col items-center gap-4">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-indigo-500" />
              <p className="text-sm text-slate-500">Loading session...</p>
            </div>
          </div>
        )}

        {/* Error loading session */}
        {isError && !session && (
          <div className="rounded-lg border border-red-800/50 bg-red-900/20 p-8 text-center">
            <XCircle className="mx-auto h-12 w-12 text-red-400 mb-4 opacity-60" />
            <h2 className="text-lg font-semibold text-red-300 mb-2">
              Failed to load session
            </h2>
            <p className="text-sm text-red-400/70 mb-6">
              Could not retrieve research session {sessionId}
            </p>
            <div className="flex items-center justify-center gap-3">
              <Button variant="outline" onClick={() => void refetch()}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Retry
              </Button>
              <Button variant="ghost" onClick={() => router.push('/')}>
                Back to home
              </Button>
            </div>
          </div>
        )}

        {/* Running state */}
        {session?.status === 'running' && (
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-6">
            <ResearchProgress
              percentage={displayPercentage}
              logs={displayLogs}
            />
          </div>
        )}

        {/* Stream error while running */}
        {streamError && session?.status === 'running' && (
          <div className="mt-4 rounded-lg border border-yellow-800/50 bg-yellow-900/20 px-4 py-3 text-sm text-yellow-300">
            Stream warning: {streamError} — polling for updates instead.
          </div>
        )}

        {/* Session error state */}
        {session?.status === 'error' && (
          <div className="rounded-lg border border-red-800/50 bg-red-900/20 p-8 text-center">
            <XCircle className="mx-auto h-12 w-12 text-red-400 mb-4 opacity-60" />
            <h2 className="text-lg font-semibold text-red-300 mb-2">
              Research failed
            </h2>
            <p className="text-sm text-red-400/70 mb-2">
              An error occurred during the research process.
            </p>
            {displayLogs.length > 0 && (
              <p className="text-xs text-red-400/50 font-mono mb-6">
                Last log: {displayLogs[displayLogs.length - 1]?.message}
              </p>
            )}
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="outline"
                onClick={() => router.push('/')}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Try again
              </Button>
              <Button
                variant="ghost"
                onClick={() => void refetch()}
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh
              </Button>
            </div>
          </div>
        )}

        {/* Completed state with results */}
        {session?.status === 'completed' && session.result && (
          <ResearchReport
            result={session.result}
            sessionId={sessionId}
            topic={session.input}
          />
        )}

        {/* Completed but no result (edge case) */}
        {session?.status === 'completed' && !session.result && (
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-8 text-center">
            <CheckCircle2 className="mx-auto h-12 w-12 text-green-400 mb-4 opacity-60" />
            <h2 className="text-lg font-semibold text-slate-200 mb-2">
              Research completed
            </h2>
            <p className="text-sm text-slate-400 mb-6">
              The session completed but no results are available.
            </p>
            <Button variant="outline" onClick={() => void refetch()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
