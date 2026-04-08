'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Search, Zap, BarChart2, Layers, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { startResearch } from '@/lib/api'
import type { Depth } from '@/lib/types'

const EXAMPLE_TOPICS = [
  'Attention mechanisms in transformers',
  'Diffusion models for image generation',
  '2312.00752',
  'Graph neural networks survey',
]

const DEPTH_OPTIONS: {
  value: Depth
  label: string
  description: string
  icon: React.ReactNode
  time: string
}[] = [
  {
    value: 'quick',
    label: 'Quick',
    description: 'Top papers, fast',
    icon: <Zap className="h-3.5 w-3.5" />,
    time: '~30s',
  },
  {
    value: 'standard',
    label: 'Standard',
    description: 'Balanced depth',
    icon: <BarChart2 className="h-3.5 w-3.5" />,
    time: '~2min',
  },
  {
    value: 'deep',
    label: 'Deep',
    description: 'Full analysis',
    icon: <Layers className="h-3.5 w-3.5" />,
    time: '~5min',
  },
]

export default function SearchForm() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [depth, setDepth] = useState<Depth>('standard')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const { session_id } = await startResearch(query.trim(), depth)
      router.push(`/research/${session_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start research')
      setLoading(false)
    }
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <form onSubmit={handleSubmit} className="space-y-4">

        {/* Search box */}
        <div className="relative group">
          {/* Glow ring */}
          <div className={cn(
            'absolute -inset-px rounded-2xl bg-gradient-to-r from-indigo-500/40 to-purple-500/20 opacity-0 blur-sm transition-opacity duration-300',
            'group-focus-within:opacity-100'
          )} />
          <div className="relative rounded-2xl border border-[#1d2d47] bg-[#0d1526]/80 transition-colors duration-200 group-focus-within:border-indigo-500/50 backdrop-blur-sm">
            <div className="flex items-start gap-3 p-5">
              <Search className="mt-1 h-5 w-5 flex-shrink-0 text-indigo-400" />
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter a topic, arXiv ID (e.g. 2301.07041), DOI, or URL..."
                rows={3}
                className="w-full resize-none bg-transparent text-slate-100 placeholder:text-slate-500 text-[15px] leading-relaxed focus:outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault()
                    void handleSubmit(e as unknown as React.FormEvent)
                  }
                }}
              />
            </div>
            <div className="px-5 pb-3 flex items-center justify-between">
              {/* Depth selector — inline */}
              <div className="flex items-center gap-1.5">
                {DEPTH_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setDepth(option.value)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150',
                      depth === option.value
                        ? 'bg-indigo-600/20 border border-indigo-500/40 text-indigo-300'
                        : 'border border-transparent text-slate-500 hover:text-slate-300 hover:bg-[#121d32]'
                    )}
                  >
                    <span className={depth === option.value ? 'text-indigo-400' : 'text-slate-600'}>
                      {option.icon}
                    </span>
                    {option.label}
                    <span className={cn(
                      'font-mono text-[10px]',
                      depth === option.value ? 'text-indigo-400/70' : 'text-slate-600'
                    )}>
                      {option.time}
                    </span>
                  </button>
                ))}
              </div>
              <span className="text-[11px] text-slate-600 select-none">
                Ctrl+Enter
              </span>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-red-900/50 bg-red-900/15 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Submit */}
        <Button
          type="submit"
          size="lg"
          className="w-full text-[15px] font-semibold font-[family-name:var(--font-display)]"
          loading={loading}
          disabled={!query.trim() || loading}
        >
          {!loading && (
            <>
              Start Research
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
          {loading && 'Starting research...'}
        </Button>
      </form>

      {/* Example topics */}
      <div className="mt-8">
        <p className="text-[11px] font-medium text-slate-600 mb-3 text-center uppercase tracking-widest">
          Try an example
        </p>
        <div className="flex flex-wrap gap-2 justify-center">
          {EXAMPLE_TOPICS.map((topic) => (
            <button
              key={topic}
              type="button"
              onClick={() => setQuery(topic)}
              className={cn(
                'rounded-full border border-[#1d2d47] bg-[#0d1526]/60 px-3 py-1.5 text-xs text-slate-500',
                'transition-all duration-150 hover:border-indigo-600/40 hover:bg-indigo-900/15 hover:text-indigo-300',
                'font-mono'
              )}
            >
              {topic}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
