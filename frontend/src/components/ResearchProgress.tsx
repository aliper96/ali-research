'use client'

import React, { useEffect, useRef } from 'react'
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
  Clock,
} from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { cn, formatTimestamp } from '@/lib/utils'
import type { LogEntry, LogLevel } from '@/lib/types'

interface ResearchProgressProps {
  percentage: number
  logs: LogEntry[]
}

const LOG_ICON: Record<LogLevel, React.ReactNode> = {
  info: <Info className="h-3.5 w-3.5 text-slate-400 flex-shrink-0 mt-0.5" />,
  success: <CheckCircle2 className="h-3.5 w-3.5 text-green-400 flex-shrink-0 mt-0.5" />,
  warning: <AlertTriangle className="h-3.5 w-3.5 text-yellow-400 flex-shrink-0 mt-0.5" />,
  error: <XCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0 mt-0.5" />,
}

const LOG_TEXT_COLOR: Record<LogLevel, string> = {
  info: 'text-slate-300',
  success: 'text-green-300',
  warning: 'text-yellow-300',
  error: 'text-red-300',
}

const LOG_BG: Record<LogLevel, string> = {
  info: '',
  success: 'bg-green-900/10',
  warning: 'bg-yellow-900/10',
  error: 'bg-red-900/10',
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-2 text-slate-500 text-sm">
      <div className="dot-pulse flex items-center gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 inline-block" />
        <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 inline-block" />
        <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 inline-block" />
      </div>
      <span>Researching...</span>
    </div>
  )
}

export default function ResearchProgress({ percentage, logs }: ResearchProgressProps) {
  const logEndRef = useRef<HTMLDivElement>(null)
  const logContainerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom as logs arrive
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [logs.length])

  return (
    <div className="w-full space-y-6 animate-fade-in">
      {/* Progress header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-indigo-400 animate-pulse" />
            <span className="text-sm font-medium text-slate-300">Research in progress</span>
          </div>
          <span className="font-mono text-sm font-semibold text-indigo-400">
            {percentage}%
          </span>
        </div>

        <Progress value={percentage} max={100} className="h-2" />

        <ThinkingDots />
      </div>

      {/* Log feed */}
      <div
        ref={logContainerRef}
        className="h-80 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/50 p-1"
      >
        {logs.length === 0 ? (
          <div className="flex h-full items-center justify-center text-slate-600 text-sm">
            Waiting for logs...
          </div>
        ) : (
          <div className="space-y-0.5 p-1">
            {logs.map((log, idx) => (
              <div
                key={idx}
                className={cn(
                  'flex items-start gap-2.5 rounded px-2.5 py-1.5 text-xs leading-relaxed',
                  LOG_BG[log.level],
                  idx === logs.length - 1 && 'ring-1 ring-indigo-500/20 bg-indigo-950/20'
                )}
              >
                {LOG_ICON[log.level]}
                <span
                  className={cn(
                    'font-mono text-slate-600 flex-shrink-0 select-none',
                    'text-[10px] pt-0.5'
                  )}
                >
                  {formatTimestamp(log.timestamp)}
                </span>
                <span className={cn('flex-1', LOG_TEXT_COLOR[log.level])}>
                  {log.message}
                </span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 text-xs text-slate-500">
        <span>{logs.length} log entries</span>
        <span>•</span>
        <span>
          {logs.filter((l) => l.level === 'success').length} completed steps
        </span>
        {logs.some((l) => l.level === 'warning') && (
          <>
            <span>•</span>
            <span className="text-yellow-500">
              {logs.filter((l) => l.level === 'warning').length} warnings
            </span>
          </>
        )}
      </div>
    </div>
  )
}
