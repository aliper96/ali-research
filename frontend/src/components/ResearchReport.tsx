'use client'

import React, { useState } from 'react'
import {
  BookOpen,
  Table2,
  Network,
  AlertTriangle,
  Map,
  CheckCircle2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import PapersTable from '@/components/PapersTable'
import CitationNetwork from '@/components/CitationNetwork'
import type { ResearchResult, Difficulty } from '@/lib/types'

interface ResearchReportProps {
  result: ResearchResult
  sessionId: string
}

type TabId = 'overview' | 'papers' | 'network' | 'gaps' | 'roadmap'

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <BookOpen className="h-4 w-4" /> },
  { id: 'papers', label: 'Papers', icon: <Table2 className="h-4 w-4" /> },
  { id: 'network', label: 'Network', icon: <Network className="h-4 w-4" /> },
  { id: 'gaps', label: 'Gaps', icon: <AlertTriangle className="h-4 w-4" /> },
  { id: 'roadmap', label: 'Roadmap', icon: <Map className="h-4 w-4" /> },
]

const DIFFICULTY_VARIANT: Record<Difficulty, 'easy' | 'medium' | 'hard'> = {
  easy: 'easy',
  medium: 'medium',
  hard: 'hard',
}

const DIFFICULTY_COLORS: Record<Difficulty, string> = {
  easy: 'border-l-green-500',
  medium: 'border-l-yellow-500',
  hard: 'border-l-red-500',
}

function OverviewTab({ result }: { result: ResearchResult }) {
  return (
    <div className="space-y-8 animate-fade-in">
      {/* Summary */}
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-4">
          Research Summary
        </h3>
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-5">
          <p className="text-sm text-slate-300 leading-7 whitespace-pre-wrap">
            {result.summary}
          </p>
        </div>
      </div>

      {/* Key Concepts */}
      {result.key_concepts.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-4">
            Key Concepts
          </h3>
          <div className="flex flex-wrap gap-2">
            {result.key_concepts.map((concept, idx) => (
              <Badge
                key={idx}
                variant="default"
                className="text-xs py-1 px-3"
              >
                {concept}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Papers', value: result.papers.length },
          { label: 'Gaps Identified', value: result.gap_analysis.length },
          {
            label: 'Roadmap Steps',
            value: result.implementation_roadmap.length,
          },
          {
            label: 'Key Concepts',
            value: result.key_concepts.length,
          },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 text-center"
          >
            <div className="text-2xl font-bold text-indigo-400">{stat.value}</div>
            <div className="text-xs text-slate-500 mt-1">{stat.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function GapsTab({ gaps }: { gaps: string[] }) {
  if (gaps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <CheckCircle2 className="h-12 w-12 mb-3 opacity-30 text-green-500" />
        <p className="text-sm">No gaps identified</p>
      </div>
    )
  }

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
            Research Gaps
          </h3>
          <p className="mt-1 text-xs text-slate-600">
            Open problems and unexplored directions identified in the literature
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-amber-800/40 bg-amber-950/30 px-3 py-1.5">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
          <span className="text-xs font-semibold text-amber-300">{gaps.length} gap{gaps.length !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Gap cards */}
      <div className="space-y-3">
        {gaps.map((gap, idx) => (
          <div
            key={idx}
            className="group relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition-all duration-200 hover:border-amber-800/40 hover:bg-slate-900/90"
          >
            {/* Left accent bar */}
            <div className="absolute inset-y-0 left-0 w-0.5 bg-gradient-to-b from-amber-500/60 via-amber-400/30 to-transparent" />

            <div className="flex items-start gap-4">
              {/* Index */}
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-amber-800/40 bg-amber-950/40 text-xs font-bold tabular-nums text-amber-400">
                {String(idx + 1).padStart(2, '0')}
              </div>

              {/* Text */}
              <p className="flex-1 text-sm leading-relaxed text-slate-300 group-hover:text-slate-200 transition-colors">
                {gap}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RoadmapTab({ steps }: { steps: ResearchResult['implementation_roadmap'] }) {
  if (steps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <Map className="h-12 w-12 mb-3 opacity-30" />
        <p className="text-sm">No roadmap available</p>
      </div>
    )
  }

  return (
    <div className="space-y-0 animate-fade-in">
      <p className="text-sm text-slate-400 mb-6">
        Implementation roadmap with suggested steps and difficulty levels:
      </p>
      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-[19px] top-0 bottom-0 w-0.5 bg-slate-800" />

        <div className="space-y-4">
          {steps.map((step, idx) => (
            <div key={idx} className="relative flex gap-4">
              {/* Step number bubble */}
              <div className="relative z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border-2 border-slate-700 bg-slate-900 font-bold text-sm text-indigo-400">
                {idx + 1}
              </div>

              {/* Content */}
              <div
                className={cn(
                  'flex-1 rounded-lg border border-l-2 border-slate-800 bg-slate-900/50 p-4 mb-1 hover:bg-slate-900/80 transition-colors',
                  DIFFICULTY_COLORS[step.difficulty]
                )}
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <h4 className="text-sm font-semibold text-slate-200 leading-snug">
                    {step.step}
                  </h4>
                  <Badge
                    variant={DIFFICULTY_VARIANT[step.difficulty]}
                    className="flex-shrink-0"
                  >
                    {step.difficulty}
                  </Badge>
                </div>
                <p className="text-sm text-slate-400 leading-relaxed">
                  {step.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function ResearchReport({ result, sessionId }: ResearchReportProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview')

  const tabBadge: Partial<Record<TabId, number>> = {
    papers: result.papers.length,
    gaps: result.gap_analysis.length,
    roadmap: result.implementation_roadmap.length,
  }

  return (
    <div className="space-y-6 animate-slide-up">
      {/* Tab bar */}
      <div className="flex items-center gap-1 overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/80 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200 whitespace-nowrap',
              activeTab === tab.id
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
            )}
          >
            <span className={activeTab === tab.id ? 'text-white' : 'text-slate-500'}>
              {tab.icon}
            </span>
            {tab.label}
            {tabBadge[tab.id] !== undefined && (
              <span
                className={cn(
                  'ml-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums',
                  activeTab === tab.id
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-700 text-slate-400'
                )}
              >
                {tabBadge[tab.id]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-96">
        {activeTab === 'overview' && <OverviewTab result={result} />}
        {activeTab === 'papers' && <PapersTable papers={result.papers} />}
        {activeTab === 'network' && (
          <CitationNetwork
            sessionId={sessionId}
            fallbackNodes={result.papers}
            fallbackLinks={result.citation_links}
          />
        )}
        {activeTab === 'gaps' && <GapsTab gaps={result.gap_analysis} />}
        {activeTab === 'roadmap' && (
          <RoadmapTab steps={result.implementation_roadmap} />
        )}
      </div>
    </div>
  )
}
