'use client'

import React, { useCallback, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Upload, FileText, BookOpen, ArrowLeft, AlertCircle, Users } from 'lucide-react'
import Link from 'next/link'
import { startReview } from '@/lib/api'
import { cn } from '@/lib/utils'

export default function ReviewPage() {
  const router = useRouter()
  const paperRef = useRef<HTMLInputElement>(null)
  const bibRef = useRef<HTMLInputElement>(null)

  const [paperFile, setPaperFile] = useState<File | null>(null)
  const [bibFile, setBibFile] = useState<File | null>(null)
  const [numReviewers, setNumReviewers] = useState(3)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer.files)
    const paper = files.find(f => /\.(pdf|tex|latex)$/i.test(f.name))
    const bib   = files.find(f => /\.bib$/i.test(f.name))
    if (paper) setPaperFile(paper)
    if (bib)   setBibFile(bib)
  }, [])

  const handleSubmit = async () => {
    if (!paperFile) return
    setLoading(true)
    setError(null)
    try {
      const { session_id } = await startReview(paperFile, numReviewers, bibFile ?? undefined)
      router.push(`/review/${session_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#030712] text-slate-100">
      {/* Background blobs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-1/4 -left-32 h-72 w-72 rounded-full bg-violet-900/10 blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 h-72 w-72 rounded-full bg-indigo-900/10 blur-3xl" />
      </div>

      <header className="relative border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-6 py-4">
          <Link href="/" className="flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors text-sm">
            <ArrowLeft className="h-4 w-4" /> Back
          </Link>
          <div className="h-5 w-px bg-slate-800" />
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-900/50 border border-violet-700/50">
              <FileText className="h-4 w-4 text-violet-400" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">Paper Review</h1>
              <p className="text-[11px] text-slate-500">AI peer-review with up to 5 independent reviewers</p>
            </div>
          </div>
        </div>
      </header>

      <main className="relative mx-auto w-full max-w-3xl flex-1 px-6 py-12 space-y-8">

        {/* Hero */}
        <div className="text-center space-y-3">
          <h2 className="text-2xl font-bold text-slate-100">Submit your paper for AI review</h2>
          <p className="text-slate-400 text-sm max-w-lg mx-auto">
            Upload your PDF or LaTeX manuscript. Up to 5 independent AI reviewers will search
            the literature, assess novelty, and give a structured peer review. An editor agent
            then synthesises their reports into a final decision.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => paperRef.current?.click()}
          className={cn(
            'relative cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center transition-all duration-200',
            dragging
              ? 'border-violet-500/70 bg-violet-900/10'
              : paperFile
                ? 'border-green-700/50 bg-green-900/10'
                : 'border-slate-700 bg-slate-900/40 hover:border-slate-600 hover:bg-slate-900/60',
          )}
        >
          <input
            ref={paperRef}
            type="file"
            accept=".pdf,.tex,.latex"
            className="hidden"
            onChange={e => e.target.files?.[0] && setPaperFile(e.target.files[0])}
          />
          {paperFile ? (
            <div className="flex flex-col items-center gap-3">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-green-900/30 border border-green-700/40">
                <FileText className="h-7 w-7 text-green-400" />
              </div>
              <p className="text-sm font-medium text-green-300">{paperFile.name}</p>
              <p className="text-xs text-slate-500">{(paperFile.size / 1024).toFixed(0)} KB — click to replace</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-slate-800 border border-slate-700">
                <Upload className="h-7 w-7 text-slate-400" />
              </div>
              <p className="text-sm text-slate-300">Drop your paper here, or click to browse</p>
              <p className="text-xs text-slate-600">PDF, .tex, or .latex — max 20 MB</p>
            </div>
          )}
        </div>

        {/* BibTeX (optional) */}
        <div
          onClick={() => bibRef.current?.click()}
          className={cn(
            'cursor-pointer rounded-xl border border-dashed px-6 py-4 flex items-center gap-4 transition-all duration-150',
            bibFile
              ? 'border-indigo-700/50 bg-indigo-900/10'
              : 'border-slate-800 hover:border-slate-700 hover:bg-slate-900/50',
          )}
        >
          <input ref={bibRef} type="file" accept=".bib" className="hidden"
            onChange={e => e.target.files?.[0] && setBibFile(e.target.files[0])} />
          <BookOpen className={cn('h-5 w-5 flex-shrink-0', bibFile ? 'text-indigo-400' : 'text-slate-600')} />
          <div className="flex-1">
            <p className={cn('text-sm font-medium', bibFile ? 'text-indigo-300' : 'text-slate-500')}>
              {bibFile ? bibFile.name : '.bib reference file (optional)'}
            </p>
            <p className="text-xs text-slate-600">
              {bibFile ? `${(bibFile.size / 1024).toFixed(0)} KB` : 'Helps reviewers compare against your cited works'}
            </p>
          </div>
          {bibFile && (
            <button onClick={e => { e.stopPropagation(); setBibFile(null) }}
              className="text-xs text-slate-600 hover:text-red-400">Remove</button>
          )}
        </div>

        {/* Number of reviewers */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-violet-400" />
            <span className="text-sm font-medium text-slate-300">Number of reviewers</span>
            <span className="ml-auto text-sm font-bold text-violet-300">{numReviewers}</span>
          </div>
          <input type="range" min={1} max={5} value={numReviewers}
            onChange={e => setNumReviewers(Number(e.target.value))}
            className="w-full accent-violet-500" />
          <div className="flex justify-between text-xs text-slate-600">
            <span>1 — quick</span>
            <span>3 — balanced</span>
            <span>5 — thorough</span>
          </div>
          <div className="mt-2 grid grid-cols-5 gap-2">
            {[1,2,3,4,5].map(n => (
              <div key={n} className={cn(
                'rounded-lg border px-2 py-2 text-center text-xs transition-colors',
                n <= numReviewers
                  ? 'border-violet-700/60 bg-violet-900/20 text-violet-300'
                  : 'border-slate-800 text-slate-700',
              )}>
                R{n}
              </div>
            ))}
          </div>
        </div>

        {/* What to expect */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 text-center">
          {[
            { label: 'Novelty check', desc: 'Searches arXiv & Semantic Scholar for prior work' },
            { label: 'Structured review', desc: 'Major/minor issues, scores, recommendation' },
            { label: 'Editor verdict', desc: 'Consolidated decision with action items' },
          ].map(f => (
            <div key={f.label} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
              <p className="text-xs font-semibold text-violet-300 mb-1">{f.label}</p>
              <p className="text-xs text-slate-500">{f.desc}</p>
            </div>
          ))}
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        )}

        <button
          disabled={!paperFile || loading}
          onClick={handleSubmit}
          className="w-full rounded-xl bg-violet-600 py-3.5 text-sm font-semibold text-white transition-all hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? 'Uploading…' : `Submit for review by ${numReviewers} AI reviewer${numReviewers > 1 ? 's' : ''}`}
        </button>
      </main>
    </div>
  )
}
