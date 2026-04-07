'use client'

import { useState } from 'react'
import { GitCompareArrows, Loader2, Plus, X } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { compareItems } from '@/lib/api'
import type { CompareResult } from '@/lib/types'

export default function ComparePage() {
  const [items, setItems]       = useState<string[]>(['', ''])
  const [context, setContext]   = useState('')
  const [loading, setLoading]   = useState(false)
  const [result, setResult]     = useState<CompareResult | null>(null)
  const [error, setError]       = useState<string | null>(null)

  function addItem() { setItems(prev => [...prev, '']) }
  function removeItem(i: number) { setItems(prev => prev.filter((_, idx) => idx !== i)) }
  function setItem(i: number, v: string) {
    setItems(prev => prev.map((x, idx) => idx === i ? v : x))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const valid = items.filter(x => x.trim())
    if (valid.length < 2 || loading) return
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await compareItems(valid, context.trim() || undefined)
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Comparison failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-5xl px-4 py-12 space-y-8">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-cyan-400">
              <GitCompareArrows className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Compare</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Comparison Matrix</h1>
          <p className="text-slate-400">
            Compare papers, methods, tools, or approaches across standardized dimensions.
            You can paste arXiv IDs (e.g. 2301.07041) or free-form names.
          </p>
        </div>

        <Card className="border-slate-800 bg-slate-900/50">
          <CardContent className="pt-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                {items.map((item, i) => (
                  <div key={i} className="flex gap-2">
                    <Input
                      value={item}
                      onChange={e => setItem(i, e.target.value)}
                      placeholder={`Item ${i + 1} — e.g. LoRA, QLoRA, or 2106.09685`}
                      disabled={loading}
                    />
                    {items.length > 2 && (
                      <Button type="button" variant="ghost" size="icon"
                        onClick={() => removeItem(i)} disabled={loading}
                        className="text-slate-500 hover:text-red-400">
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                ))}
                <Button type="button" variant="ghost" size="sm"
                  onClick={addItem} disabled={loading || items.length >= 8}
                  className="text-slate-500 hover:text-cyan-400">
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add item
                </Button>
              </div>

              <div className="space-y-1">
                <label className="text-xs text-slate-400">Context (optional)</label>
                <Input
                  value={context}
                  onChange={e => setContext(e.target.value)}
                  placeholder="e.g. Focus on memory efficiency for edge deployment"
                  disabled={loading}
                />
              </div>

              <Button type="submit"
                disabled={items.filter(x => x.trim()).length < 2 || loading}
                className="bg-cyan-700 hover:bg-cyan-600">
                {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                {loading ? 'Comparing…' : 'Compare'}
              </Button>
            </form>
          </CardContent>
        </Card>

        {error && (
          <div className="rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {result && <CompareMatrix result={result} />}
      </div>
    </main>
  )
}

function CompareMatrix({ result }: { result: CompareResult }) {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-100">{result.title}</h2>

      {/* Summary */}
      <Card className="border-slate-800 bg-slate-900/50">
        <CardContent className="pt-4 space-y-2">
          <p className="text-sm text-slate-300">{result.summary}</p>
          {result.recommendation && (
            <p className="text-xs text-cyan-400 font-medium">{result.recommendation}</p>
          )}
        </CardContent>
      </Card>

      {/* Matrix table */}
      {result.dimensions.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-900 border-b border-slate-800">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider w-40">
                  Dimension
                </th>
                {result.items.map(item => (
                  <th key={item} className="px-4 py-3 text-left text-xs font-semibold text-slate-200 min-w-48">
                    {item}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {result.dimensions.map((dim, di) => (
                <tr key={dim} className={di % 2 === 0 ? 'bg-slate-950/30' : 'bg-transparent'}>
                  <td className="px-4 py-3 text-xs font-medium text-slate-400 align-top">{dim}</td>
                  {result.items.map(item => (
                    <td key={item} className="px-4 py-3 text-xs text-slate-300 align-top leading-relaxed">
                      {result.matrix[item]?.[dim] ?? '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
