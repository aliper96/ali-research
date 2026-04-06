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
    description: 'Top papers, fast results',
    icon: <Zap className="h-4 w-4" />,
    time: '~30s',
  },
  {
    value: 'standard',
    label: 'Standard',
    description: 'Balanced depth & speed',
    icon: <BarChart2 className="h-4 w-4" />,
    time: '~2min',
  },
  {
    value: 'deep',
    label: 'Deep',
    description: 'Comprehensive analysis',
    icon: <Layers className="h-4 w-4" />,
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

  const handleExampleClick = (topic: string) => {
    setQuery(topic)
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Search textarea */}
        <div className="relative group">
          <div
            className={cn(
              'absolute -inset-0.5 rounded-xl bg-gradient-to-r from-indigo-500/30 to-purple-500/20 opacity-0 blur transition-opacity duration-300',
              'group-focus-within:opacity-100'
            )}
          />
          <div className="relative rounded-xl border border-slate-700 bg-slate-900 transition-colors duration-200 group-focus-within:border-indigo-500/70">
            <div className="flex items-start gap-3 p-4">
              <Search className="mt-0.5 h-5 w-5 flex-shrink-0 text-indigo-400" />
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter a topic, arXiv ID (e.g. 2301.07041), DOI, or URL..."
                rows={3}
                className="w-full resize-none bg-transparent text-slate-100 placeholder:text-slate-500 text-sm leading-relaxed focus:outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault()
                    void handleSubmit(e as unknown as React.FormEvent)
                  }
                }}
              />
            </div>
            <div className="px-4 pb-2 flex items-center justify-end">
              <span className="text-xs text-slate-600">
                ⌘↵ to search
              </span>
            </div>
          </div>
        </div>

        {/* Depth selector */}
        <div>
          <p className="text-xs font-medium text-slate-400 mb-2.5 uppercase tracking-wider">
            Research Depth
          </p>
          <div className="grid grid-cols-3 gap-2">
            {DEPTH_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setDepth(option.value)}
                className={cn(
                  'relative flex flex-col items-center gap-1.5 rounded-lg border p-3 text-center transition-all duration-200',
                  depth === option.value
                    ? 'border-indigo-500 bg-indigo-900/30 text-indigo-300 shadow-lg shadow-indigo-500/10'
                    : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:bg-slate-800 hover:text-slate-300'
                )}
              >
                <div
                  className={cn(
                    'flex items-center gap-1.5 font-medium text-sm',
                    depth === option.value ? 'text-indigo-300' : 'text-slate-300'
                  )}
                >
                  <span
                    className={depth === option.value ? 'text-indigo-400' : 'text-slate-500'}
                  >
                    {option.icon}
                  </span>
                  {option.label}
                </div>
                <span className="text-xs text-slate-500">{option.description}</span>
                <span
                  className={cn(
                    'text-xs font-mono',
                    depth === option.value ? 'text-indigo-400/70' : 'text-slate-600'
                  )}
                >
                  {option.time}
                </span>
                {depth === option.value && (
                  <div className="absolute inset-0 rounded-lg ring-1 ring-indigo-500/50 pointer-events-none" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Submit button */}
        <Button
          type="submit"
          size="lg"
          className="w-full text-base font-semibold"
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
        <p className="text-xs font-medium text-slate-500 mb-3 text-center uppercase tracking-wider">
          Try an example
        </p>
        <div className="flex flex-wrap gap-2 justify-center">
          {EXAMPLE_TOPICS.map((topic) => (
            <button
              key={topic}
              type="button"
              onClick={() => handleExampleClick(topic)}
              className={cn(
                'rounded-full border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-xs text-slate-400',
                'transition-all duration-150 hover:border-indigo-600/50 hover:bg-indigo-900/20 hover:text-indigo-300',
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
